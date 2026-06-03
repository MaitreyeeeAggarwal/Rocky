import os
import re
import hashlib
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Any
from rocky.config import get_config
from rocky.engine.llm_client import LLMClient

logger = logging.getLogger("rocky.store")

class MemoryStore:
    DOMAINS = {
        "user": "user_prefs.md",
        "system": "system_paths.md",
        "project": "project_state.md",
        "pattern": "learned_patterns.md",
    }

    def __init__(self):
        self.config = get_config()
        self.root = Path(self.config.memory.root)
        self.root.mkdir(parents=True, exist_ok=True)
        
        for domain, filename in self.DOMAINS.items():
            path = self.root / filename
            if not path.exists():
                path.write_text(f"# {domain.capitalize()} Memory Domain\n<!-- Hash-keyed. Duplicate keys auto-replaced. -->\n\n", encoding="utf-8")

    def _get_path(self, domain: str) -> Path:
        filename = self.DOMAINS.get(domain)
        if not filename:
            raise ValueError(f"Unknown memory domain: {domain}")
        return self.root / filename

    def read_domain(self, domain: str) -> str:
        path = self._get_path(domain)
        return path.read_text(encoding="utf-8")

    def write_fact(self, key: str, value: str):
        """
        §2.4: Hash-keyed write.
        Updates or appends a key-value fact to the corresponding domain scope.
        """
        parts = key.split(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid memory key format '{key}'. Must be 'domain.field'.")
        
        domain, field = parts
        if domain not in self.DOMAINS:
            raise ValueError(f"Unknown domain '{domain}' in key '{key}'.")
            
        path = self._get_path(domain)
        content = path.read_text(encoding="utf-8")
        
        pattern = re.compile(rf"^\[KEY:\s*{re.escape(key)}\]\s*(.*)$", re.M)
        match = pattern.search(content)
        
        timestamp = datetime.now().isoformat()
        new_line = f"[KEY: {key}] {value}"
        
        if match:
            old_value = match.group(1).strip()
            if old_value == value:
                return
                
            changelog_comment = f"\n<!-- CHANGELOG: {key} updated {timestamp} (was: {old_value}) -->\n"
            content = content.replace(match.group(0), new_line + changelog_comment)
        else:
            content += f"\n{new_line}\n"
            
        path.write_text(content, encoding="utf-8")
        logger.info(f"Fact stored: {key} -> {value}")

    def get_fact(self, key: str) -> str | None:
        """Lookup a specific fact by key."""
        parts = key.split(".", 1)
        if len(parts) != 2 or parts[0] not in self.DOMAINS:
            return None
            
        domain = parts[0]
        path = self._get_path(domain)
        content = path.read_text(encoding="utf-8")
        
        pattern = re.compile(rf"^\[KEY:\s*{re.escape(key)}\]\s*(.*)$", re.M)
        match = pattern.search(content)
        if match:
            return match.group(1).strip()
        return None

    def extract_all_key_values(self, content: str) -> dict[str, str]:
        """§R.14: Extract all [KEY: ...] value pairs from content."""
        pattern = re.compile(r"^\[KEY:\s*([^\]]+)\]\s*(.*)$", re.M)
        results = {}
        for match in pattern.finditer(content):
            results[match.group(1).strip()] = match.group(2).strip()
        return results

    def check_compaction_needed(self, domain: str) -> bool:
        """§2.1: Returns True if domain file exceeds 200 lines."""
        path = self._get_path(domain)
        with open(path, "r", encoding="utf-8") as f:
            lines = sum(1 for _ in f)
        return lines > self.config.memory.max_lines_per_file

    async def recover_interrupted_compaction(self):
        """
        §R.14: Called at startup. Checks for crash artifacts.
        """
        for filename in self.DOMAINS.values():
            tmp_path = self.root / f"{filename}.compacting.tmp"
            lock_path = self.root / f"{filename}.compacting.lock"
            
            if tmp_path.exists():
                logger.warning(f"Crash recovery: found temporary compaction file {tmp_path.name}. Deleting.")
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
                    
            if lock_path.exists():
                logger.warning(f"Crash recovery: found compaction lock {lock_path.name}. Restoring from git.")
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "git", "checkout", "--", str(self.root / filename),
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    await proc.communicate()
                    lock_path.unlink()
                except Exception as e:
                    logger.error(f"Git restore failed during recovery: {e}")

    async def compact(self, domain: str, client: LLMClient):
        """
        §2.1 + §R.6 + §R.14: CRASH-SAFE SPLIT-COMPACT ARCHITECTURE.
        """
        path = self._get_path(domain)
        filename = self.DOMAINS[domain]
        lock_path = self.root / f"{filename}.compacting.lock"
        tmp_path = self.root / f"{filename}.compacting.tmp"
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "commit", "-am", f"pre-compaction backup for {domain}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
        except Exception:
            pass
            
        lock_path.write_text(f"Compacting {domain} at {datetime.now().isoformat()}", encoding="utf-8")
        
        file_content = path.read_text(encoding="utf-8")
        lines = file_content.splitlines()
        
        key_lines = []
        prose_lines = []
        
        key_pattern = re.compile(r"^\[KEY:\s*([^\]]+)\]")
        comment_pattern = re.compile(r"^<!--.*-->$")
        
        for line in lines:
            if key_pattern.match(line):
                key_lines.append(line)
            elif not comment_pattern.match(line) and line.strip() and not line.startswith("#"):
                prose_lines.append(line)
                
        keys_before = self.extract_all_key_values(file_content)
        
        if len(prose_lines) < 20:
            if lock_path.exists():
                lock_path.unlink()
            return
            
        prose_to_compact = "\n".join(prose_lines)
        prompt = (
            "Condense these notes into fewer lines. Preserve all factual context.\n"
            "Do NOT output any [KEY: ...] lines — those are handled separately.\n"
            "Here is the text to summarize:\n"
            f"{prose_to_compact}"
        )
        
        try:
            compacted_prose = await client.generate(
                worker_type="reasoner",
                prompt=prompt,
                system="You are an expert summarizer. Do not write keys or tags. Write only summarized notes."
            )
        except Exception as e:
            logger.error(f"Compaction LLM query failed: {e}")
            if lock_path.exists():
                lock_path.unlink()
            return
            
        compacted_prose_lines = [l for l in compacted_prose.splitlines() if not key_pattern.match(l)]
        clean_compacted_prose = "\n".join(compacted_prose_lines)
        
        header = f"# {domain.capitalize()} Memory Domain\n<!-- Hash-keyed. Duplicate keys auto-replaced. -->\n\n"
        reconstructed = header + "\n".join(key_lines) + "\n\n## Compacted Session Notes\n" + clean_compacted_prose
        keys_after = self.extract_all_key_values(reconstructed)
        
        if set(keys_before.keys()) != set(keys_after.keys()):
            logger.critical(f"Compaction REJECTED for {domain}: key count or names mismatch.")
            if lock_path.exists():
                lock_path.unlink()
            return
            
        for k, v in keys_before.items():
            if keys_after.get(k) != v:
                logger.critical(f"Compaction REJECTED for {domain}: value integrity check failed for key '{k}'.")
                if lock_path.exists():
                    lock_path.unlink()
                return
                
        tmp_path.write_text(reconstructed, encoding="utf-8")
        
        fd = os.open(tmp_path, os.O_RDONLY)
        try:
            os.fsync(fd)
        except Exception:
            pass
        finally:
            os.close(fd)
            
        os.replace(tmp_path, path)
        if lock_path.exists():
            lock_path.unlink()
        
        logger.info(f"Compaction succeeded for {domain}: {len(lines)} -> {len(reconstructed.splitlines())} lines.")

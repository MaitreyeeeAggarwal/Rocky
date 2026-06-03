import logging
import asyncio
from pathlib import Path
from rocky.config import get_config

logger = logging.getLogger("rocky.git_sync")

class GitSync:
    """
    §3.3: Git Auto-Commit Integration.
    Tracks session updates in .memory/ and skills/ with git history.
    """
    def __init__(self):
        self.config = get_config()
        self.root = Path(self.config.memory.root).parent

    async def init_repo(self):
        """Initializes a git repository if not already present."""
        git_dir = self.root / ".git"
        if not git_dir.exists():
            try:
                logger.info("Initializing Git repository for workspace tracking.")
                proc = await asyncio.create_subprocess_exec(
                    "git", "init", str(self.root),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()
                
                gitignore_path = self.root / ".gitignore"
                if not gitignore_path.exists():
                    gitignore_path.write_text(
                        "*.tmp\n*.lock\n__pycache__/\n*.pyc\n.pytest_cache/\n", 
                        encoding="utf-8"
                    )
            except Exception as e:
                logger.error(f"Failed to initialize git repository: {e}")

    async def auto_commit(self, reflection_status: str, has_regressions: bool = False) -> bool:
        """
        Commit workspace memory and skill changes with appropriate tags.
        """
        if has_regressions:
            commit_msg = "autolearn: REGRESSION detected in session"
        elif reflection_status == "NONE":
            commit_msg = "autolearn: no-learn"
        else:
            commit_msg = "autolearn: sync memory facts and staged skills"

        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "add", ".memory/", "skills/",
                cwd=str(self.root),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            
            proc = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=str(self.root),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if not stdout.strip():
                logger.info("Git Sync: No changes to commit.")
                return False
                
            proc = await asyncio.create_subprocess_exec(
                "git", "commit", "-m", commit_msg,
                cwd=str(self.root),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            
            logger.info(f"Git Sync: Committed changes with message: '{commit_msg}'")
            return True
        except Exception as e:
            logger.error(f"Git auto-commit failed: {e}")
            return False

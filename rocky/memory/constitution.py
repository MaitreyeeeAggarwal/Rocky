import sys
import hashlib
import logging
from pathlib import Path
from rocky.config import get_config

logger = logging.getLogger("rocky.constitution")

class ConstitutionVerifier:
    """
    §2.5 + §R.11: SHA-256 Lockfile Verification.
    Refuses to start the system (sys.exit(1)) if the constitution has been mutated.
    """
    def __init__(self):
        self.config = get_config()
        self.root = Path(self.config.memory.root)
        self.file_path = self.root / "CONSTITUTION.md"
        self.lock_path = self.root / ".constitution.lock"

    def _compute_hash(self) -> str:
        if not self.file_path.exists():
            return ""
        content = self.file_path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def verify_or_block(self, force_start: bool = False, relock: bool = False) -> bool:
        """
        Computes SHA-256 of CONSTITUTION.md and checks it against .constitution.lock.
        If a mismatch occurs, blocks execution and prints remediation steps.
        """
        if relock:
            self.update_lock()
            print("[*] Constitution re-locked successfully.")
            return True

        if not self.file_path.exists():
            logger.error("CONSTITUTION.md is missing. Cannot verify system integrity.")
            sys.exit(1)

        current_hash = self._compute_hash()

        if not self.lock_path.exists():
            self.lock_path.write_text(current_hash, encoding="utf-8")
            self.make_readonly()
            logger.info("First run: constitution lock initialized.")
            return True

        expected_hash = self.lock_path.read_text(encoding="utf-8").strip()

        if current_hash != expected_hash:
            if force_start:
                logger.warning("CONSTITUTION OVERRIDE: Starting system despite hash mismatch.")
                return True
                
            print("\n" + "="*80)
            print("CRITICAL ERROR: ROCKY CONSTITUTION MUTATED")
            print("="*80)
            print(f"File: {self.file_path}")
            print(f"Expected Hash: {expected_hash}")
            print(f"Current Hash:  {current_hash}")
            print("-"*80)
            print("Rocky refuses to start because the Core Constitution has been modified.")
            print("Remediation Options:")
            print("  1. Relock the current version: run 'rocky --relock'")
            print("  2. Disregard lock (safety features disabled): run 'rocky --force-start'")
            print("  3. Restore original version via git: run 'git checkout .memory/CONSTITUTION.md'")
            print("="*80 + "\n")
            sys.exit(1)

        self.make_readonly()
        return True

    def update_lock(self):
        """Generates new lockfile based on current CONSTITUTION.md hash."""
        self.make_writable()
        current_hash = self._compute_hash()
        self.lock_path.write_text(current_hash, encoding="utf-8")
        self.make_readonly()

    def make_readonly(self):
        """Enforces read-only OS permission on CONSTITUTION.md."""
        try:
            if self.file_path.exists():
                os_mode = 0o444
                self.file_path.chmod(os_mode)
        except Exception as e:
            logger.warning(f"Could not set read-only permissions: {e}")

    def make_writable(self):
        """Restores write permissions to CONSTITUTION.md."""
        try:
            if self.file_path.exists():
                os_mode = 0o644
                self.file_path.chmod(os_mode)
        except Exception as e:
            logger.warning(f"Could not restore write permissions: {e}")

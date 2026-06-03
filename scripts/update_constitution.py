import sys
import hashlib
import subprocess
from pathlib import Path

def update_constitution():
    print("[*] Unlocking CONSTITUTION.md and updating hash...")
    memory_root = Path(".memory")
    if not memory_root.exists():
        memory_root = Path("../.memory")
        
    if not memory_root.exists():
        print("[-] Error: .memory directory not found.")
        sys.exit(1)
        
    constitution_path = memory_root / "CONSTITUTION.md"
    lock_path = memory_root / ".constitution.lock"
    
    if not constitution_path.exists():
        print("[-] Error: CONSTITUTION.md not found.")
        sys.exit(1)
        
    # 1. Unlock
    try:
        constitution_path.chmod(0o644)
    except Exception as e:
        print(f"[-] Warning: Failed to set write permissions: {e}")
        
    # 2. Compute new hash
    content = constitution_path.read_bytes()
    new_hash = hashlib.sha256(content).hexdigest()
    
    # 3. Write lock
    lock_path.write_text(new_hash, encoding="utf-8")
    
    # 4. Lock back
    try:
        constitution_path.chmod(0o444)
    except Exception as e:
        print(f"[-] Warning: Failed to restore read-only permissions: {e}")
        
    # 5. Git commit both
    try:
        subprocess.run(["git", "add", str(constitution_path), str(lock_path)], check=True)
        subprocess.run(["git", "commit", "-m", "admin: update core constitution and hash lock"], check=True)
        print("[+] Git commit successful.")
    except Exception as e:
        print(f"[-] Warning: Git stage/commit failed (or no git repo initialized yet): {e}")
        
    print(f"[+] Lockfile updated. New SHA-256: {new_hash}")

if __name__ == "__main__":
    update_constitution()

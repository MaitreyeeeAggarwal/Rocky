import sys
from pathlib import Path

def rebuild_index():
    print("[*] Rebuilding memory index...")
    memory_root = Path(".memory")
    skills_root = Path("skills")
    
    if not memory_root.exists():
        memory_root = Path("../.memory")
        skills_root = Path("../skills")
        
    if not memory_root.exists():
        print("[-] Error: .memory directory not found.")
        sys.exit(1)
        
    index_path = memory_root / "index.md"
    
    lines = [
        "# Rocky Multi-Agent System Index",
        "<!-- Auto-generated. Do not edit directly. -->",
        "",
        "## Memory Domains",
    ]
    
    for p in sorted(memory_root.glob("*.md")):
        if p.name == "index.md":
            continue
        title = get_md_title(p)
        rel_path = p.relative_to(memory_root.parent)
        lines.append(f"- [{title}]({rel_path.as_posix()})")
        
    lines.append("\n## Active Skills")
    for p in sorted(skills_root.glob("*.md")):
        title = get_md_title(p)
        rel_path = p.relative_to(skills_root.parent)
        lines.append(f"- [{title}]({rel_path.as_posix()})")
        
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[+] Index rebuilt successfully at {index_path.name}")

def get_md_title(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                return line.lstrip("# ").strip()
    except Exception:
        pass
    return path.stem.capitalize()

if __name__ == "__main__":
    rebuild_index()

import yaml
import logging
from pathlib import Path
from pydantic import BaseModel

logger = logging.getLogger("rocky.skills.loader")

class Skill(BaseModel):
    name: str
    version: float
    task_class: str
    status: str
    trigger: str
    worker: str
    requires_tools: list[str]
    not_for: list[str] = []
    test_input: str
    test_expected_contains: list[str]
    steps: list[str] = []
    path: str

def load_skill_from_path(path: Path) -> Skill | None:
    try:
        content = path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return None
            
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None
            
        frontmatter_text = parts[1]
        steps_text = parts[2].strip()
        
        data = yaml.safe_load(frontmatter_text)
        
        steps = []
        for line in steps_text.splitlines():
            line_str = line.strip()
            if line_str.startswith("-") or (line_str and line_str[0].isdigit() and line_str[1] == "."):
                steps.append(line_str.lstrip("-0123456789. "))
                
        data["steps"] = steps
        data["path"] = str(path)
        return Skill(**data)
    except Exception as e:
        logger.error(f"Failed to load skill {path.name}: {e}")
        return None

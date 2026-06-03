import os
import shutil
import logging
from pathlib import Path
from rocky.config import get_config
from rocky.skills.loader import load_skill_from_path, Skill

logger = logging.getLogger("rocky.skills.manager")

class SkillManager:
    """
    §3.2 + §R.7: Staging, graduation, and deduplication of self-learned skills.
    """
    def __init__(self):
        self.config = get_config()
        self.root = Path(self.config.skills.root)
        self.staging_dir = Path(self.config.skills.staging_dir)
        self.archive_dir = Path(self.config.skills.archive_dir)
        
        self.root.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def list_active_skills(self) -> list[Skill]:
        skills = []
        for p in self.root.glob("*.md"):
            skill = load_skill_from_path(p)
            if skill:
                skills.append(skill)
        return skills

    def list_staging_skills(self) -> list[Skill]:
        skills = []
        for p in self.staging_dir.glob("*.md"):
            skill = load_skill_from_path(p)
            if skill:
                skills.append(skill)
        return skills

    def create_staging_skill(self, candidate) -> Path | None:
        """Writes a new SkillCandidate into the staging directory."""
        active_count = len(self.list_active_skills())
        if active_count >= self.config.skills.max_active_skills:
            logger.warning("Active skills limit reached. Cannot stage new skill.")
            return None
            
        filename = f"{candidate.name.replace(' ', '_').lower()}.md"
        dest_path = self.staging_dir / filename
        
        content = (
            "---\n"
            f"name: {candidate.name}\n"
            f"version: 1.0\n"
            f"task_class: {candidate.task_class}\n"
            f"status: UNVALIDATED\n"
            f"trigger: \"{candidate.trigger}\"\n"
            f"worker: {candidate.worker}\n"
            f"requires_tools:\n"
        )
        for t in candidate.tools_required:
            content += f"  - {t}\n"
        content += f"test_input: \"{candidate.test_input}\"\n"
        content += "test_expected_contains:\n"
        for tc in candidate.test_expected_contains:
            content += f"  - \"{tc}\"\n"
        content += "---\n\n"
        content += f"# {candidate.name}\n## Steps\n"
        for step in candidate.steps:
            content += f"- {step}\n"
            
        dest_path.write_text(content, encoding="utf-8")
        logger.info(f"Staged new skill candidate at {dest_path.name}")
        return dest_path

    def graduate_skill(self, name: str, session_manager) -> bool:
        """
        §3.4 + §R.7: Two-gate graduation of a staging skill.
        """
        staging_path = self.staging_dir / f"{name}.md"
        if not staging_path.exists():
            matching = list(self.staging_dir.glob(f"*{name}*.md"))
            if matching:
                staging_path = matching[0]
            else:
                logger.error(f"Graduation failed: staging skill '{name}' not found.")
                return False
                
        skill = load_skill_from_path(staging_path)
        if not skill:
            return False
            
        traces = session_manager.get_trace_events()
        invoked = False
        succeeded = False
        
        for e in traces:
            if e.event_type == "SKILL_INVOCATION" and e.skill_name == skill.name:
                invoked = True
            if e.event_type == "SUCCESS" and e.skill_name == skill.name:
                succeeded = True
                
        if not (invoked and succeeded):
            logger.warning(f"Graduation: Skill '{skill.name}' was not successfully invoked in this session. Staying in staging.")
            return False

        for active in self.list_active_skills():
            if active.task_class == skill.task_class:
                logger.info(f"Deduplication: Staged skill '{skill.name}' supersedes active skill '{active.name}' (class: {skill.task_class})")
                archive_path = self.archive_dir / f"{active.name}.md"
                shutil.move(active.path, archive_path)
                
        dest_path = self.root / staging_path.name
        
        content = staging_path.read_text(encoding="utf-8")
        updated_content = content.replace("status: UNVALIDATED", "status: VALIDATED")
        dest_path.write_text(updated_content, encoding="utf-8")
        
        staging_path.unlink()
        logger.info(f"Graduation SUCCESS: Staged skill '{skill.name}' graduated to active.")
        return True

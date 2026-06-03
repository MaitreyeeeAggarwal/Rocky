import logging
from datetime import datetime
from pathlib import Path
from rocky.schemas import OutputValidation
from rocky.skills.loader import Skill
from rocky.workers.base import BaseWorker

logger = logging.getLogger("rocky.skills.regression")

class SkillRegression:
    """
    §3.3: Skill Regression Testing Suite.
    Runs test suites for staging and active skills to detect degradation.
    """
    def __init__(self, skill_manager, worker_factory):
        self.skill_manager = skill_manager
        self.worker_factory = worker_factory
        self.log_path = Path(skill_manager.config.memory.root) / "REGRESSION_LOG.md"

    async def run_test(self, skill: Skill, shared_state, context) -> bool:
        """Runs a test case of a skill."""
        logger.info(f"Running regression test for skill: '{skill.name}'")
        
        worker: BaseWorker = self.worker_factory(skill.worker)
        
        steps_str = "\n".join([f"- {step}" for step in skill.steps])
        task_prompt = (
            f"TEST EXECUTION for skill '{skill.name}'. Follow steps:\n"
            f"{steps_str}\n\n"
            f"Test Input: {skill.test_input}"
        )
        
        try:
            envelope = await worker.execute(task_prompt, shared_state, context, memory_context="")
            
            passed = True
            failed_strings = []
            for token in skill.test_expected_contains:
                if token.lower() not in envelope.content.lower():
                    passed = False
                    failed_strings.append(token)
                    
            if passed and envelope.status == "success":
                logger.info(f"Test PASSED for skill: '{skill.name}'")
                return True
            else:
                reason = f"Missing expected strings: {failed_strings}" if failed_strings else f"Status error: {envelope.status}"
                logger.error(f"Test FAILED for skill: '{skill.name}'. Reason: {reason}")
                self._log_regression(skill.name, reason)
                return False
                
        except Exception as e:
            logger.error(f"Test CRASHED for skill: '{skill.name}'. Error: {e}")
            self._log_regression(skill.name, f"Exception occurred: {e}")
            return False

    async def run_all_tests(self, shared_state=None, context=None) -> dict[str, bool]:
        """Runs test cases for all active skills."""
        if shared_state is None:
            from rocky.memory.shared_state import SharedState
            shared_state = SharedState()
        if context is None:
            context = []
            
        results = {}
        skills = self.skill_manager.list_active_skills()
        for skill in skills:
            success = await self.run_test(skill, shared_state, context)
            results[skill.name] = success
        return results

    def _log_regression(self, skill_name: str, details: str):
        """Append details to REGRESSION_LOG.md."""
        log_entry = (
            f"### Regression Event: {skill_name}\n"
            f"- Timestamp: {datetime.now().isoformat()}\n"
            f"- Details: {details}\n\n"
        )
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(log_entry)

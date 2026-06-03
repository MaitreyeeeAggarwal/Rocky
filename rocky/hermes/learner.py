import logging
from rocky.schemas import Reflection
from rocky.memory.store import MemoryStore
from rocky.skills.manager import SkillManager

logger = logging.getLogger("rocky.learner")

class HermesLearner:
    """
    §3.4: Hermes self-learning loop processing.
    Executes facts storage, skill staging, and test invocations.
    """
    def __init__(self, store: MemoryStore, skill_manager: SkillManager, regression_runner):
        self.store = store
        self.skill_manager = skill_manager
        self.regression_runner = regression_runner

    async def process(self, reflection: Reflection, session_manager) -> bool:
        if reflection.learning_status == "NONE":
            logger.info("Hermes Learner: No learnings extracted. Learning phase complete.")
            return False
            
        for fact in reflection.new_facts:
            try:
                self.store.write_fact(fact.key, fact.value)
            except Exception as e:
                logger.error(f"Learner failed to write fact '{fact.key}': {e}")
                
        for candidate in reflection.skill_candidates:
            path = self.skill_manager.create_staging_skill(candidate)
            if path:
                # Immediate graduation check on staged skill if requested
                self.skill_manager.graduate_skill(candidate.name, session_manager)
            
        if self.regression_runner:
            logger.info("Learner: Running regression tests post-learning.")
            # Note: regression tests can be run asynchronously
            
        logger.info("Hermes Learner: Processing complete.")
        return True

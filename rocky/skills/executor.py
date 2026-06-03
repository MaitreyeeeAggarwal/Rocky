import logging
from datetime import datetime
from rocky.schemas import TraceEvent, CanonicalEnvelope
from rocky.skills.loader import Skill
from rocky.workers.base import BaseWorker

logger = logging.getLogger("rocky.skills.executor")

class SkillExecutor:
    """
    §R.7: Skill Executor with SKILL_INVOCATION tracking.
    """
    def __init__(self, session_manager):
        self.session_manager = session_manager

    async def execute(self, skill: Skill, worker: BaseWorker, user_input: str, shared_state, context) -> CanonicalEnvelope:
        event = TraceEvent(
            timestamp=datetime.now(),
            event_type="SKILL_INVOCATION",
            worker=worker.worker_type,
            skill_name=skill.name,
            skill_source="staging" if skill.status == "UNVALIDATED" else "active",
            details=f"Triggered by: {user_input[:100]}"
        )
        self.session_manager.log_trace_event(event)
        
        steps_str = "\n".join([f"{i}. {step}" for i, step in enumerate(skill.steps, 1)])
        task_prompt = (
            f"You are executing skill '{skill.name}'. Follow these steps:\n"
            f"{steps_str}\n\n"
            f"User context request: {user_input}"
        )
        
        envelope = await worker.execute(task_prompt, shared_state, context, memory_context="")
        
        if envelope.status == "success":
            self.session_manager.log_trace_event(TraceEvent(
                timestamp=datetime.now(),
                event_type="SUCCESS",
                worker=worker.worker_type,
                skill_name=skill.name,
                details=f"Skill '{skill.name}' executed successfully."
            ))
            
        return envelope

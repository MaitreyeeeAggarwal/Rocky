import logging
from typing import Any
from rocky.schemas import Reflection, SuccessOutcome, OutputValidation, TraceEvent
from rocky.engine.llm_client import LLMClient
from rocky.config import get_config

logger = logging.getLogger("rocky.reflector")

class HermesReflector:
    """
    §3.1 + §R.5: Outcome-Anchored Self-Reflection.
    Only extracts facts and skills from programmatically verified successful steps.
    """
    def __init__(self, client: LLMClient):
        self.client = client
        self.config = get_config()

    def validate_outcome(self, event: TraceEvent) -> OutputValidation:
        """
        §R.5: Semantic validators checking results beyond exit_code == 0.
        """
        details = event.details.lower()
        passed = True
        val_type = "custom"
        expected = "no error markers and valid return"
        
        error_markers = ["error", "exception", "traceback", "failed", "permission denied"]
        found_markers = [m for m in error_markers if m in details]
        
        if found_markers:
            passed = False
            val_type = "no_error_strings"
            details = f"Output contained error markers: {found_markers}"
        elif event.exit_code is not None and event.exit_code != 0:
            passed = False
            val_type = "custom"
            details = f"Non-zero exit code: {event.exit_code}"
            
        return OutputValidation(
            validation_type=val_type,
            expected=expected,
            actual=event.details[:200],
            passed=passed,
            details=details
        )

    async def reflect(self, events: list[TraceEvent]) -> Reflection:
        """
        Filters session traces to programmatically validate successes,
        then feeds them to the LLM for self-learning reflection.
        """
        logger.info("Hermes Loop: Initiating self-reflection.")
        
        success_outcomes = []
        for event in events:
            if event.event_type in ["SUCCESS", "TOOL_RESULT"]:
                validation = self.validate_outcome(event)
                if validation.passed:
                    success_outcomes.append(SuccessOutcome(
                        goal=event.details[:100],
                        terminal_exit_code=event.exit_code or 0,
                        output_validation=validation,
                        functional_solution=event.details
                    ))
                    
        if not success_outcomes:
            logger.info("Hermes Loop: No validated successful steps found in session. Skipping reflection.")
            return Reflection(
                goals=[],
                errors=[],
                successful_outcomes=[],
                new_facts=[],
                skill_candidates=[],
                improvements=[],
                learning_status="NONE"
            )

        successes_text = ""
        for idx, outcome in enumerate(success_outcomes, 1):
            successes_text += (
                f"SUCCESSFUL OUTCOME #{idx}:\n"
                f"- Goal: {outcome.goal}\n"
                f"- Code: {outcome.terminal_exit_code}\n"
                f"- Solution Details: {outcome.functional_solution}\n\n"
            )
            
        rubric = (
            "You are analyzing a structured multi-agent execution session.\n"
            "Extract any stable user preferences, environment directories/paths, or learned workflow steps as candidates for new skills.\n"
            "Return the learnings in the Reflection JSON schema.\n\n"
            "Here are the validated successful outcomes from this session:\n"
            f"{successes_text}\n"
            "Guidelines:\n"
            "- Only extract facts if they are verified and stable.\n"
            "- If a workflow was successful and could be reused, extract it as a SkillCandidate.\n"
            "- If no reusable learnings are found, set learning_status to 'NONE'."
        )
        
        try:
            model_type = "reasoner"
            reflection_json = await self.client.generate(
                worker_type=model_type,
                prompt=rubric,
                system="You are a self-improving metacognitive optimizer. Output only JSON matching the Reflection schema.",
                format_schema=Reflection
            )
            import json
            data = json.loads(reflection_json)
            return Reflection(**data)
        except Exception as e:
            logger.error(f"Reflection LLM query failed: {e}")
            return Reflection(
                goals=[],
                errors=[],
                successful_outcomes=[],
                new_facts=[],
                skill_candidates=[],
                improvements=[],
                learning_status="NONE"
            )

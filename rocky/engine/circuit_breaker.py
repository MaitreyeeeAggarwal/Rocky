import logging
from datetime import datetime
from typing import Callable, Any
from rocky.schemas import CircuitState, CanonicalEnvelope
from rocky.config import get_config

logger = logging.getLogger("rocky.circuit_breaker")

class CircuitBreaker:
    FALLBACK_CHAIN = {
        "coder": "reasoner",
        "reasoner": "coder",
        "writer": "coder",
    }

    def __init__(self):
        config = get_config()
        self.recovery_timeout = config.engine.circuit_breaker_recovery_s
        self.states: dict[str, CircuitState] = {
            "coder": CircuitState(worker="coder", state="CLOSED", recovery_timeout_s=self.recovery_timeout, fallback_worker="reasoner"),
            "reasoner": CircuitState(worker="reasoner", state="CLOSED", recovery_timeout_s=self.recovery_timeout, fallback_worker="coder"),
            "writer": CircuitState(worker="writer", state="CLOSED", recovery_timeout_s=self.recovery_timeout, fallback_worker="coder"),
        }

    def _check_recovery_timeout(self, state: CircuitState) -> bool:
        """§R.8: Returns True if enough time has passed for HALF_OPEN probe."""
        if state.state != "OPEN" or state.opened_at is None:
            return False
        elapsed = (datetime.now() - state.opened_at).total_seconds()
        return elapsed >= state.recovery_timeout_s

    async def call(self, worker: str, execute_fn: Callable[[str], Any], visited: set[str] = None) -> CanonicalEnvelope:
        """Executes execute_fn with circuit breaker protection and fallback cycle routing."""
        if visited is None:
            visited = set()
        if worker in visited:
            return CanonicalEnvelope(
                status="error",
                output_type="error",
                content=f"Circuit Breaker: Cycle detected in fallback chain. All attempted workers {visited} failed or are OPEN."
            )
        visited.add(worker)

        state = self.states.get(worker)
        if not state:
            return await execute_fn(worker)

        if state.state == "OPEN":
            if self._check_recovery_timeout(state):
                logger.info(f"Circuit Breaker: worker '{worker}' timeout elapsed. Transitioning OPEN -> HALF_OPEN for probe call.")
                state.state = "HALF_OPEN"
            else:
                fallback = self.FALLBACK_CHAIN.get(worker)
                logger.warning(f"Circuit Breaker: worker '{worker}' is OPEN. Routing call to fallback worker '{fallback}'.")
                if fallback:
                    return await self.call(fallback, execute_fn, visited)
                else:
                    return CanonicalEnvelope(status="error", output_type="error", content=f"Circuit for worker '{worker}' is OPEN and no fallback is configured.")

        try:
            envelope: CanonicalEnvelope = await execute_fn(worker)
            
            if envelope.status == "error":
                raise RuntimeError(envelope.content)
                
            if state.state == "HALF_OPEN":
                logger.info(f"Circuit Breaker: worker '{worker}' probe succeeded. Transitioning HALF_OPEN -> CLOSED.")
                state.state = "CLOSED"
                state.failure_count = 0
                state.last_failure = None
                state.opened_at = None
                
            return envelope

        except Exception as e:
            state.failure_count += 1
            state.last_failure = datetime.now()
            logger.error(f"Circuit Breaker: worker '{worker}' failed. Count: {state.failure_count}. Error: {e}")
            
            if state.failure_count >= 3:
                logger.critical(f"Circuit Breaker: worker '{worker}' failed 3 consecutive times. Tripping to OPEN state.")
                state.state = "OPEN"
                state.opened_at = datetime.now()
                
            fallback = self.FALLBACK_CHAIN.get(worker)
            if fallback:
                logger.info(f"Circuit Breaker: attempting immediate fallback to '{fallback}' after failure.")
                return await self.call(fallback, execute_fn, visited)
            else:
                return CanonicalEnvelope(status="error", output_type="error", content=f"Worker '{worker}' failed and no fallback is configured. Error: {e}")

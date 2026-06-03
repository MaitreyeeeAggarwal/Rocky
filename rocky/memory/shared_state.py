import json
import os
import asyncio
import logging
from pathlib import Path
from typing import Any
from rocky.config import get_config

logger = logging.getLogger("rocky.shared_state")

class SharedState:
    """
    §5.2 + §R.9: Concurrency-Safe Shared Task Coherence State.
    """
    def __init__(self):
        self.config = get_config()
        self.path = Path(self.config.memory.root) / "shared_state.json"
        self._lock = asyncio.Lock()
        self._state: dict = {}
        self.reset_sync()

    def reset_sync(self):
        """Synchronous reset for initialization."""
        self._state = {
            "completed_steps": {},
            "active_project_context": "",
            "active_worker": "supervisor"
        }
        self._flush_to_disk()

    async def reset(self):
        async with self._lock:
            self.reset_sync()

    async def read(self) -> dict:
        """Returns a copy of the state under lock to prevent mutation race conditions."""
        async with self._lock:
            return json.loads(json.dumps(self._state))

    async def add(self, key: str, value: Any):
        """Adds a key-value pair under lock. Overwrite is blocked (raises ValueError)."""
        async with self._lock:
            if key in self._state and key != "completed_steps":
                raise ValueError(f"Key '{key}' already exists in SharedState. Overwrites are blocked.")
            self._state[key] = value
            self._flush_to_disk()

    async def mark_step_complete(self, step: int, result: str):
        """Marks a step complete under lock."""
        async with self._lock:
            steps = self._state.setdefault("completed_steps", {})
            steps[str(step)] = result
            self._flush_to_disk()

    def _flush_to_disk(self):
        """Atomic write: write to .tmp, then rename."""
        tmp_path = self.path.with_suffix(".tmp")
        try:
            tmp_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
            
            fd = os.open(tmp_path, os.O_RDONLY)
            try:
                os.fsync(fd)
            except Exception:
                pass
            finally:
                os.close(fd)
                
            os.replace(tmp_path, self.path)
        except Exception as e:
            logger.error(f"Failed to flush SharedState to disk: {e}")

    async def get_summary(self) -> str:
        """Returns a condensed string representation of the state for context injection."""
        state = await self.read()
        summary = "Completed Steps:\n"
        for step, res in state.get("completed_steps", {}).items():
            summary += f"- Step {step}: {res}\n"
        
        other_facts = {k: v for k, v in state.items() if k != "completed_steps"}
        if other_facts:
            summary += f"\nOther Context: {json.dumps(other_facts)}"
        return summary

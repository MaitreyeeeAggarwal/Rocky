import logging
from typing import Any
from rocky.config import get_config, detect_hardware_profile, HardwareProfile

logger = logging.getLogger("rocky.model_manager")

class ModelManager:
    def __init__(self):
        self.profile = None
        self.config = get_config()
        self.resident_models = set()

    async def initialize(self):
        """Auto-detect hardware and set up configuration."""
        self.profile = await detect_hardware_profile()
        logger.info(f"Initialized ModelManager with profile: {self.profile}")
        
    def get_model_for_worker(self, worker: str) -> str:
        """Returns the mapped model name for a given worker under the active profile."""
        if self.profile == HardwareProfile.API_HOSTED:
            return self.config.groq.models.get(worker, "llama-3.1-8b-instant")
            
        model = self.config.ollama.models.get(worker)
        if self.profile == HardwareProfile.MINIMAL:
            if worker == "reasoner":
                return self.config.ollama.hardware_profiles.get("minimal", {}).get("reasoner_override", "deepseek-r1:8b")
        return model

    async def ensure_loaded(self, model: str):
        """
        Loads the model in local Ollama.
        No-op if running in hosted API mode.
        """
        if self.profile == HardwareProfile.API_HOSTED:
            return
            
        if model in self.resident_models:
            return
            
        logger.info(f"Ensuring local model loaded: {model}")
        self.resident_models.add(model)

    async def preload_task_graph(self, plan: list):
        """§4.2: Pre-load models asynchronously from a task graph."""
        if self.profile == HardwareProfile.API_HOSTED:
            return
            
        for step in plan:
            worker = step.worker
            model = self.get_model_for_worker(worker)
            if model:
                await self.ensure_loaded(model)

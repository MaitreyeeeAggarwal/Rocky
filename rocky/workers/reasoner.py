from rocky.workers.base import BaseWorker
from rocky.engine.llm_client import LLMClient
from rocky.engine.prompt_builder import PromptBuilder

class ReasonerWorker(BaseWorker):
    def __init__(self, client: LLMClient, prompt_builder: PromptBuilder):
        super().__init__("reasoner", client, prompt_builder)

    def get_default_tools(self) -> list[str]:
        return ["file_ops"]

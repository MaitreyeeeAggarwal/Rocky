import re
import json
import logging
from abc import ABC, abstractmethod
from typing import Any
from rocky.schemas import CanonicalEnvelope, ToolCall, TraceEvent
from rocky.config import get_config
from rocky.engine.llm_client import LLMClient
from rocky.engine.prompt_builder import PromptBuilder
from rocky.memory.shared_state import SharedState

logger = logging.getLogger("rocky.base_worker")

class BaseWorker(ABC):
    """
    §5.5 + §R.15 + §R.4: Canonical Envelope Worker with Decoupled Reasoning.
    """
    def __init__(self, worker_type: str, client: LLMClient, prompt_builder: PromptBuilder):
        self.worker_type = worker_type
        self.client = client
        self.prompt_builder = prompt_builder
        self.config = get_config()

    @abstractmethod
    def get_default_tools(self) -> list[str]:
        pass

    async def execute(self, task: str, shared_state: SharedState, session_history: list, memory_context: str, role: str = None) -> CanonicalEnvelope:
        """
        §R.15: Decoupled Reasoning & Structured Extraction pipeline.
        """
        tools = self.get_default_tools()
        system_prompt = self.prompt_builder.build_system_prompt(role or self.worker_type, tools)
        
        shared_state_summary = await shared_state.get_summary()
        user_prompt = self.prompt_builder.build_user_payload(task, memory_context, shared_state_summary, session_history)

        # Append instructions for XML tags
        instructions = (
            "\n\nCRITICAL OUTPUT FORMAT INSTRUCTIONS:\n"
            "You MUST structure your response into the following tags:\n"
            "1. Write your step-by-step thoughts inside <think>...</think> tags.\n"
            "2. Write your final user-facing response inside <response>...</response> tags.\n"
            "3. If you need to invoke tools, write a JSON list of tool calls inside <tools>...</tools> tags, e.g.:\n"
            "   <tools>\n"
            "   [\n"
            "     {\"name\": \"write_file\", \"arguments\": {\"filename\": \"app.py\", \"content\": \"print(1)\"}}\n"
            "   ]\n"
            "   </tools>\n"
            "   If no tools are needed, write empty tags: <tools>[]</tools>.\n"
            "Do NOT output raw Pydantic JSON or write outside these tags."
        )
        
        full_user_prompt = user_prompt + instructions
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_user_prompt}
        ]

        # === PASS 1: REASONING (PLAIN TEXT) ===
        raw_response = await self.client.chat(self.worker_type, messages, format_schema=None)
        
        # === PASS 2: PROGRAMMATIC PARSING ===
        envelope = self._parse_raw_response(raw_response)
        
        # === PASS 3: FALLBACK FORMATTING CALL ===
        if not envelope:
            logger.warning(f"Worker '{self.worker_type}' regex parsing failed. Initiating Pass 3 formatting call.")
            envelope = await self._run_fallback_formatting(raw_response)

        # === §R.4: Enforce pre-tool brevity via post-processing ===
        envelope = self._enforce_pretool_brevity(envelope)
        return envelope

    def _parse_raw_response(self, text: str) -> CanonicalEnvelope | None:
        """Extract content from XML-like tags using regex."""
        try:
            think_match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
            response_match = re.search(r"<response>(.*?)</response>", text, re.DOTALL)
            tools_match = re.search(r"<tools>(.*?)</tools>", text, re.DOTALL)
            
            if not response_match:
                return None
                
            content = response_match.group(1).strip()
            
            tool_calls = []
            if tools_match:
                tools_text = tools_match.group(1).strip()
                if tools_text and tools_text != "[]":
                    # Try parsing JSON list
                    try:
                        calls_data = json.loads(tools_text)
                        if isinstance(calls_data, list):
                            for call in calls_data:
                                tool_calls.append(ToolCall(name=call["name"], arguments=call["arguments"]))
                    except Exception:
                        return None
                        
            return CanonicalEnvelope(
                status="success",
                output_type="text" if not tool_calls else "code",
                content=content,
                confidence=0.9,
                tool_calls=tool_calls,
                needs_followup=len(tool_calls) > 0
            )
        except Exception:
            return None

    async def _run_fallback_formatting(self, raw_text: str) -> CanonicalEnvelope:
        """
        §R.15 Pass 3: Cheap formatting LLM query.
        Forces grammar-constrained structure onto the raw reasoning output of Pass 1.
        """
        formatter_prompt = (
            "Take this unstructured reasoning text from a worker and format it precisely into the CanonicalEnvelope JSON schema.\n"
            f"Raw text:\n{raw_text}"
        )
        
        system_prompt = (
            "You are a structured data formatting assistant. Your job is to output ONLY valid JSON matching the schema."
        )
        
        try:
            formatted_json = await self.client.generate(
                worker_type="supervisor", # Use lightweight supervisor for formatting pass
                prompt=formatter_prompt,
                system=system_prompt,
                format_schema=CanonicalEnvelope
            )
            data = json.loads(formatted_json)
            return CanonicalEnvelope(**data)
        except Exception as e:
            logger.critical(f"Pass 3 fallback formatting failed: {e}")
            return CanonicalEnvelope(
                status="error",
                output_type="error",
                content=f"Decoupled parsing failed. Raw response: {raw_text[:200]}...",
                confidence=0.0
            )

    def _enforce_pretool_brevity(self, envelope: CanonicalEnvelope) -> CanonicalEnvelope:
        """
        §R.4: Truncate pre-tool commentary to one sentence, max 150 chars,
        preventing models from writing long preambles before calling tools.
        """
        if envelope.tool_calls and envelope.content.strip():
            # Split by sentence boundary
            sentences = re.split(r'(?<=[.!?])\s+', envelope.content)
            if sentences:
                first_sentence = sentences[0]
                if len(first_sentence) > 150:
                    first_sentence = first_sentence[:147] + "..."
                envelope.content = first_sentence
        return envelope

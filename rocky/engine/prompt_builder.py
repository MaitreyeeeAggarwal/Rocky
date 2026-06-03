import os
import logging
from pathlib import Path
from rocky.config import get_config

logger = logging.getLogger("rocky.prompt_builder")

class PromptBuilder:
    def __init__(self):
        self.config = get_config()
        self.memory_root = Path(self.config.memory.root)
        self.skills_root = Path(self.config.skills.root)

    def _get_constitution(self) -> str:
        path = self.memory_root / "CONSTITUTION.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return "# Rocky Constitution\nNo constitution found."

    def _get_active_skills(self) -> str:
        skills = []
        try:
            if self.skills_root.exists():
                for f in self.skills_root.glob("*.md"):
                    content = f.read_text(encoding="utf-8")
                    skills.append(content[:500])
        except Exception:
            pass
        if skills:
            return "\n\n## Active Skills\n" + "\n---\n".join(skills)
        return ""

    def build_system_prompt(self, worker_type: str, tools: list[str]) -> str:
        """
        §2.5 + §R.17: Strict Two-Tiered Prompt Caching Layout.
        """
        constitution = self._get_constitution()
        skills = self._get_active_skills()
        
        role_prompts = {
            "supervisor": "You are the Supervisor head. Your task is to analyze user intent and route tasks to Coder, Reasoner, or Writer.",
            "brainstorm": "You are the Brainstorm cofounder mode. Pitch ideas, challenge assumptions, perform SWOT analyses, validate markets, and refine good concepts.",
            "architect": "You are the Architect cofounder mode. Finalize system architectures, pick technologies, write detailed specs, plan database schemas (SQL/NoSQL), and write PRDs.",
            "builder": "You are the Builder cofounder mode. Write code, create files, run terminal commands, write tests, debug errors, and deploy the application.",
            "analyst": "You are the Analyst cofounder mode. Read logs and analytics data, spot patterns, debug performance issues, and calculate actionable metrics.",
            "content": "You are the Content cofounder mode. Write scripts, captions, ad copy, content calendars, tweets, and product launch posts.",
            "memory": "You are the Memory cofounder mode. Query preferences, historical decisions, and active environment contexts."
        }
        role = role_prompts.get(worker_type, "You are a specialist cofounder worker.")
        
        tool_specs = ""
        if tools:
            tool_specs = "\n\n## Available Tools\n" + "\n".join([f"- {t}" for t in tools])
            
        system_prompt = (
            f"{constitution}\n"
            f"{skills}\n"
            f"## Worker Role: {worker_type.upper()}\n"
            f"{role}\n"
            f"{tool_specs}"
        )
        return system_prompt

    def build_user_payload(self, task: str, memory_context: str, shared_state_summary: str, session_history: list) -> str:
        """
        === TIER 3: DYNAMIC TAIL ===
        Assembles all turn-by-turn dynamic variables into a single user payload message,
        preventing cache invalidation of the system prompt.
        """
        history_lines = []
        for m in session_history[-10:]:
            try:
                event_type = m.event_type if hasattr(m, "event_type") else m.get("event_type")
                details = m.details if hasattr(m, "details") else m.get("details", "")
                worker = m.worker if hasattr(m, "worker") else m.get("worker")
                
                if event_type == "USER_MESSAGE":
                    history_lines.append(f"USER: {details}")
                elif event_type in ["SUCCESS", "TOOL_CALL", "TOOL_RESULT"] and worker:
                    history_lines.append(f"{worker.upper()}: {details}")
            except Exception:
                pass
        history_text = "\n".join(history_lines)
        payload = (
            f"## Dynamic Context\n"
            f"### Memory Domain Facts:\n{memory_context}\n\n"
            f"### Shared State Coherence:\n{shared_state_summary}\n\n"
            f"### Session History:\n{history_text}\n\n"
            f"### Current Instruction:\n{task}"
        )
        return payload

import logging
from pathlib import Path
from datetime import datetime
from typing import Callable, Any
from rocky.schemas import ToolCall
from rocky.config import get_config

logger = logging.getLogger("rocky.tools")

class ToolRegistry:
    """
    §5.4: Risk Classification and UNDO_LOG Manager.
    Enforces human confirmation gates on IRREVERSIBLE tool actions.
    """
    def __init__(self):
        self.config = get_config()
        self.undo_log_path = Path(self.config.memory.root) / "UNDO_LOG.md"
        self._tools: dict[str, tuple[Callable, str]] = {}
        
        if not self.undo_log_path.exists():
            self.undo_log_path.write_text("# Rocky Action Undo Log\n<!-- Log of reversible actions for undo recovery -->\n\n", encoding="utf-8")

        from rocky.tools.file_ops import write_file, read_file
        from rocky.tools.shell import run_command
        from rocky.tools.web import web_fetch
        from rocky.tools.code_exec import execute_python

        self.register_tool("write_file", write_file, "reversible")
        self.register_tool("read_file", read_file, "safe")
        self.register_tool("run_command", run_command, "irreversible")
        self.register_tool("web_fetch", web_fetch, "safe")
        self.register_tool("execute_python", execute_python, "reversible")

    def register_tool(self, name: str, func: Callable, risk_level: str):
        """Registers a tool function with its safety category."""
        if risk_level not in ["safe", "reversible", "irreversible"]:
            raise ValueError(f"Invalid safety risk level: {risk_level}")
        self._tools[name] = (func, risk_level)

    def get_risk_level(self, tool_name: str) -> str:
        """Determines the safety category of a tool based on registration or config overrides."""
        registered = self._tools.get(tool_name)
        if registered:
            return registered[1]
            
        levels = self.config.safety.risk_levels
        if tool_name in levels.get("safe", []):
            return "safe"
        elif tool_name in levels.get("reversible", []):
            return "reversible"
        return "irreversible"

    async def execute(self, call: ToolCall) -> Any:
        """Executes a tool call respecting risk gates."""
        name = call.name
        args = call.arguments
        
        registered = self._tools.get(name)
        if not registered:
            raise KeyError(f"Tool '{name}' is not registered.")
            
        func, registered_risk = registered
        risk_level = self.get_risk_level(name)
        
        if risk_level == "irreversible":
            print("\n" + "!"*80)
            print(f"WARNING: Rocky wants to execute an IRREVERSIBLE action: '{name}'")
            print(f"Arguments: {args}")
            print("!"*80)
            confirm = input("Do you authorize this execution? (y/N): ").strip().lower()
            if confirm not in ["y", "yes"]:
                print("[-] Action denied by user.")
                raise PermissionError(f"User denied execution of irreversible tool '{name}'.")
            print("[+] Action authorized.")

        result = await func(**args)

        if risk_level == "reversible":
            timestamp = datetime.now().isoformat()
            undo_line = f"- [{timestamp}] Reversible Tool: '{name}' called with arguments {args}.\n"
            
            if "write" in name or "edit" in name:
                filename = args.get("filename") or args.get("path")
                if filename:
                    undo_line += f"  Undo Hint: To restore, checkout this file via Git: 'git checkout -- {filename}'\n"
                    
            with open(self.undo_log_path, "a", encoding="utf-8") as f:
                f.write(undo_line)
                
        return result

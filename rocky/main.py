import sys
import os
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from rich.console import Console
from rich.markdown import Markdown

from rocky.config import get_config, detect_hardware_profile, is_wsl_environment
from rocky.memory.constitution import ConstitutionVerifier
from rocky.memory.store import MemoryStore
from rocky.memory.session import SessionManager
from rocky.memory.shared_state import SharedState
from rocky.engine.llm_client import LLMClient
from rocky.engine.model_manager import ModelManager
from rocky.engine.thermal_monitor import ThermalMonitor
from rocky.engine.circuit_breaker import CircuitBreaker
from rocky.engine.prompt_builder import PromptBuilder
from rocky.supervisor.dispatcher import Dispatcher
from rocky.skills.manager import SkillManager
from rocky.skills.executor import SkillExecutor
from rocky.skills.regression import SkillRegression
from rocky.hermes.reflector import HermesReflector
from rocky.hermes.learner import HermesLearner
from rocky.hermes.git_sync import GitSync
from rocky.schemas import TraceEvent, CanonicalEnvelope
from rocky.tools.registry import ToolRegistry

from rocky.workers.coder import CoderWorker
from rocky.workers.reasoner import ReasonerWorker
from rocky.workers.writer import WriterWorker

console = Console()
logger = logging.getLogger("rocky.main")

class RockyREPL:
    def __init__(self):
        self.config = get_config()
        self.client = LLMClient()
        self.prompt_builder = PromptBuilder()
        
        self.store = MemoryStore()
        self.session = SessionManager()
        self.shared_state = SharedState()
        self.verifier = ConstitutionVerifier()
        self.dispatcher = Dispatcher()
        self.skills = SkillManager()
        self.git = GitSync()
        
        self.workers = {
            "coder": CoderWorker(self.client, self.prompt_builder),
            "reasoner": ReasonerWorker(self.client, self.prompt_builder),
            "writer": WriterWorker(self.client, self.prompt_builder)
        }
        
        self.regression = SkillRegression(self.skills, lambda name: self.workers[name])
        self.learner = HermesLearner(self.store, self.skills, self.regression)
        self.reflector = HermesReflector(self.client)
        self.executor = SkillExecutor(self.session)
        self.circuit_breaker = CircuitBreaker()
        self.thermal = ThermalMonitor()
        self.tool_registry = ToolRegistry()
        self._override_mode = "auto"

    async def startup(self, force_start: bool = False, relock: bool = False):
        console.print("[bold green]Starting Rocky Multi-Agent System...[/bold green]")
        
        self.verifier.verify_or_block(force_start, relock)
        await self.git.init_repo()
        await self.store.recover_interrupted_compaction()
        await self.thermal.start()
        
        warm_sum = self.session.check_resumption()
        if warm_sum:
            console.print(f"\n[yellow]WARM SESSION DETECTED from {warm_sum.created_from_hot.strftime('%Y-%m-%d %H:%M:%S')}[/yellow]")
            console.print(f"Goal: {warm_sum.original_goal}")
            ans = input("Would you like to resume this session context? (Y/n): ").strip().lower()
            if ans in ["", "y", "yes"]:
                await self.shared_state.add("active_project_context", f"Resumed Goal: {warm_sum.original_goal}. Critical Decisions: {warm_sum.critical_decisions}")
                console.print("[+] Context injected.")
                
        console.print("\n[bold]CAPABILITY CEILING DISCLOSURE:[/bold]")
        for opt in self.config.capability_ceiling.optimized_for:
            console.print(f"  [green]+[/green] Mapped: {opt}")
        for nopt in self.config.capability_ceiling.not_optimized_for:
            console.print(f"  [red]-[/red] Ceiling: {nopt}")
        console.print("="*60 + "\n")

    async def run(self):
        try:
            while True:
                user_input = input("rocky> ").strip()
                if not user_input:
                    continue
                
                if user_input.startswith("/"):
                    if await self._handle_command(user_input):
                        break
                    continue
                
                self.session.log_trace_event(TraceEvent(
                    event_type="USER_MESSAGE",
                    details=user_input
                ))
                
                intent_info = self.dispatcher.classify(user_input)
                console.print(f"[*] Routed via [bold blue]{intent_info.routing_tier}[/bold blue] -> worker: [bold yellow]{intent_info.intent}[/bold yellow]")
                
                matched_skill = None
                for skill in self.skills.list_active_skills():
                    if skill.trigger in user_input.lower():
                        matched_skill = skill
                        break
                
                await self.thermal.check_and_pace()
                
                intent = intent_info.intent
                
                # Check for manual override mode
                if self._override_mode != "auto":
                    intent = self._override_mode
                    console.print(f"[*] Manual override active -> mode: [bold yellow]{intent}[/bold yellow]")
                
                if intent == "memory":
                    facts = self.store.read_domain("user")
                    console.print(f"[*] User Memory Lookup:\n{facts}")
                    self.thermal.mark_idle()
                    continue
                elif intent == "skill" or matched_skill:
                    skill = matched_skill or self.skills.list_active_skills()[0]
                    
                    async def execute_skill(w_type: str):
                        w = self.workers[w_type]
                        return await self.executor.execute(skill, w, user_input, self.shared_state, self.session.get_trace_events())
                        
                    envelope = await self.circuit_breaker.call(skill.worker, execute_skill)
                else:
                    mapping = {
                        "brainstorm": "reasoner",
                        "architect": "reasoner",
                        "builder": "coder",
                        "analyst": "reasoner",
                        "content": "writer"
                    }
                    worker_type = mapping.get(intent, "reasoner")
                    
                    async def execute_worker(w_type: str):
                        w = self.workers[w_type]
                        return await w.execute(user_input, self.shared_state, self.session.get_trace_events(), memory_context="", role=intent)
                        
                    envelope = await self.circuit_breaker.call(worker_type, execute_worker)
                
                self.thermal.mark_idle()
                if envelope.status == "success":
                    console.print(Markdown(envelope.content))
                    for call in envelope.tool_calls:
                        console.print(f"[bold cyan]Executing tool: {call.name} with {call.arguments}[/bold cyan]")
                        try:
                            result = await self.tool_registry.execute(call)
                            console.print(f"[green]Result:[/green] {result}")
                            self.session.log_trace_event(TraceEvent(
                                event_type="TOOL_RESULT",
                                details=f"Tool '{call.name}' returned: {result}"
                            ))
                        except Exception as e:
                            console.print(f"[bold red]Tool Execution Failed:[/bold red] {e}")
                            self.session.log_trace_event(TraceEvent(
                                event_type="ERROR",
                                details=f"Tool '{call.name}' failed: {e}"
                            ))
                else:
                    console.print(f"[bold red]Execution Error:[/bold red] {envelope.content}")
                    
        except (KeyboardInterrupt, EOFError):
            console.print("\n[*] Exiting REPL...")
        finally:
            await self._cleanup()

    async def _handle_command(self, cmd: str) -> bool:
        parts = cmd.split()
        command = parts[0].lower()
        
        if command == "/end-session":
            await self._end_session()
            return True
        elif command == "/status":
            console.print(f"API Provider: {self.config.engine.provider}")
            console.print(f"Thermal State: {self.thermal._last_temp}°C (Threshold: {self.thermal._threshold}°C)")
            console.print(f"Active Skills Count: {len(self.skills.list_active_skills())}")
            console.print(f"Staged Skills Count: {len(self.skills.list_staging_skills())}")
        elif command == "/memory":
            for domain in self.store.DOMAINS:
                console.print(f"Domain Facts: {domain.upper()}")
                console.print(self.store.read_domain(domain))
                console.print("-"*40)
        elif command == "/skills":
            console.print("Active Skills:")
            for s in self.skills.list_active_skills():
                console.print(f"  - {s.name} (trigger: {s.trigger})")
            console.print("Staging Skills:")
            for s in self.skills.list_staging_skills():
                console.print(f"  - {s.name} (UNVALIDATED)")
        elif command == "/prune":
            await self._prune_entropy()
        elif command == "/mode":
            if len(parts) > 1:
                mode = parts[1].lower()
                allowed_modes = ["auto", "brainstorm", "architect", "builder", "analyst", "content", "memory"]
                if mode in allowed_modes:
                    self._override_mode = mode
                    console.print(f"[+] Co-founder mode set to: [bold yellow]{mode}[/bold yellow]")
                else:
                    console.print(f"[-] Invalid mode. Allowed: {allowed_modes}")
            else:
                console.print(f"Current Co-founder mode: [bold yellow]{self._override_mode}[/bold yellow]")
                console.print("To change mode, run: /mode <auto|brainstorm|architect|builder|analyst|content|memory>")
        elif command == "/undo":
            console.print(self.store.root.joinpath("UNDO_LOG.md").read_text(encoding="utf-8"))
        elif command == "/help":
            console.print("Commands: /end-session, /status, /memory, /skills, /prune, /undo, /help")
        else:
            console.print(f"Unknown command: {command}")
        return False

    async def _prune_entropy(self):
        console.print("[bold yellow]Running Entropy Budget Review...[/bold yellow]")
        active_skills = self.skills.list_active_skills()
        console.print(f"Active Skills: {len(active_skills)} / {self.config.skills.max_active_skills}")
        
        rules_count = len(self.dispatcher.TIER1_PATTERNS)
        console.print(f"Dispatch Rules: {rules_count} / {self.config.skills.max_dispatch_rules}")
        
        for domain, filename in self.store.DOMAINS.items():
            path = self.store.root / filename
            lines = 0
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    lines = sum(1 for _ in f)
            console.print(f"Memory Domain '{domain}' line count: {lines} / {self.config.memory.max_lines_per_file}")
            
        if active_skills:
            ans = input("Would you like to archive any active skills? (y/N): ").strip().lower()
            if ans in ["y", "yes"]:
                for idx, skill in enumerate(active_skills, 1):
                    console.print(f"  [{idx}] {skill.name} (trigger: '{skill.trigger}')")
                selection = input("Select skill number to archive: ").strip()
                try:
                    sel_idx = int(selection) - 1
                    if 0 <= sel_idx < len(active_skills):
                        target = active_skills[sel_idx]
                        archive_path = self.skills.archive_dir / Path(target.path).name
                        import shutil
                        shutil.move(target.path, archive_path)
                        console.print(f"[+] Skill '{target.name}' moved to archive.")
                    else:
                        console.print("[-] Invalid selection.")
                except ValueError:
                    console.print("[-] Invalid input.")

    async def _end_session(self):
        console.print("[bold yellow]Ending Session. Running Hermes Loop...[/bold yellow]")
        
        traces = self.session.get_trace_events()
        reflection = await self.reflector.reflect(traces)
        
        if reflection.learning_status == "LEARNED":
            await self.learner.process(reflection, self.session)
            
            for domain in self.store.DOMAINS:
                if self.store.check_compaction_needed(domain):
                    console.print(f"[*] Compacting domain memory '{domain}'...")
                    await self.store.compact(domain, self.client)
                    
        await self.git.auto_commit(reflection.learning_status)
        console.print("[bold green]Session ended cleanly and changes committed.[/bold green]")

    async def _cleanup(self):
        await self.thermal.stop()

def cli():
    import argparse
    parser = argparse.ArgumentParser(description="Rocky Multi-Agent CLI")
    parser.add_argument("--force-start", action="store_true", help="Bypass constitution SHA lock check")
    parser.add_argument("--relock", action="store_true", help="Update constitution SHA lockfile to current version")
    args = parser.parse_args()
    
    repl = RockyREPL()
    asyncio.run(repl.startup(force_start=args.force_start, relock=args.relock))
    asyncio.run(repl.run())

if __name__ == "__main__":
    cli()

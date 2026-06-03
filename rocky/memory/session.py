import json
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from rocky.config import get_config
from rocky.schemas import WarmSummary, TraceEvent

logger = logging.getLogger("rocky.session")

class SessionManager:
    """
    §2.3 + §R.12: Three-Tier Context Persistence & Warm Resumption.
    """
    def __init__(self):
        self.config = get_config()
        self.root = Path(self.config.memory.root)
        
        self.hot_path = self.root / "session_hot_context.md"
        self.warm_dir = self.root / "session_warm"
        self.cold_dir = self.root / "session_cold"
        
        self.warm_dir.mkdir(parents=True, exist_ok=True)
        self.cold_dir.mkdir(parents=True, exist_ok=True)
        
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.trace_path = self.root / f"trace_{self.session_id}.jsonl"

    def log_trace_event(self, event: TraceEvent):
        """Append a structured JSON trace event to the session trace file."""
        with open(self.trace_path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def get_trace_events(self) -> list[TraceEvent]:
        events = []
        if not self.trace_path.exists():
            return events
        with open(self.trace_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    events.append(TraceEvent.model_validate_json(line))
        return events

    def check_resumption(self) -> WarmSummary | None:
        """
        Scan session_warm/ for any summaries within 7 days.
        Returns the most recent WarmSummary if found.
        """
        candidates = list(self.warm_dir.glob("*.json"))
        if not candidates:
            return None
            
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        for p in candidates:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                summary = WarmSummary(**data)
                
                created_time = summary.created_from_hot
                if datetime.now() - created_time < timedelta(days=self.config.memory.warm_ttl_days):
                    return summary
            except Exception as e:
                logger.error(f"Failed to parse warm summary {p.name}: {e}")
                
        return None

    def transition_hot_to_warm(self, original_goal: str, constraints: list[str], decisions: list[str], variables: dict[str, str], files_modified: list[str], summary_text: str):
        """
        §R.12: Transmit hot context into WarmSummary schema.
        Writes to session_warm/session_id.json
        """
        summary = WarmSummary(
            session_id=self.session_id,
            original_goal=original_goal,
            key_constraints=constraints,
            critical_decisions=decisions,
            active_variables=variables,
            files_modified=files_modified,
            unresolved_issues=[],
            summary_text=summary_text,
            created_from_hot=datetime.now()
        )
        
        dest_path = self.warm_dir / f"{self.session_id}.json"
        dest_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        logger.info(f"Transitioned session {self.session_id} to WARM storage.")

    def run_ttl_transitions(self):
        """
        Transitions files exceeding session TTLs:
        - session_warm files > 7 days → moved to session_cold
        """
        warm_ttl = timedelta(days=self.config.memory.warm_ttl_days)
        for p in self.warm_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                summary = WarmSummary(**data)
                created_time = summary.created_from_hot
                
                if datetime.now() - created_time >= warm_ttl:
                    logger.info(f"WARM TTL expired for {p.name}. Moving to session_cold.")
                    cold_path = self.cold_dir / p.name
                    os.replace(p, cold_path)
            except Exception as e:
                logger.error(f"TTL transition check failed for {p.name}: {e}")

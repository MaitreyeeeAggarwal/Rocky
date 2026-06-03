import re
import json
import logging
from pathlib import Path
from typing import Literal
from pydantic import BaseModel
from datetime import datetime
from rocky.config import get_config
from rocky.schemas import IntentClassification

logger = logging.getLogger("rocky.dispatcher")

class WorkerRoute(BaseModel):
    worker: Literal["brainstorm", "architect", "builder", "analyst", "content", "memory", "supervisor"]
    tools: list[str]

class Dispatcher:
    # §R.1: Strict T1 Regex priorities
    TIER1_PATTERNS: list[tuple[int, re.Pattern, WorkerRoute]] = [
        (100, re.compile(r'\b(error:|traceback|exception)\b', re.I),
              WorkerRoute(worker="builder", tools=["file_ops", "shell", "code_exec"])),
        (90,  re.compile(r'\b(def |class |import |from .+ import|function )\b'),
              WorkerRoute(worker="builder", tools=["file_ops", "shell", "code_exec"])),
        (80,  re.compile(r'\b(bug|fix|debug)\b', re.I),
              WorkerRoute(worker="builder", tools=["file_ops", "shell", "code_exec"])),
        (70,  re.compile(r'\.(py|js|ts|go|rs|java|cpp|c|rb|sh|sql|html|css)\b'),
              WorkerRoute(worker="builder", tools=["file_ops", "code_exec"])),
        (60,  re.compile(r'\b(run|execute|deploy|build|compile|install)\b', re.I),
              WorkerRoute(worker="builder", tools=["shell", "file_ops"])),
    ]

    # §R.1: Tier 2 keyword sets
    TIER2_CLUSTERS: dict[frozenset[str], WorkerRoute] = {
        frozenset({"brainstorm", "pitch", "idea", "market", "swot", "concept", "validate"}):
            WorkerRoute(worker="brainstorm", tools=["file_ops"]),
        frozenset({"architect", "schema", "prd", "spec", "design", "tech stack", "database"}):
            WorkerRoute(worker="architect", tools=["file_ops"]),
        frozenset({"build", "code", "develop", "implement", "create file", "write code"}):
            WorkerRoute(worker="builder", tools=["file_ops", "shell", "code_exec"]),
        frozenset({"analyze", "analytics", "pattern", "metric", "log", "debug"}):
            WorkerRoute(worker="analyst", tools=["file_ops", "shell"]),
        frozenset({"content", "write script", "tweet", "post", "blog", "calendar", "caption"}):
            WorkerRoute(worker="content", tools=["file_ops"]),
        frozenset({"memory", "remember", "recall", "forget", "preference", "fact"}):
            WorkerRoute(worker="memory", tools=["memory"]),
    }

    def __init__(self):
        self.config = get_config()
        self.version_file = Path(self.config.skills.dispatch_version_file)
        self.version_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_version()

    def _load_version(self):
        if self.version_file.exists():
            try:
                data = json.loads(self.version_file.read_text(encoding="utf-8"))
                self.version = data.get("version", 1)
            except Exception:
                self.version = 1
        else:
            self.version = 1
            self._save_version([])

    def _save_version(self, log_entries: list):
        data = {
            "version": self.version,
            "changelog": log_entries
        }
        self.version_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def classify(self, user_input: str) -> IntentClassification:
        """
        §R.1: Strict priority dispatcher (T1 > T2 > T3).
        Matches regex first, then cluster keywords, then LLM.
        """
        matches = []
        for weight, pattern, route in self.TIER1_PATTERNS:
            if pattern.search(user_input):
                matches.append((weight, pattern, route))
                
        if matches:
            matches.sort(key=lambda x: x[0], reverse=True)
            weight, pattern, route = matches[0]
            logger.info(f"Dispatcher: T1 match. Winning pattern: '{pattern.pattern}' (weight {weight}) -> {route.worker}")
            return IntentClassification(
                intent=route.worker if route.worker != "supervisor" else "memory",
                routing_tier="T1_exact",
                winning_pattern=pattern.pattern,
                confidence=1.0,
                sub_task=user_input,
                required_tools=route.tools
            )

        words = set(re.findall(r'\b\w+\b', user_input.lower()))
        max_intersection = 0
        winning_cluster = None
        winning_route = None
        
        for cluster, route in self.TIER2_CLUSTERS.items():
            intersection = len(words.intersection(cluster))
            if intersection > max_intersection:
                max_intersection = intersection
                winning_cluster = cluster
                winning_route = route
                
        if winning_route and max_intersection > 0:
            logger.info(f"Dispatcher: T2 match. Winning cluster: {list(winning_cluster)} (score {max_intersection}) -> {winning_route.worker}")
            return IntentClassification(
                intent=winning_route.worker if winning_route.worker != "supervisor" else "memory",
                routing_tier="T2_keyword",
                winning_pattern=";".join(winning_cluster),
                confidence=0.8,
                sub_task=user_input,
                required_tools=winning_route.tools
            )

        logger.info("Dispatcher: T1 & T2 missed. Falling back to T3 (Architect worker default).")
        return IntentClassification(
            intent="architect",
            routing_tier="T3_llm",
            confidence=0.5,
            sub_task=user_input,
            required_tools=["file_ops"]
        )

    def add_rule(self, pattern_str: str, worker: str, tools: list[str], weight: int = 50):
        """
        §R.2: Versioned AUTOLEARN matrix expansion.
        """
        if len(self.TIER1_PATTERNS) >= self.config.skills.max_dispatch_rules:
            logger.warning("DISPATCH_MATRIX limit reached. Blocking AUTOLEARN rule addition.")
            return
            
        try:
            pattern = re.compile(pattern_str, re.I)
            route = WorkerRoute(worker=worker, tools=tools)
            
            self.TIER1_PATTERNS.append((weight, pattern, route))
            self.version += 1
            
            changelog_entry = {
                "version": self.version,
                "timestamp": datetime.now().isoformat(),
                "action": "add_rule",
                "pattern": pattern_str,
                "worker": worker,
                "tools": tools,
                "weight": weight
            }
            
            existing_log = []
            if self.version_file.exists():
                try:
                    existing_log = json.loads(self.version_file.read_text(encoding="utf-8")).get("changelog", [])
                except Exception:
                    pass
            existing_log.append(changelog_entry)
            self._save_version(existing_log)
            
            logger.info(f"DISPATCH_MATRIX expanded to version {self.version}. Added: {pattern_str} -> {worker}")
        except Exception as e:
            logger.error(f"Failed to add dispatch rule '{pattern_str}': {e}")

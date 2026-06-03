from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field

class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any]

class CanonicalEnvelope(BaseModel):
    """Every worker wraps output in this. Models never see raw peer output."""
    status: Literal["success", "partial", "error"]
    output_type: Literal["text", "code", "plan", "data", "error"]
    content: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    next_suggested_action: str | None = None
    tool_calls: list[ToolCall] = []
    needs_followup: bool = False

class ConfidenceSignals(BaseModel):
    """Observable signals for composite confidence score."""
    schema_valid: bool = True
    retries_needed: int = 0
    output_length_in_range: bool = True
    error_keywords_present: bool = False

    @property
    def composite_score(self) -> float:
        """C = 0.4*schema + 0.3*no_retry + 0.2*length + 0.1*no_errors"""
        return (
            0.4 * float(self.schema_valid) +
            0.3 * float(self.retries_needed == 0) +
            0.2 * float(self.output_length_in_range) +
            0.1 * float(not self.error_keywords_present)
        )

class TaskStep(BaseModel):
    step: int
    worker: Literal["coder", "reasoner", "writer", "supervisor"]
    description: str

class IntentClassification(BaseModel):
    intent: Literal["brainstorm", "architect", "builder", "analyst", "content", "memory", "skill", "meta", "unknown"]
    routing_tier: Literal["T1_exact", "T2_keyword", "T3_llm"]
    winning_pattern: str | None = None
    tie_resolution: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    sub_task: str
    required_tools: list[str]
    task_plan: list[TaskStep] = []

class FactEntry(BaseModel):
    key: str
    value: str
    updated: datetime
    previous_value: str | None = None

class OutputValidation(BaseModel):
    validation_type: Literal["file_exists", "output_contains", "output_matches_schema",
                             "file_non_empty", "no_error_strings", "custom"]
    expected: str
    actual: str
    passed: bool
    details: str = ""

class SuccessOutcome(BaseModel):
    goal: str
    terminal_exit_code: int
    output_validation: OutputValidation
    functional_solution: str

class ErrorReport(BaseModel):
    step: str
    error_message: str
    category: str

class SkillCandidate(BaseModel):
    name: str
    task_class: str
    trigger: str
    steps: list[str]
    tools_required: list[str]
    test_input: str
    test_expected_contains: list[str]

class Reflection(BaseModel):
    goals: list[str]
    errors: list[ErrorReport] = []
    successful_outcomes: list[SuccessOutcome] = []
    new_facts: list[FactEntry] = []
    skill_candidates: list[SkillCandidate] = []
    improvements: list[str] = []
    learning_status: Literal["LEARNED", "NONE"]

class CircuitState(BaseModel):
    worker: str
    state: Literal["CLOSED", "OPEN", "HALF_OPEN"]
    failure_count: int = 0
    last_failure: datetime | None = None
    opened_at: datetime | None = None
    recovery_timeout_s: int = 300
    fallback_worker: str | None = None

class RiskAction(BaseModel):
    tool_name: str
    risk_level: Literal["SAFE", "REVERSIBLE", "IRREVERSIBLE"]
    arguments: dict[str, Any]
    undo_command: str | None = None

class TraceEvent(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.now)
    event_type: Literal[
        "TOOL_CALL", "TOOL_RESULT", "ERROR",
        "RETRY", "SUCCESS", "USER_MESSAGE",
        "WORKER_DISPATCH", "MODEL_SWAP",
        "SKILL_INVOCATION",
        "OUTPUT_VALIDATION"
    ]
    worker: str | None = None
    skill_name: str | None = None
    skill_source: Literal["active", "staging", "none"] = "none"
    input_hash: str | None = None
    output_hash: str | None = None
    exit_code: int | None = None
    token_count: int | None = None
    validation: OutputValidation | None = None
    details: str = ""

class ChainContext(BaseModel):
    chain_id: str
    step: int
    total_steps: int
    outer_result: dict[str, Any]
    remaining_fields: list[str]
    accumulated_schema: dict[str, Any]

class WarmSummary(BaseModel):
    session_id: str
    original_goal: str
    key_constraints: list[str]
    critical_decisions: list[str]
    active_variables: dict[str, str]
    files_modified: list[str]
    unresolved_issues: list[str]
    summary_text: str
    created_from_hot: datetime

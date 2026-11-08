from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ContextLevel(str, Enum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class ClarificationOption(BaseModel):
    metric_id: str
    label: str
    description: str
    business_rule_reference: str | None = None


class ClarificationRequest(BaseModel):
    is_ambiguous: bool
    ambiguity_group_id: str | None = None
    question: str
    options: list[ClarificationOption] = Field(default_factory=list)


class RetrievedExampleInfo(BaseModel):
    id: str
    question: str
    sql: str
    similarity_score: float = 0.0
    resolved_metric_id: str | None = None
    origin: str = "curated"


class SelectedTableInfo(BaseModel):
    table_name: str
    schema_name: str
    columns: list[str] = Field(default_factory=list)
    retrieval_reason: str = ""


class SelectedMetricInfo(BaseModel):
    metric_id: str
    name: str
    canonical_sql: str
    base_table: str


class ContextInspectionReport(BaseModel):
    selected_tables: list[SelectedTableInfo] = Field(default_factory=list)
    selected_metrics: list[SelectedMetricInfo] = Field(default_factory=list)
    few_shot_examples: list[RetrievedExampleInfo] = Field(default_factory=list)
    raw_schema_tokens: int = 0
    compressed_context_tokens: int = 0
    token_reduction_percentage: float = 0.0
    latency_ms: float = 0.0


class AssembledContext(BaseModel):
    level: ContextLevel
    system_prompt: str
    schema_ddl: str = ""
    semantic_metrics: str = ""
    few_shot_block: str = ""
    inspection_report: ContextInspectionReport = Field(default_factory=ContextInspectionReport)


class SQLExecutionResult(BaseModel):
    query: str
    success: bool
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float = 0.0
    error_message: str | None = None


class GeneratedSQLResponse(BaseModel):
    raw_sql: str
    sanitized_sql: str
    reasoning: str = ""
    confidence: float = 1.0


class QueryTurnResult(BaseModel):
    question: str
    context_level: ContextLevel
    assembled_context: AssembledContext
    generated_sql: GeneratedSQLResponse
    execution_result: SQLExecutionResult
    correction_attempts: int = 0


class SavedPlaybook(BaseModel):
    id: str
    title: str
    question: str
    sanitized_sql: str
    resolved_metric_id: str | None = None
    used_tables: list[str] = Field(default_factory=list)
    created_at: str = ""

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


class ColumnMetadata(BaseModel):
    name: str
    data_type: str = Field(default="", alias="type")
    description: str = ""
    is_primary_key: bool = False
    is_foreign_key: bool = False
    references: str | None = None
    allowed_values: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class TableMetadata(BaseModel):
    name: str
    schema_name: str = "marts"
    description: str = ""
    columns: list[ColumnMetadata] = Field(default_factory=list)
    primary_key: list[str] = Field(default_factory=list)


class MetricMetadata(BaseModel):
    id: str
    name: str
    description: str
    canonical_sql: str
    base_table: str
    filters_required: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)


class AmbiguityGroup(BaseModel):
    id: str
    name: str
    trigger_terms: list[str] = Field(default_factory=list)
    description: str = ""
    candidate_metrics: list[str] = Field(default_factory=list)


class BusinessRule(BaseModel):
    id: str
    name: str
    description: str
    rule_sql_condition: str | None = None


class JoinRelationship(BaseModel):
    from_table: str
    to_table: str
    join_type: str = "many_to_one"
    on_clause: str
    description: str = ""


class ForbiddenJoin(BaseModel):
    from_table: str
    to_table: str
    on_condition: str | None = None
    reason: str


class FewShotExample(BaseModel):
    id: str
    question: str
    sql: str
    resolved_metric_id: str | None = None
    tables_used: list[str] = Field(default_factory=list)
    explanation: str = ""


class MetadataCatalog(BaseModel):
    tables: list[TableMetadata] = Field(default_factory=list)
    metrics: list[MetricMetadata] = Field(default_factory=list)
    ambiguity_groups: list[AmbiguityGroup] = Field(default_factory=list)
    business_rules: list[BusinessRule] = Field(default_factory=list)
    allowed_joins: list[JoinRelationship] = Field(default_factory=list)
    forbidden_joins: list[ForbiddenJoin] = Field(default_factory=list)
    few_shot_examples: list[FewShotExample] = Field(default_factory=list)

    def get_table(self, table_name: str) -> TableMetadata | None:
        target = table_name.lower().strip()
        for t in self.tables:
            if t.name.lower() == target:
                return t
            if "." in t.name and t.name.lower().split(".", 1)[1] == target:
                return t
            if "." in target and target.split(".", 1)[1] == t.name.lower():
                return t
        return None

    def get_metric(self, metric_id: str) -> MetricMetadata | None:
        target = metric_id.lower().strip()
        for m in self.metrics:
            if m.id.lower() == target:
                return m
        return None

    def find_ambiguity_group(self, term: str) -> AmbiguityGroup | None:
        target = term.lower().strip()
        if not target:
            return None
        for g in self.ambiguity_groups:
            if g.id.lower() == target or g.name.lower() == target:
                return g
            for trigger in g.trigger_terms:
                trigger_clean = trigger.lower().strip()
                if not trigger_clean:
                    continue
                if trigger_clean in target:
                    return g
                if len(target) >= 3 and target in trigger_clean:
                    return g
        return None


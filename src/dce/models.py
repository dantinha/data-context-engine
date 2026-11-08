from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


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
    needs_clarification: bool = False
    is_ambiguous: bool = False
    ambiguity_group_id: str | None = None
    question: str
    message: str = ""
    options: list[ClarificationOption] = Field(default_factory=list)
    resolved_metric_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _sync_ambiguity(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "is_ambiguous" in data and "needs_clarification" not in data:
                data["needs_clarification"] = data["is_ambiguous"]
            elif "needs_clarification" in data and "is_ambiguous" not in data:
                data["is_ambiguous"] = data["needs_clarification"]
        return data


class RetrievedExampleInfo(BaseModel):
    id: str
    question: str
    sql: str
    similarity_score: float = 0.0
    resolved_metric_id: str | None = None
    origin: str = "curated"
    source: str = "static_few_shot"

    @model_validator(mode="before")
    @classmethod
    def _sync_source_origin(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "source" in data and "origin" not in data:
                if data["source"] == "saved_playbook":
                    data["origin"] = "saved_playbook"
                elif data["source"] == "static_few_shot":
                    data["origin"] = "curated"
                else:
                    data["origin"] = data["source"]
            elif "origin" in data and "source" not in data:
                if data["origin"] == "saved_playbook":
                    data["source"] = "saved_playbook"
                elif data["origin"] == "curated":
                    data["source"] = "static_few_shot"
                else:
                    data["source"] = data["origin"]
            elif "origin" in data and "source" in data:
                if data["origin"] == "saved_playbook" and data.get("source") != "saved_playbook":
                    data["source"] = "saved_playbook"
                elif data["source"] == "saved_playbook" and data.get("origin") != "saved_playbook":
                    data["origin"] = "saved_playbook"
        return data


class SelectedTableInfo(BaseModel):
    table_name: str
    schema_name: str = "marts"
    selection_type: str = "direct_match"  # "direct_match" | "graph_bridge" | "baseline_dump"
    reason: str = ""
    retrieval_reason: str = ""
    relevance_score: float = 1.0
    columns_included: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _sync_table_info(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "columns" in data and "columns_included" not in data:
                data["columns_included"] = data["columns"]
            elif "columns_included" in data and "columns" not in data:
                data["columns"] = data["columns_included"]
            if "reason" in data and "retrieval_reason" not in data:
                data["retrieval_reason"] = data["reason"]
            elif "retrieval_reason" in data and "reason" not in data:
                data["reason"] = data["retrieval_reason"]
        return data


class SelectedMetricInfo(BaseModel):
    metric_id: str
    name: str
    canonical_sql: str
    base_table: str
    description: str = ""
    filters_required: list[str] = Field(default_factory=list)
    was_clarified_by_user: bool = False


class RetrievalBundle(BaseModel):
    selected_tables: list[SelectedTableInfo] = Field(default_factory=list)
    selected_metrics: list[SelectedMetricInfo] = Field(default_factory=list)
    few_shot_examples: list[RetrievedExampleInfo] = Field(default_factory=list)
    resolved_metric_id: str | None = None

    @property
    def retrieved_examples(self) -> list[RetrievedExampleInfo]:
        return self.few_shot_examples

    @model_validator(mode="before")
    @classmethod
    def _sync_retrieved_examples(cls, data: Any) -> Any:
        if isinstance(data, dict) and "retrieved_examples" in data:
            if "few_shot_examples" not in data:
                data["few_shot_examples"] = data["retrieved_examples"]
            del data["retrieved_examples"]
        return data


class ContextInspectionReport(BaseModel):
    level: ContextLevel = ContextLevel.L4
    token_budget: int = 2500
    raw_full_schema_tokens: int = 0
    raw_schema_tokens: int = 0
    assembled_context_tokens: int = 0
    compressed_context_tokens: int = 0
    token_savings_pct: float = 0.0
    token_reduction_percentage: float = 0.0
    prefix_cacheable_tokens: int = 0
    prefix_cacheable_pct: float = 0.0
    selected_tables: list[SelectedTableInfo] = Field(default_factory=list)
    selected_metrics: list[SelectedMetricInfo] = Field(default_factory=list)
    few_shot_examples: list[RetrievedExampleInfo] = Field(default_factory=list)
    latency_ms: float = 0.0

    @model_validator(mode="before")
    @classmethod
    def _sync_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # raw_full_schema_tokens <-> raw_schema_tokens
            if "raw_full_schema_tokens" in data and "raw_schema_tokens" not in data:
                data["raw_schema_tokens"] = data["raw_full_schema_tokens"]
            elif "raw_schema_tokens" in data and "raw_full_schema_tokens" not in data:
                data["raw_full_schema_tokens"] = data["raw_schema_tokens"]

            # assembled_context_tokens <-> compressed_context_tokens
            if "assembled_context_tokens" in data and "compressed_context_tokens" not in data:
                data["compressed_context_tokens"] = data["assembled_context_tokens"]
            elif "compressed_context_tokens" in data and "assembled_context_tokens" not in data:
                data["assembled_context_tokens"] = data["compressed_context_tokens"]

            # token_savings_pct <-> token_reduction_percentage
            if "token_savings_pct" in data and "token_reduction_percentage" not in data:
                data["token_reduction_percentage"] = data["token_savings_pct"]
            elif "token_reduction_percentage" in data and "token_savings_pct" not in data:
                data["token_savings_pct"] = data["token_reduction_percentage"]
        return data


class AssembledContext(BaseModel):
    level: ContextLevel
    system_prompt: str = ""
    static_prefix: str = ""
    dynamic_suffix: str = ""
    full_prompt: str = ""
    schema_ddl: str = ""
    semantic_metrics: str = ""
    few_shot_block: str = ""
    inspection: ContextInspectionReport = Field(default_factory=ContextInspectionReport)
    inspection_report: ContextInspectionReport = Field(default_factory=ContextInspectionReport)

    @model_validator(mode="before")
    @classmethod
    def _sync_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # inspection <-> inspection_report
            if "inspection" in data and "inspection_report" not in data:
                data["inspection_report"] = data["inspection"]
            elif "inspection_report" in data and "inspection" not in data:
                data["inspection"] = data["inspection_report"]

            # static_prefix <-> system_prompt
            if "static_prefix" in data and not data.get("system_prompt"):
                data["system_prompt"] = data["static_prefix"]
            elif "system_prompt" in data and not data.get("static_prefix"):
                data["static_prefix"] = data["system_prompt"]

            # full_prompt synthesis if missing
            if not data.get("full_prompt") and (data.get("static_prefix") or data.get("dynamic_suffix")):
                p = f"{data.get('static_prefix', '')}\n\n{data.get('dynamic_suffix', '')}".strip()
                data["full_prompt"] = p
        return data


class SQLExecutionResult(BaseModel):
    query: str
    success: bool
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: float = 0.0
    error_message: str | None = None
    security_violation: bool = False
    sql_executed: str | None = None
    tables_referenced: list[str] = Field(default_factory=list)
    limit_applied: int | None = None
    governance_warnings: list[str] = Field(default_factory=list)


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
    sql_query: str = ""
    sanitized_sql: str = ""
    resolved_metric_id: str | None = None
    tables_used: list[str] = Field(default_factory=list)
    used_tables: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: str = ""
    verified: bool = True

    @model_validator(mode="before")
    @classmethod
    def _sync_playbook_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # sql_query <-> sanitized_sql
            if data.get("sql_query") and not data.get("sanitized_sql"):
                data["sanitized_sql"] = data["sql_query"]
            elif data.get("sanitized_sql") and not data.get("sql_query"):
                data["sql_query"] = data["sanitized_sql"]

            # tables_used <-> used_tables
            if data.get("tables_used") and not data.get("used_tables"):
                data["used_tables"] = data["tables_used"]
            elif data.get("used_tables") and not data.get("tables_used"):
                data["tables_used"] = data["used_tables"]
        return data


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
    origin: str = "curated"
    source: str = "static_few_shot"

    @model_validator(mode="before")
    @classmethod
    def _sync_source_origin(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "source" in data and "origin" not in data:
                if data["source"] == "saved_playbook":
                    data["origin"] = "saved_playbook"
                elif data["source"] == "static_few_shot":
                    data["origin"] = "curated"
                else:
                    data["origin"] = data["source"]
            elif "origin" in data and "source" not in data:
                if data["origin"] == "saved_playbook":
                    data["source"] = "saved_playbook"
                elif data["origin"] == "curated":
                    data["source"] = "static_few_shot"
                else:
                    data["source"] = data["origin"]
            elif "origin" in data and "source" in data:
                if data["origin"] == "saved_playbook" and data.get("source") != "saved_playbook":
                    data["source"] = "saved_playbook"
                elif data["source"] == "saved_playbook" and data.get("origin") != "saved_playbook":
                    data["origin"] = "saved_playbook"
        return data


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



class GoldQuestion(BaseModel):
    id: str
    question: str
    difficulty: str
    trap_tags: list[str] = Field(default_factory=list)
    resolved_metric_id: str | None = None
    gold_sql: str


class LevelBenchmarkResult(BaseModel):
    level: ContextLevel
    single_shot_accuracy: float = 0.0
    corrected_accuracy: float = 0.0
    avg_tokens: float = 0.0
    token_savings_pct: float = 0.0
    total_questions: int = 30
    correct_single_shot: int = 0
    correct_with_correction: int = 0
    failed_questions: list[str] = Field(default_factory=list)
    details: list[dict[str, Any]] = Field(default_factory=list)


class BenchmarkSummary(BaseModel):
    results: list[LevelBenchmarkResult] = Field(default_factory=list)
    generated_at: str = ""
    execution_mode: str = "replay"

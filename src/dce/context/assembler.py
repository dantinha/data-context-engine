"""ContextAssembler supporting L0-L4 context generation, DDL compression, prefix caching, and inspection reports."""

import time
from pathlib import Path

import duckdb

from dce.context.retriever import HybridRetriever
from dce.models import (
    AssembledContext,
    ContextInspectionReport,
    ContextLevel,
    FewShotExample,
    MetadataCatalog,
    MetricMetadata,
    RetrievedExampleInfo,
    SelectedMetricInfo,
    SelectedTableInfo,
    TableMetadata,
)


def estimate_tokens(text: str) -> int:
    """Fast rule-of-thumb token estimator: max(1, len(text) // 4)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _first_sentence(text: str) -> str:
    """Extracts first sentence from text for compact DDL summaries."""
    if not text:
        return ""
    cleaned = text.strip()
    return cleaned.split(".")[0].strip()


# Predefined schema definitions for raw and staging tables when DuckDB file is not present
FALLBACK_SCHEMAS: dict[str, list[tuple[str, str, str]]] = {
    "raw.olist_orders_dataset": [
        ("order_id", "VARCHAR", "Primary transactional key for order"),
        ("customer_id", "VARCHAR", "Transactional customer key"),
        ("order_status", "VARCHAR", "Order fulfillment status"),
        ("order_purchase_timestamp", "TIMESTAMP", "Timestamp of order purchase"),
        ("order_approved_at", "TIMESTAMP", "Payment approval timestamp"),
        ("order_delivered_carrier_date", "TIMESTAMP", "Carrier handoff timestamp"),
        ("order_delivered_customer_date", "TIMESTAMP", "Customer delivery timestamp"),
        ("order_estimated_delivery_date", "TIMESTAMP", "Estimated delivery date"),
    ],
    "raw.olist_order_items_dataset": [
        ("order_id", "VARCHAR", "Order foreign key"),
        ("order_item_id", "INTEGER", "Sequential item number within order"),
        ("product_id", "VARCHAR", "Product foreign key"),
        ("seller_id", "VARCHAR", "Seller foreign key"),
        ("shipping_limit_date", "TIMESTAMP", "Shipping deadline"),
        ("price", "DECIMAL(10,2)", "Item price excluding freight"),
        ("freight_value", "DECIMAL(10,2)", "Item freight cost"),
    ],
    "raw.olist_order_payments_dataset": [
        ("order_id", "VARCHAR", "Order foreign key"),
        ("payment_sequential", "INTEGER", "Payment sequence number"),
        ("payment_type", "VARCHAR", "Payment method"),
        ("payment_installments", "INTEGER", "Number of installments"),
        ("payment_value", "DECIMAL(10,2)", "Payment amount"),
    ],
    "raw.olist_order_reviews_dataset": [
        ("review_id", "VARCHAR", "Review identifier"),
        ("order_id", "VARCHAR", "Order foreign key"),
        ("review_score", "INTEGER", "Customer satisfaction score 1-5"),
        ("review_comment_title", "VARCHAR", "Review title"),
        ("review_comment_message", "VARCHAR", "Review body message"),
        ("review_creation_date", "TIMESTAMP", "Review sent date"),
        ("review_answer_timestamp", "TIMESTAMP", "Review answer date"),
    ],
    "raw.olist_customers_dataset": [
        ("customer_id", "VARCHAR", "Transactional customer identifier"),
        ("customer_unique_id", "VARCHAR", "Unique persistent customer key"),
        ("customer_zip_code_prefix", "INTEGER", "Customer zip prefix"),
        ("customer_city", "VARCHAR", "Customer residence city"),
        ("customer_state", "VARCHAR", "Customer residence state"),
    ],
    "raw.olist_sellers_dataset": [
        ("seller_id", "VARCHAR", "Seller unique identifier"),
        ("seller_zip_code_prefix", "INTEGER", "Seller zip prefix"),
        ("seller_city", "VARCHAR", "Seller city"),
        ("seller_state", "VARCHAR", "Seller state"),
    ],
    "raw.olist_products_dataset": [
        ("product_id", "VARCHAR", "Product unique identifier"),
        ("product_category_name", "VARCHAR", "Original category name"),
        ("product_name_lenght", "INTEGER", "Length of product title"),
        ("product_description_lenght", "INTEGER", "Length of product description"),
        ("product_photos_qty", "INTEGER", "Number of product photos"),
        ("product_weight_g", "DOUBLE", "Weight in grams"),
        ("product_length_cm", "DOUBLE", "Length in cm"),
        ("product_height_cm", "DOUBLE", "Height in cm"),
        ("product_width_cm", "DOUBLE", "Width in cm"),
    ],
    "raw.product_category_name_translation": [
        ("product_category_name", "VARCHAR", "Portuguese category name"),
        ("product_category_name_english", "VARCHAR", "English category name"),
    ],
    "raw.olist_geolocation_dataset": [
        ("geolocation_zip_code_prefix", "INTEGER", "Zip prefix"),
        ("geolocation_lat", "DOUBLE", "Latitude"),
        ("geolocation_lng", "DOUBLE", "Longitude"),
        ("geolocation_city", "VARCHAR", "City"),
        ("geolocation_state", "VARCHAR", "State"),
    ],
    "staging.stg_orders": [
        ("order_id", "VARCHAR", "Order unique identifier"),
        ("customer_id", "VARCHAR", "Customer transactional identifier"),
        ("customer_unique_id", "VARCHAR", "Unique persistent customer key"),
        ("order_status", "VARCHAR", "Current fulfillment status"),
        ("order_purchase_timestamp", "TIMESTAMP", "Purchase datetime"),
        ("order_purchase_date", "DATE", "Purchase calendar date"),
        ("order_approved_at", "TIMESTAMP", "Approval timestamp"),
        ("order_delivered_carrier_date", "TIMESTAMP", "Carrier dispatch timestamp"),
        ("order_delivered_customer_date", "TIMESTAMP", "Delivery timestamp"),
        ("order_estimated_delivery_date", "TIMESTAMP", "Estimated delivery date"),
        ("is_delivered", "BOOLEAN", "True if status is delivered"),
        ("is_canceled", "BOOLEAN", "True if status is canceled"),
    ],
    "staging.stg_order_items": [
        ("order_id", "VARCHAR", "Order reference"),
        ("order_item_id", "INTEGER", "Item sequence number"),
        ("product_id", "VARCHAR", "Product reference"),
        ("seller_id", "VARCHAR", "Seller reference"),
        ("shipping_limit_date", "TIMESTAMP", "Shipping limit timestamp"),
        ("price", "DECIMAL(10,2)", "Item price"),
        ("freight_value", "DECIMAL(10,2)", "Item freight value"),
        ("total_item_value", "DECIMAL(10,2)", "Price plus freight"),
    ],
    "staging.stg_order_payments": [
        ("order_id", "VARCHAR", "Order reference"),
        ("payment_sequential", "INTEGER", "Payment sequence index"),
        ("payment_type", "VARCHAR", "Payment instrument type"),
        ("payment_installments", "INTEGER", "Installments count"),
        ("payment_value", "DECIMAL(10,2)", "Payment amount"),
    ],
    "staging.stg_order_reviews": [
        ("review_id", "VARCHAR", "Review identifier"),
        ("order_id", "VARCHAR", "Order reference"),
        ("review_score", "INTEGER", "Customer score rating"),
        ("review_comment_title", "VARCHAR", "Comment title"),
        ("review_comment_message", "VARCHAR", "Comment text"),
        ("review_creation_date", "TIMESTAMP", "Survey creation timestamp"),
        ("review_answer_timestamp", "TIMESTAMP", "Survey answer timestamp"),
    ],
    "staging.stg_customers": [
        ("customer_id", "VARCHAR", "Transactional customer key"),
        ("customer_unique_id", "VARCHAR", "Unique persistent customer identifier"),
        ("customer_zip_code_prefix", "INTEGER", "Customer zip prefix"),
        ("customer_city", "VARCHAR", "Customer residence city"),
        ("customer_state", "VARCHAR", "Customer residence state"),
    ],
    "staging.stg_sellers": [
        ("seller_id", "VARCHAR", "Seller identifier"),
        ("seller_zip_code_prefix", "INTEGER", "Seller zip prefix"),
        ("seller_city", "VARCHAR", "Seller city"),
        ("seller_state", "VARCHAR", "Seller state"),
    ],
    "staging.stg_products": [
        ("product_id", "VARCHAR", "Product identifier"),
        ("category_name_pt", "VARCHAR", "Portuguese category name"),
        ("category_name_en", "VARCHAR", "English category name"),
        ("product_weight_g", "DOUBLE", "Weight in grams"),
        ("product_length_cm", "DOUBLE", "Length in cm"),
        ("product_height_cm", "DOUBLE", "Height in cm"),
        ("product_width_cm", "DOUBLE", "Width in cm"),
    ],
}


class ContextAssembler:
    """Assembles prompt contexts across levels L0-L4 with DDL compression, prefix caching and inspection."""

    def __init__(
        self,
        catalog: MetadataCatalog,
        retriever: HybridRetriever,
        db_path: Path | str | None = None,
    ) -> None:
        self.catalog = catalog
        self.retriever = retriever
        self.db_path = Path(db_path) if db_path else None
        self._raw_full_schema_ddl: str | None = None
        self._raw_full_schema_tables: list[SelectedTableInfo] | None = None
        self._raw_full_schema_tokens: int | None = None

    def _extract_raw_full_schema(self) -> tuple[str, list[SelectedTableInfo], int]:
        """Extracts or synthesizes the full naive DDL dump for raw, staging and marts schemas."""
        if (
            self._raw_full_schema_ddl is not None
            and self._raw_full_schema_tables is not None
            and self._raw_full_schema_tokens is not None
        ):
            return self._raw_full_schema_ddl, self._raw_full_schema_tables, self._raw_full_schema_tokens

        ddl_statements: list[str] = []
        selected_tables: list[SelectedTableInfo] = []

        if self.db_path and self.db_path.exists():
            con = duckdb.connect(str(self.db_path), read_only=True)
            try:
                cols = con.execute("""
                    SELECT table_schema, table_name, column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema IN ('raw', 'staging', 'marts')
                    ORDER BY table_schema, table_name, ordinal_position
                """).fetchall()

                current_tbl: str | None = None
                tbl_cols: list[str] = []
                tbl_cols_names: list[str] = []

                for schema, tbl, col, dtype, is_null in cols:
                    full_name = f"{schema}.{tbl}"
                    if full_name != current_tbl:
                        if current_tbl:
                            cols_joined = ",\n".join(tbl_cols)
                            ddl_statements.append(
                                f"-- Naive full schema DDL for: {current_tbl}\n"
                                f"CREATE TABLE {current_tbl} (\n{cols_joined}\n);"
                            )
                            s_name, t_name = current_tbl.split(".", 1)
                            selected_tables.append(
                                SelectedTableInfo(
                                    table_name=current_tbl,
                                    schema_name=s_name,
                                    selection_type="baseline_dump",
                                    reason=f"Full naive schema dump ({s_name}.{t_name})",
                                    columns_included=tbl_cols_names,
                                )
                            )
                            tbl_cols = []
                            tbl_cols_names = []
                        current_tbl = full_name

                    null_txt = "NOT NULL" if is_null == "NO" else "NULL"
                    tbl_cols.append(f"    {col:<28} {dtype:<16} {null_txt} COMMENT 'Column {col} in {full_name}'")
                    tbl_cols_names.append(col)

                if current_tbl:
                    cols_joined = ",\n".join(tbl_cols)
                    ddl_statements.append(
                        f"-- Naive full schema DDL for: {current_tbl}\n"
                        f"CREATE TABLE {current_tbl} (\n{cols_joined}\n);"
                    )
                    s_name, t_name = current_tbl.split(".", 1)
                    selected_tables.append(
                        SelectedTableInfo(
                            table_name=current_tbl,
                            schema_name=s_name,
                            selection_type="baseline_dump",
                            reason=f"Full naive schema dump ({s_name}.{t_name})",
                            columns_included=tbl_cols_names,
                        )
                    )
            finally:
                con.close()
        else:
            # Fallback schema synthesis from catalog and FALLBACK_SCHEMAS
            for tbl_name, col_list in FALLBACK_SCHEMAS.items():
                s_name, t_name = tbl_name.split(".", 1)
                col_defs = [
                    f"    {col:<28} {dtype:<16} NULL COMMENT '{desc}'"
                    for col, dtype, desc in col_list
                ]
                ddl_statements.append(
                    f"-- Naive full schema DDL for: {tbl_name}\n"
                    f"CREATE TABLE {tbl_name} (\n" + ",\n".join(col_defs) + "\n);"
                )
                selected_tables.append(
                    SelectedTableInfo(
                        table_name=tbl_name,
                        schema_name=s_name,
                        selection_type="baseline_dump",
                        reason=f"Full naive schema dump ({tbl_name})",
                        columns_included=[c[0] for c in col_list],
                    )
                )

            # Marts from catalog
            for t in self.catalog.tables:
                col_defs = [
                    f"    {c.name:<28} {c.data_type:<16} NULL COMMENT '{_first_sentence(c.description)}'"
                    for c in t.columns
                ]
                ddl_statements.append(
                    f"-- Naive full schema DDL for: {t.name}\n"
                    f"CREATE TABLE {t.name} (\n" + ",\n".join(col_defs) + "\n);"
                )
                selected_tables.append(
                    SelectedTableInfo(
                        table_name=t.name,
                        schema_name=t.schema_name,
                        selection_type="baseline_dump",
                        reason=f"Full naive schema dump ({t.name})",
                        columns_included=[c.name for c in t.columns],
                    )
                )

        raw_ddl = "\n\n".join(ddl_statements)
        tokens = estimate_tokens(raw_ddl)

        self._raw_full_schema_ddl = raw_ddl
        self._raw_full_schema_tables = selected_tables
        self._raw_full_schema_tokens = tokens
        return raw_ddl, selected_tables, tokens

    def _build_dialect_instructions(self) -> str:
        """Returns standard DuckDB system instructions and dialect conventions."""
        return (
            "Você é um engenheiro analítico e especialista sênior em DuckDB SQL no Data Context Engine (DCE).\n"
            "Sua função é gerar consultas SQL precisas, determinísticas e semanticamente corretas no dialeto DuckDB.\n\n"
            "### Diretrizes Gerais de Geração de SQL:\n"
            "1. Gere exclusivamente consultas SQL executáveis no dialeto DuckDB.\n"
            "2. Utilize nomes totalmente qualificados para as tabelas (ex: `marts.fct_orders`).\n"
            "3. Nunca consulte schemas brutos ou intermediários (`raw`, `staging`). Utilize EXCLUSIVAMENTE o schema `marts`.\n"
            "4. Crie aliases claros e semânticos para todas as colunas calculadas e agregadas.\n"
            "5. Use CTEs (Common Table Expressions) para estruturar cálculos em etapas lógicas sempre que a consulta for complexa.\n"
            "6. Ordene os resultados explicitamente quando a pergunta solicitar 'maiores', 'melhores', 'top N', ou análises temporais.\n"
            "7. Trate valores nulos adequadamente utilizando `COALESCE` e `NULLS LAST` em ordenações descendentes.\n\n"
            "### Guia Completo do Dialeto DuckDB:\n"
            "- Manipulação de Datas e Intervalos:\n"
            "  - Truncamento e datas: `DATE_TRUNC('month', order_purchase_timestamp)`, `DATE_TRUNC('year', order_purchase_date)`.\n"
            "  - Diferença entre datas: `DATE_DIFF('day', order_purchase_date, order_delivered_customer_date)`.\n"
            "  - Conversões de tipo: `CAST(order_purchase_timestamp AS DATE)`, `STRFTIME(order_purchase_date, '%Y-%m')`.\n"
            "- Agregações e Janelas:\n"
            "  - Seleção por extremo: `ARG_MAX(customer_city, order_purchase_timestamp)` retorna a cidade do pedido mais recente.\n"
            "  - Arredondamento numérico: `ROUND(expr, 2)` para valores monetários e taxas.\n"
            "  - Contagens condicionais: `COUNT(DISTINCT CASE WHEN order_status = 'delivered' THEN customer_unique_id END)`.\n"
            "- Filtragem e Texto:\n"
            "  - Comparações textuais insensíveis a maiúsculas/minúsculas devem usar `ILIKE` ou `LOWER(col)`.\n"
            "  - Tratamento de nulos em filtros: utilize `COALESCE(col, 'fallback')` para comparações seguras."
        )

    def _build_business_rules_and_joins(self) -> str:
        """Formats RN-01 to RN-07 business rules and forbidden joins."""
        lines = ["### Regras de Negócio Globais Canônicas (RN-01 a RN-07):"]
        for r in self.catalog.business_rules:
            cond = f"\n  - Condição SQL canônica: `{r.rule_sql_condition}`" if r.rule_sql_condition else ""
            lines.append(f"- **{r.id}: {r.name}**\n  - {r.description}{cond}")

        lines.append("\n### Joins Proibidos e Restrições Estruturais:")
        for fj in self.catalog.forbidden_joins:
            cond = f" via `{fj.on_condition}`" if fj.on_condition else ""
            lines.append(f"- **PROIBIDO JOIN:** Entre `{fj.from_table}` e `{fj.to_table}`{cond}. Motivo: {fj.reason}")

        return "\n".join(lines)

    def _format_compressed_ddl(
        self,
        tables: list[TableMetadata],
        columns_filter: dict[str, list[str]] | None = None,
    ) -> str:
        """Formats table schemas as concise Markdown with column types and structural constraints."""
        table_blocks: list[str] = []
        for t in tables:
            allowed_cols = columns_filter.get(t.name) if columns_filter else None
            cols_txt: list[str] = []

            for c in t.columns:
                if allowed_cols and c.name not in allowed_cols:
                    continue

                extras: list[str] = []
                if c.is_primary_key:
                    extras.append("PK")
                if c.is_foreign_key or c.references:
                    ref = f" -> {c.references}" if c.references else ""
                    extras.append(f"FK{ref}")
                if c.allowed_values:
                    vals = ",".join(c.allowed_values[:3])
                    extras.append(f"enum=[{vals}]")

                extra_str = f", {', '.join(extras)}" if extras else ""
                cols_txt.append(f"- {c.name} ({c.data_type}{extra_str})")

            desc_tbl = f" ({_first_sentence(t.description)})" if t.description else ""
            table_blocks.append(f"### Table: {t.name}{desc_tbl}\nColumns:\n" + "\n".join(cols_txt))

        return "\n\n".join(table_blocks)

    def _format_metrics_block(
        self,
        metrics: list[MetricMetadata] | list[SelectedMetricInfo],
    ) -> str:
        """Formats canonical semantic metrics into structured Markdown."""
        metric_blocks: list[str] = []
        for m in metrics:
            m_id = getattr(m, "metric_id", getattr(m, "id", ""))
            filters = ", ".join(m.filters_required) if m.filters_required else "Nenhum"
            short_desc = _first_sentence(m.description)
            metric_blocks.append(
                f"### Metric: {m.name} (`{m_id}`)\n"
                f"- Base Table: `{m.base_table}` | Canonical SQL: `{m.canonical_sql}` | Filters: `{filters}`\n"
                f"- Description: {short_desc}"
            )
        return "\n\n".join(metric_blocks)

    def _format_few_shot_block(
        self,
        examples: list[RetrievedExampleInfo] | list[FewShotExample],
    ) -> str:
        """Formats retrieved few-shot examples into Markdown."""
        ex_blocks: list[str] = []
        for i, ex in enumerate(examples, 1):
            ex_blocks.append(
                f"#### Example {i} ({ex.id}):\n"
                f"Question: {ex.question}\n"
                f"```sql\n{ex.sql.strip()}\n```"
            )
        return "\n\n".join(ex_blocks)

    def assemble(
        self,
        question: str,
        level: ContextLevel = ContextLevel.L4,
        selected_metric_id: str | None = None,
        token_budget: int = 2500,
        include_user_playbooks: bool = True,
    ) -> AssembledContext:
        """Assembles prompt context according to the specified context level (L0-L4)."""
        start_time = time.perf_counter()

        raw_ddl, raw_tables, raw_full_tokens = self._extract_raw_full_schema()
        dialect_instructions = self._build_dialect_instructions()
        rules_and_joins = self._build_business_rules_and_joins()

        if level == ContextLevel.L0:
            static_prefix = dialect_instructions
            dynamic_suffix = f"### Pergunta do Usuário:\n{question}"
            full_prompt = f"{static_prefix}\n\n{dynamic_suffix}"

            assembled_tokens = estimate_tokens(full_prompt)
            prefix_tokens = estimate_tokens(static_prefix)
            prefix_pct = (prefix_tokens / assembled_tokens * 100.0) if assembled_tokens > 0 else 0.0
            savings_pct = (
                max(0.0, (raw_full_tokens - assembled_tokens) / raw_full_tokens * 100.0)
                if raw_full_tokens > 0
                else 0.0
            )

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            report = ContextInspectionReport(
                level=ContextLevel.L0,
                token_budget=token_budget,
                raw_full_schema_tokens=raw_full_tokens,
                assembled_context_tokens=assembled_tokens,
                token_savings_pct=savings_pct,
                prefix_cacheable_tokens=prefix_tokens,
                prefix_cacheable_pct=prefix_pct,
                selected_tables=[],
                selected_metrics=[],
                few_shot_examples=[],
                latency_ms=latency_ms,
            )
            return AssembledContext(
                level=ContextLevel.L0,
                static_prefix=static_prefix,
                dynamic_suffix=dynamic_suffix,
                full_prompt=full_prompt,
                schema_ddl="",
                semantic_metrics="",
                few_shot_block="",
                inspection=report,
            )

        elif level == ContextLevel.L1:
            static_prefix = dialect_instructions
            dynamic_suffix = (
                f"### Schema Bruto Completo do Banco de Dados:\n{raw_ddl}\n\n"
                f"### Pergunta do Usuário:\n{question}"
            )
            full_prompt = f"{static_prefix}\n\n{dynamic_suffix}"

            assembled_tokens = estimate_tokens(full_prompt)
            prefix_tokens = estimate_tokens(static_prefix)
            prefix_pct = (prefix_tokens / assembled_tokens * 100.0) if assembled_tokens > 0 else 0.0

            # L1 represents the naive baseline: token savings is 0.0%
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            report = ContextInspectionReport(
                level=ContextLevel.L1,
                token_budget=token_budget,
                raw_full_schema_tokens=assembled_tokens,
                assembled_context_tokens=assembled_tokens,
                token_savings_pct=0.0,
                prefix_cacheable_tokens=prefix_tokens,
                prefix_cacheable_pct=prefix_pct,
                selected_tables=raw_tables,
                selected_metrics=[],
                few_shot_examples=[],
                latency_ms=latency_ms,
            )
            return AssembledContext(
                level=ContextLevel.L1,
                static_prefix=static_prefix,
                dynamic_suffix=dynamic_suffix,
                full_prompt=full_prompt,
                schema_ddl=raw_ddl,
                semantic_metrics="",
                few_shot_block="",
                inspection=report,
            )

        elif level == ContextLevel.L2:
            marts_tables = [t for t in self.catalog.tables if t.schema_name == "marts"]
            marts_ddl = self._format_compressed_ddl(marts_tables)

            static_prefix = (
                f"{dialect_instructions}\n\n"
                f"### Schemas das Tabelas Analíticas (marts):\n{marts_ddl}"
            )
            dynamic_suffix = f"### Pergunta do Usuário:\n{question}"
            full_prompt = f"{static_prefix}\n\n{dynamic_suffix}"

            assembled_tokens = estimate_tokens(full_prompt)
            prefix_tokens = estimate_tokens(static_prefix)
            prefix_pct = (prefix_tokens / assembled_tokens * 100.0) if assembled_tokens > 0 else 0.0
            savings_pct = (
                max(0.0, (raw_full_tokens - assembled_tokens) / raw_full_tokens * 100.0)
                if raw_full_tokens > 0
                else 0.0
            )

            selected_tbls = [
                SelectedTableInfo(
                    table_name=t.name,
                    schema_name=t.schema_name,
                    selection_type="direct_match",
                    reason=f"All marts tables in L2 ({t.name})",
                    columns_included=[c.name for c in t.columns],
                )
                for t in marts_tables
            ]

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            report = ContextInspectionReport(
                level=ContextLevel.L2,
                token_budget=token_budget,
                raw_full_schema_tokens=raw_full_tokens,
                assembled_context_tokens=assembled_tokens,
                token_savings_pct=savings_pct,
                prefix_cacheable_tokens=prefix_tokens,
                prefix_cacheable_pct=prefix_pct,
                selected_tables=selected_tbls,
                selected_metrics=[],
                few_shot_examples=[],
                latency_ms=latency_ms,
            )
            return AssembledContext(
                level=ContextLevel.L2,
                static_prefix=static_prefix,
                dynamic_suffix=dynamic_suffix,
                full_prompt=full_prompt,
                schema_ddl=marts_ddl,
                semantic_metrics="",
                few_shot_block="",
                inspection=report,
            )

        elif level == ContextLevel.L3:
            marts_tables = [t for t in self.catalog.tables if t.schema_name == "marts"]
            marts_ddl = self._format_compressed_ddl(marts_tables)
            metrics_block = self._format_metrics_block(self.catalog.metrics)

            static_prefix = (
                f"{dialect_instructions}\n\n"
                f"{rules_and_joins}\n\n"
                f"### Camada Semântica de Métricas Canônicas:\n{metrics_block}\n\n"
                f"### Schemas das Tabelas Analíticas (marts):\n{marts_ddl}"
            )
            dynamic_suffix = f"### Pergunta do Usuário:\n{question}"
            full_prompt = f"{static_prefix}\n\n{dynamic_suffix}"

            assembled_tokens = estimate_tokens(full_prompt)
            prefix_tokens = estimate_tokens(static_prefix)
            prefix_pct = (prefix_tokens / assembled_tokens * 100.0) if assembled_tokens > 0 else 0.0
            savings_pct = (
                max(0.0, (raw_full_tokens - assembled_tokens) / raw_full_tokens * 100.0)
                if raw_full_tokens > 0
                else 0.0
            )

            selected_tbls = [
                SelectedTableInfo(
                    table_name=t.name,
                    schema_name=t.schema_name,
                    selection_type="direct_match",
                    reason=f"All marts tables in L3 ({t.name})",
                    columns_included=[c.name for c in t.columns],
                )
                for t in marts_tables
            ]
            selected_mets = [
                SelectedMetricInfo(
                    metric_id=m.id,
                    name=m.name,
                    canonical_sql=m.canonical_sql,
                    base_table=m.base_table,
                    description=m.description,
                    filters_required=m.filters_required,
                )
                for m in self.catalog.metrics
            ]

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            report = ContextInspectionReport(
                level=ContextLevel.L3,
                token_budget=token_budget,
                raw_full_schema_tokens=raw_full_tokens,
                assembled_context_tokens=assembled_tokens,
                token_savings_pct=savings_pct,
                prefix_cacheable_tokens=prefix_tokens,
                prefix_cacheable_pct=prefix_pct,
                selected_tables=selected_tbls,
                selected_metrics=selected_mets,
                few_shot_examples=[],
                latency_ms=latency_ms,
            )
            return AssembledContext(
                level=ContextLevel.L3,
                static_prefix=static_prefix,
                dynamic_suffix=dynamic_suffix,
                full_prompt=full_prompt,
                schema_ddl=marts_ddl,
                semantic_metrics=metrics_block,
                few_shot_block="",
                inspection=report,
            )

        else:
            # ContextLevel.L4 - Full Context Engine with Pruning, Few-Shot and Prefix Caching
            bundle = self.retriever.retrieve(
                question=question,
                selected_metric_id=selected_metric_id,
                include_user_playbooks=include_user_playbooks,
            )

            # Static prefix: System instructions + DuckDB guidelines + Business rules RN-01..07 + Forbidden joins
            static_prefix = f"{dialect_instructions}\n\n{rules_and_joins}"

            # Dynamic suffix components
            chosen_tables: list[TableMetadata] = []
            for t_info in bundle.selected_tables:
                t_meta = self.catalog.get_table(t_info.table_name)
                if t_meta:
                    chosen_tables.append(t_meta)

            compressed_ddl = self._format_compressed_ddl(chosen_tables)
            metrics_block = self._format_metrics_block(bundle.selected_metrics)
            few_shot_block = self._format_few_shot_block(bundle.few_shot_examples)

            suffix_parts: list[str] = []
            if compressed_ddl:
                suffix_parts.append(f"### Schemas das Tabelas Selecionadas (DDL Compacto):\n{compressed_ddl}")
            if metrics_block:
                suffix_parts.append(f"### Métricas Semânticas Canônicas Aplicáveis:\n{metrics_block}")
            if few_shot_block:
                suffix_parts.append(f"### Exemplos Analíticos Relevantes (Few-Shot):\n{few_shot_block}")
            suffix_parts.append(f"### Pergunta do Usuário:\n{question}")

            dynamic_suffix = "\n\n".join(suffix_parts)
            full_prompt = f"{static_prefix}\n\n{dynamic_suffix}"

            assembled_tokens = estimate_tokens(full_prompt)
            prefix_tokens = estimate_tokens(static_prefix)
            prefix_pct = (prefix_tokens / assembled_tokens * 100.0) if assembled_tokens > 0 else 0.0
            savings_pct = (
                max(0.0, (raw_full_tokens - assembled_tokens) / raw_full_tokens * 100.0)
                if raw_full_tokens > 0
                else 0.0
            )

            latency_ms = (time.perf_counter() - start_time) * 1000.0
            report = ContextInspectionReport(
                level=ContextLevel.L4,
                token_budget=token_budget,
                raw_full_schema_tokens=raw_full_tokens,
                assembled_context_tokens=assembled_tokens,
                token_savings_pct=savings_pct,
                prefix_cacheable_tokens=prefix_tokens,
                prefix_cacheable_pct=prefix_pct,
                selected_tables=bundle.selected_tables,
                selected_metrics=bundle.selected_metrics,
                few_shot_examples=bundle.few_shot_examples,
                latency_ms=latency_ms,
            )
            return AssembledContext(
                level=ContextLevel.L4,
                static_prefix=static_prefix,
                dynamic_suffix=dynamic_suffix,
                full_prompt=full_prompt,
                schema_ddl=compressed_ddl,
                semantic_metrics=metrics_block,
                few_shot_block=few_shot_block,
                inspection=report,
            )

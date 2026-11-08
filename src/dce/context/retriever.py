import json
import logging
import re
import unicodedata
from collections import deque
from pathlib import Path

from dce.models import (
    FewShotExample,
    MetadataCatalog,
    RetrievalBundle,
    RetrievedExampleInfo,
    SelectedMetricInfo,
    SelectedTableInfo,
    TableMetadata,
)

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
    "em", "no", "na", "nos", "nas", "para", "por", "com", "que", "qual", "quais",
    "quem", "como", "quando", "onde", "e", "ou", "se", "mais", "menos", "muito",
    "nosso", "nossos", "nossa", "nossas", "sao", "foi", "foram", "pelo", "pela",
    "pelos", "pelas", "ao", "aos",
}

CONCEPT_MAPPINGS: dict[str, list[str]] = {
    "dim_customers": [
        "cliente", "clientes", "comprador", "compradores", "consumidor", "consumidores",
        "estado", "cidade", "uf", "moram", "residencia", "ltv", "recompra",
    ],
    "dim_products": [
        "produto", "produtos", "categoria", "categorias", "item", "dimensoes", "peso",
    ],
    "dim_sellers": [
        "vendedor", "vendedores", "seller", "sellers", "lojista", "lojistas", "avaliacao",
    ],
    "fct_orders": [
        "pedido", "pedidos", "compra", "compras", "ordem", "ordens", "faturamento",
        "receita", "entrega", "atraso", "frete", "status",
    ],
    "fct_order_items": [
        "item", "itens", "linha", "linhas", "preco", "frete", "venda", "vendas",
    ],
    "fct_order_payments": [
        "pagamento", "pagamentos", "parcela", "parcelas", "cartao", "boleto", "voucher",
    ],
}


def _normalize_text(text: str) -> str:
    """Lowercases, strips accents, replaces underscores/punctuation, and removes excess whitespace."""
    text = text.lower().replace("_", " ")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(text: str) -> set[str]:
    """Tokenizes text into normalized unique words excluding stop words."""
    norm = _normalize_text(text)
    words = norm.split()
    return {w for w in words if w not in STOP_WORDS and len(w) >= 2}


class HybridRetriever:
    """Retrieves relevant tables, canonical metrics, and few-shot examples with relational graph expansion."""

    def __init__(
        self,
        catalog: MetadataCatalog,
        playbooks_path: Path | str = Path("data/playbooks/saved_playbooks.json"),
    ) -> None:
        self.catalog = catalog
        self.playbooks_path = Path(playbooks_path)
        self._graph = self._build_join_graph()

    def _canonical_table_name(self, name: str) -> str:
        t = self.catalog.get_table(name)
        if t:
            return t.name
        if not name.startswith("marts.") and "." not in name:
            return f"marts.{name}"
        return name

    def _build_join_graph(self) -> dict[str, set[str]]:
        adj: dict[str, set[str]] = {}
        for table in self.catalog.tables:
            if table.schema_name == "marts":
                adj.setdefault(table.name, set())

        for join in self.catalog.allowed_joins:
            u = self._canonical_table_name(join.from_table)
            v = self._canonical_table_name(join.to_table)
            adj.setdefault(u, set()).add(v)
            adj.setdefault(v, set()).add(u)

        return adj

    def _find_shortest_path(self, start: str, target: str) -> list[str] | None:
        if start == target:
            return [start]
        queue = deque([(start, [start])])
        visited = {start}
        while queue:
            curr, path = queue.popleft()
            if curr == target:
                return path
            for neighbor in sorted(self._graph.get(curr, set())):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return None

    def _score_table(
        self,
        table: TableMetadata,
        question: str,
        q_tokens: set[str],
    ) -> float:
        score = 0.0
        short_name = table.name.split(".")[-1]

        # 1. Concept mapping boost
        for concept in CONCEPT_MAPPINGS.get(short_name, []):
            if concept in q_tokens:
                score += 3.5

        # 2. Table name matching
        table_tokens = _tokenize(short_name)
        score += 3.0 * len(q_tokens & table_tokens)

        # 3. Table description matching
        desc_tokens = _tokenize(table.description)
        score += 1.0 * len(q_tokens & desc_tokens)

        # 4. Columns matching
        for col in table.columns:
            col_tokens = _tokenize(col.name)
            # Exact token match with column name
            score += 4.5 * len(q_tokens & col_tokens)

            # Column description
            col_desc_tokens = _tokenize(col.description)
            score += 1.5 * len(q_tokens & col_desc_tokens)

            # Allowed values
            for val in col.allowed_values:
                val_norm = _normalize_text(val)
                if val_norm in q_tokens:
                    score += 2.0

        return round(score, 2)

    def _select_tables(
        self,
        question: str,
        priority_table: str | None = None,
        top_k_tables: int = 3,
    ) -> list[SelectedTableInfo]:
        q_tokens = _tokenize(question)
        mart_tables = [t for t in self.catalog.tables if t.schema_name == "marts"]

        scored_tables: list[tuple[TableMetadata, float, bool]] = []
        for table in mart_tables:
            is_priority = bool(
                priority_table
                and (
                    table.name == priority_table
                    or table.name.endswith(priority_table)
                    or priority_table.endswith(table.name)
                )
            )
            s = self._score_table(table, question, q_tokens)
            scored_tables.append((table, s, is_priority))

        # Sort: priority tables first, then by score descending
        scored_tables.sort(key=lambda x: (1 if x[2] else 0, x[1]), reverse=True)

        selected_direct: list[SelectedTableInfo] = []
        if not scored_tables:
            return selected_direct

        max_lexical_score = max((x[1] for x in scored_tables), default=0.0)
        threshold = max(3.5, 0.35 * max_lexical_score)

        for table, score, is_priority in scored_tables:
            if len(selected_direct) >= top_k_tables:
                break
            if is_priority:
                selected_direct.append(
                    SelectedTableInfo(
                        table_name=table.name,
                        schema_name=table.schema_name,
                        selection_type="direct_match",
                        reason=f"Primary table for resolved metric (lexical score: {score:.1f})",
                        relevance_score=score + 100.0,
                        columns_included=[c.name for c in table.columns],
                    )
                )
            elif score >= threshold and score > 0.0:
                selected_direct.append(
                    SelectedTableInfo(
                        table_name=table.name,
                        schema_name=table.schema_name,
                        selection_type="direct_match",
                        reason=f"Direct match on query terms (score: {score:.1f})",
                        relevance_score=score,
                        columns_included=[c.name for c in table.columns],
                    )
                )

        # Fallback: if no table passed threshold but max_lexical_score > 0, pick top 1
        if not selected_direct and max_lexical_score > 0:
            top_t, top_s, _ = scored_tables[0]
            selected_direct.append(
                SelectedTableInfo(
                    table_name=top_t.name,
                    schema_name=top_t.schema_name,
                    selection_type="direct_match",
                    reason=f"Direct match on query terms (score: {top_s:.1f})",
                    relevance_score=top_s,
                    columns_included=[c.name for c in top_t.columns],
                )
            )

        # Relational Graph Expansion (Graph Bridge)
        selected_table_names = {t.table_name for t in selected_direct}
        all_selected: list[SelectedTableInfo] = list(selected_direct)

        # Check all pairs in selected_direct
        for i in range(len(selected_direct)):
            for j in range(i + 1, len(selected_direct)):
                t1 = selected_direct[i].table_name
                t2 = selected_direct[j].table_name

                # If already directly connected in join graph, no bridge required
                if t2 in self._graph.get(t1, set()):
                    continue

                # Find shortest path
                path = self._find_shortest_path(t1, t2)
                if path and len(path) > 2:
                    # Intermediate nodes are bridge tables
                    for bridge_table in path[1:-1]:
                        if bridge_table not in selected_table_names:
                            t1_clean = t1.split(".")[-1]
                            t2_clean = t2.split(".")[-1]
                            bridge_meta = self.catalog.get_table(bridge_table)
                            cols = [c.name for c in bridge_meta.columns] if bridge_meta else []
                            bridge_info = SelectedTableInfo(
                                table_name=bridge_table,
                                schema_name="marts",
                                selection_type="graph_bridge",
                                reason=f"Graph bridge between {t1_clean} and {t2_clean}",
                                relevance_score=0.9,
                                columns_included=cols,
                            )
                            all_selected.append(bridge_info)
                            selected_table_names.add(bridge_table)

        return all_selected

    def _select_metrics(
        self,
        question: str,
        resolved_metric_id: str | None = None,
        selected_metric_id: str | None = None,
    ) -> list[SelectedMetricInfo]:
        selected_metrics: list[SelectedMetricInfo] = []
        added_metric_ids: set[str] = set()

        # 1. Primary resolved metric
        if resolved_metric_id:
            m = self.catalog.get_metric(resolved_metric_id)
            if m:
                selected_metrics.append(
                    SelectedMetricInfo(
                        metric_id=m.id,
                        name=m.name,
                        canonical_sql=m.canonical_sql,
                        base_table=m.base_table,
                        description=m.description,
                        filters_required=m.filters_required,
                        was_clarified_by_user=(selected_metric_id is not None),
                    )
                )
                added_metric_ids.add(m.id)

        # 2. Other metrics mentioned in question
        norm_q = _normalize_text(question)
        for m in self.catalog.metrics:
            if m.id in added_metric_ids:
                continue
            terms = [m.name, m.id] + m.synonyms
            for term in terms:
                norm_term = _normalize_text(term)
                if norm_term and len(norm_term) >= 3 and re.search(rf"\b{re.escape(norm_term)}\b", norm_q):
                    selected_metrics.append(
                        SelectedMetricInfo(
                            metric_id=m.id,
                            name=m.name,
                            canonical_sql=m.canonical_sql,
                            base_table=m.base_table,
                            description=m.description,
                            filters_required=m.filters_required,
                            was_clarified_by_user=False,
                        )
                    )
                    added_metric_ids.add(m.id)
                    break

        return selected_metrics

    def _select_few_shot(
        self,
        question: str,
        resolved_metric_id: str | None,
        selected_tables: list[SelectedTableInfo],
        top_k_examples: int = 3,
        include_user_playbooks: bool = True,
    ) -> list[RetrievedExampleInfo]:
        q_tokens = _tokenize(question)
        selected_table_names = {t.table_name for t in selected_tables}

        # Gather candidate examples
        candidates: list[FewShotExample] = list(self.catalog.few_shot_examples)

        # Load playbooks if present
        if include_user_playbooks and self.playbooks_path:
            playbook_path = Path(self.playbooks_path)
            if playbook_path.exists():
                try:
                    with open(playbook_path, "r", encoding="utf-8") as f:
                        pb_data = json.load(f)
                        if isinstance(pb_data, list):
                            for pb in pb_data:
                                if isinstance(pb, dict):
                                    q = pb.get("question", "")
                                    res_id = pb.get("resolved_metric_id")
                                    indexed_q = f"{q} [Critério: {res_id}]" if res_id else q
                                    candidates.append(
                                        FewShotExample(
                                            id=pb.get("id", ""),
                                            question=indexed_q,
                                            sql=pb.get("sanitized_sql", "") or pb.get("sql_query", ""),
                                            resolved_metric_id=res_id,
                                            tables_used=pb.get("used_tables", []) or pb.get("tables_used", []),
                                            explanation=pb.get("title", "Saved User Playbook"),
                                            origin="saved_playbook",
                                            source="saved_playbook",
                                        )
                                    )
                except (json.JSONDecodeError, OSError, KeyError, TypeError, AttributeError) as exc:
                    logger.debug("Failed to load saved playbooks: %s", exc)

        scored_examples: list[tuple[RetrievedExampleInfo, float]] = []
        for ex in candidates:
            ex_tokens = _tokenize(ex.question)
            union = q_tokens | ex_tokens
            jaccard = (len(q_tokens & ex_tokens) / max(len(union), 1)) if union else 0.0

            # Metric bonus
            metric_bonus = 0.0
            if resolved_metric_id and ex.resolved_metric_id == resolved_metric_id:
                metric_bonus = 5.0

            # Table overlap bonus
            table_bonus = 0.0
            ex_tables = getattr(ex, "tables_used", [])
            for tbl in ex_tables:
                if tbl in selected_table_names:
                    table_bonus += 0.5

            total_score = round(jaccard + metric_bonus + table_bonus, 3)
            origin = getattr(ex, "origin", "curated")
            source = "saved_playbook" if origin == "saved_playbook" else "static_few_shot"
            info = RetrievedExampleInfo(
                id=ex.id,
                question=ex.question,
                sql=ex.sql.strip(),
                similarity_score=total_score,
                resolved_metric_id=ex.resolved_metric_id,
                origin=origin,
                source=source,
            )
            scored_examples.append((info, total_score))

        scored_examples.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in scored_examples[:top_k_examples]]

    _rank_few_shot_examples = _select_few_shot

    def retrieve(
        self,
        question: str,
        selected_metric_id: str | None = None,
        top_k_tables: int = 3,
        top_k_examples: int = 3,
        include_user_playbooks: bool = True,
    ) -> RetrievalBundle:
        """Retrieves and bundles tables, canonical metrics, and few-shot examples for the question.

        Args:
            question: The user query string.
            selected_metric_id: Explicit metric ID if already resolved or clarified.
            top_k_tables: Maximum number of direct match tables to retrieve before graph expansion.
            top_k_examples: Maximum number of few-shot examples to retrieve.
            include_user_playbooks: Whether to consider user saved playbooks in few-shot retrieval.

        Returns:
            RetrievalBundle with selected tables (including graph bridges), metrics, and examples.
        """
        resolved_metric_id = selected_metric_id
        priority_table: str | None = None
        if resolved_metric_id:
            m = self.catalog.get_metric(resolved_metric_id)
            if m:
                priority_table = m.base_table

        # 1. Select tables with graph bridge expansion
        selected_tables = self._select_tables(
            question=question,
            priority_table=priority_table,
            top_k_tables=top_k_tables,
        )

        # 2. Select metrics
        selected_metrics = self._select_metrics(
            question=question,
            resolved_metric_id=resolved_metric_id,
            selected_metric_id=selected_metric_id,
        )

        if not resolved_metric_id and selected_metrics:
            resolved_metric_id = selected_metrics[0].metric_id

        # 3. Select few-shot examples
        few_shot_examples = self._select_few_shot(
            question=question,
            resolved_metric_id=resolved_metric_id,
            selected_tables=selected_tables,
            top_k_examples=top_k_examples,
            include_user_playbooks=include_user_playbooks,
        )

        return RetrievalBundle(
            selected_tables=selected_tables,
            selected_metrics=selected_metrics,
            few_shot_examples=few_shot_examples,
            resolved_metric_id=resolved_metric_id,
        )

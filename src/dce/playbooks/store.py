import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import sqlglot
from sqlglot import errors

from dce.context.retriever import HybridRetriever
from dce.execution.executor import SafeSQLExecutor
from dce.execution.guardrails import SQLGuardrail, SQLSecurityViolationError
from dce.models import SavedPlaybook

logger = logging.getLogger(__name__)


class PlaybookStore:
    """Manages persistence, retrieval, validation, and hot-reload of saved user playbooks."""

    def __init__(
        self,
        storage_path: Path | str = Path("data/playbooks/saved_playbooks.json"),
        retriever: HybridRetriever | None = None,
        executor: SafeSQLExecutor | None = None,
    ) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.retriever = retriever
        self.executor = executor
        if self.retriever is not None:
            self.retriever.playbooks_path = self.storage_path

    def _save_to_disk(self, playbooks: list[SavedPlaybook]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = [pb.model_dump(mode="json") for pb in playbooks]
        temp_file = self.storage_path.with_suffix(f".tmp_{uuid.uuid4().hex[:6]}")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        temp_file.replace(self.storage_path)

    def list_playbooks(self, tag: str | None = None) -> list[SavedPlaybook]:
        if not self.storage_path.exists():
            return []
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return []
                raw_list = json.loads(content)
                if not isinstance(raw_list, list):
                    return []
                playbooks = [
                    SavedPlaybook.model_validate(item)
                    for item in raw_list
                    if isinstance(item, dict)
                ]
        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning("Failed to load playbooks from %s: %s", self.storage_path, exc)
            return []

        if tag:
            target = tag.lower().strip()
            return [pb for pb in playbooks if any(t.lower().strip() == target for t in pb.tags)]
        return playbooks

    def get_playbook(self, playbook_id: str) -> SavedPlaybook | None:
        for pb in self.list_playbooks():
            if pb.id == playbook_id:
                return pb
        return None

    def delete_playbook(self, playbook_id: str) -> bool:
        playbooks = self.list_playbooks()
        filtered = [pb for pb in playbooks if pb.id != playbook_id]
        if len(filtered) == len(playbooks):
            return False
        self._save_to_disk(filtered)
        return True

    def save_playbook(
        self,
        title: str,
        question: str,
        sql_query: str,
        resolved_metric_id: str | None = None,
        tags: list[str] | None = None,
    ) -> SavedPlaybook:
        tables_used: list[str] = []
        sanitized_sql = sql_query

        if self.executor is not None:
            exec_result = self.executor.execute(sql_query)
            if not exec_result.success:
                if exec_result.security_violation:
                    raise SQLSecurityViolationError(
                        exec_result.error_message or "Security violation in playbook query"
                    )
                raise ValueError(f"Playbook SQL execution failed: {exec_result.error_message}")
            if exec_result.tables_referenced:
                tables_used = list(exec_result.tables_referenced)
            if exec_result.sql_executed:
                sanitized_sql = exec_result.sql_executed
        else:
            guardrail = SQLGuardrail()
            guardrail_res = guardrail.validate_and_rewrite(sql_query)
            if guardrail_res.tables_referenced:
                tables_used = list(guardrail_res.tables_referenced)
            if guardrail_res.sanitized_sql:
                sanitized_sql = guardrail_res.sanitized_sql

        if not tables_used:
            try:
                parsed = sqlglot.parse_one(sanitized_sql, read="duckdb")
                cte_names = {
                    c.alias_or_name.lower()
                    for c in parsed.find_all(sqlglot.exp.CTE)
                    if c.alias_or_name
                }
                for tbl in parsed.find_all(sqlglot.exp.Table):
                    t_name = (tbl.name or "").strip()
                    if t_name:
                        s_name = (tbl.db or "").strip()
                        if not s_name and t_name.lower() in cte_names:
                            continue
                        full_t = f"{s_name}.{t_name}" if s_name else t_name
                        if full_t not in tables_used:
                            tables_used.append(full_t)
            except (errors.SqlglotError, ValueError) as exc:
                logger.debug("AST fallback table extraction failed: %s", exc)

        pb_id = f"pb_{uuid.uuid4().hex[:8]}"
        now_iso = datetime.now(UTC).isoformat()
        clean_tags = list(tags) if tags is not None else []

        pb = SavedPlaybook(
            id=pb_id,
            title=title,
            question=question,
            sql_query=sql_query,
            sanitized_sql=sanitized_sql,
            resolved_metric_id=resolved_metric_id,
            tables_used=tables_used,
            used_tables=tables_used,
            tags=clean_tags,
            created_at=now_iso,
            verified=True,
        )

        existing = self.list_playbooks()
        existing.append(pb)
        self._save_to_disk(existing)

        if self.retriever is not None:
            self.retriever.playbooks_path = self.storage_path

        return pb

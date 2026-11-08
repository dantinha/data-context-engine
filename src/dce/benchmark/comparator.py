"""ResultComparator matching DuckDB result sets independent of column ordering, aliases, or Decimal vs float."""

import datetime
import itertools
import math
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from dce.models import SQLExecutionResult


class ComparisonResult(BaseModel):
    is_match: bool
    reason: str = ""
    matched_columns: int = 0
    rows_compared: int = 0


def _normalize_value(val: Any) -> Any:
    """Normalizes scalar value to canonical float, ISO date string, or stripped lowercase string."""
    if val is None:
        return None
    if isinstance(val, (Decimal, int, float)):
        return float(val)
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        cleaned = val.strip().lower()
        # ISO date prefix check
        if (
            len(cleaned) >= 10
            and cleaned[4] == "-"
            and cleaned[7] == "-"
            and cleaned[:10].replace("-", "").isdigit()
        ):
            return cleaned[:10]
        return cleaned
    return str(val).strip().lower()


def _values_match(v1: Any, v2: Any, atol: float, rtol: float) -> bool:
    """Checks equality between two normalized scalar values within tolerance."""
    if v1 is None and v2 is None:
        return True
    if v1 is None or v2 is None:
        return False

    is_v1_num = isinstance(v1, (int, float))
    is_v2_num = isinstance(v2, (int, float))

    if is_v1_num and is_v2_num:
        if math.isnan(v1) and math.isnan(v2):
            return True
        return math.isclose(v1, v2, abs_tol=atol, rel_tol=rtol)

    if is_v1_num and isinstance(v2, str):
        try:
            return math.isclose(v1, float(v2), abs_tol=atol, rel_tol=rtol)
        except ValueError:
            return False

    if is_v2_num and isinstance(v1, str):
        try:
            return math.isclose(float(v1), v2, abs_tol=atol, rel_tol=rtol)
        except ValueError:
            return False

    return v1 == v2


def _row_sort_key(row_tuple: tuple[Any, ...]) -> tuple:
    """Deterministic sorting key for canonical ordering of row tuples."""
    key_items = []
    for item in row_tuple:
        if item is None:
            key_items.append((0, 0, ""))
        elif isinstance(item, (int, float)):
            key_items.append((1, round(item, 2), ""))
        elif isinstance(item, bool):
            key_items.append((2, 1 if item else 0, ""))
        else:
            key_items.append((3, 0, str(item)))
    return tuple(key_items)


class ResultComparator:
    """Compares DuckDB SQL query execution outputs against gold reference sets."""

    def compare(
        self,
        gold_rows: list[dict[str, Any]] | list[list[Any]],
        gen_rows: list[dict[str, Any]] | list[list[Any]],
        atol: float = 1e-2,
        rtol: float = 1e-2,
    ) -> ComparisonResult:
        """Compares two row sets independent of column ordering, aliases, row order or numeric type."""
        # Convert list of lists to list of dicts if needed
        norm_gold = self._to_row_dicts(gold_rows)
        norm_gen = self._to_row_dicts(gen_rows)

        if len(norm_gold) != len(norm_gen):
            return ComparisonResult(
                is_match=False,
                reason=f"Row count mismatch: gold={len(norm_gold)}, gen={len(norm_gen)}",
                matched_columns=0,
                rows_compared=max(len(norm_gold), len(norm_gen)),
            )

        if len(norm_gold) == 0:
            return ComparisonResult(
                is_match=True,
                reason="Both result sets are empty",
                matched_columns=0,
                rows_compared=0,
            )

        gold_keys = list(norm_gold[0].keys())
        gen_keys = list(norm_gen[0].keys())

        if len(gold_keys) != len(gen_keys):
            return ComparisonResult(
                is_match=False,
                reason=f"Column count mismatch: gold={len(gold_keys)}, gen={len(gen_keys)}",
                matched_columns=0,
                rows_compared=len(norm_gold),
            )

        col_count = len(gold_keys)

        # Build normalized gold tuples
        gold_tuples = [tuple(_normalize_value(r.get(k)) for k in gold_keys) for r in norm_gold]
        sorted_gold = sorted(gold_tuples, key=_row_sort_key)

        # Try column permutations of gen_keys
        # Heuristic 1: Try identical order if names match or single column
        candidate_permutations = list(itertools.permutations(gen_keys))
        # Prioritize matching key names if possible
        if set(gold_keys) == set(gen_keys):
            candidate_permutations.insert(0, tuple(gold_keys))

        for gen_perm in candidate_permutations:
            gen_tuples = [tuple(_normalize_value(r.get(k)) for k in gen_perm) for r in norm_gen]
            sorted_gen = sorted(gen_tuples, key=_row_sort_key)

            # Check if all elements match
            match = True
            for g_row, m_row in zip(sorted_gold, sorted_gen):
                for col_idx in range(col_count):
                    if not _values_match(g_row[col_idx], m_row[col_idx], atol=atol, rtol=rtol):
                        match = False
                        break
                if not match:
                    break

            if match:
                return ComparisonResult(
                    is_match=True,
                    reason="Semantic match with bijective column mapping",
                    matched_columns=col_count,
                    rows_compared=len(norm_gold),
                )

        return ComparisonResult(
            is_match=False,
            reason="Values do not match under any column permutation",
            matched_columns=0,
            rows_compared=len(norm_gold),
        )

    def compare_execution_results(
        self,
        gold_result: SQLExecutionResult,
        gen_result: SQLExecutionResult,
        atol: float = 1e-2,
        rtol: float = 1e-2,
    ) -> ComparisonResult:
        """Helper to compare two SQLExecutionResults directly."""
        if not gold_result.success or not gen_result.success:
            if not gold_result.success and not gen_result.success:
                return ComparisonResult(
                    is_match=False,
                    reason=f"Both executions failed: gold='{gold_result.error_message}', gen='{gen_result.error_message}'",
                    matched_columns=0,
                    rows_compared=0,
                )
            failed_which = "gold" if not gold_result.success else "gen"
            err = gold_result.error_message if not gold_result.success else gen_result.error_message
            return ComparisonResult(
                is_match=False,
                reason=f"Execution failed ({failed_which}): {err}",
                matched_columns=0,
                rows_compared=0,
            )

        # Convert rows and columns to list[dict]
        gold_dicts = [dict(zip(gold_result.columns, row)) for row in gold_result.rows]
        gen_dicts = [dict(zip(gen_result.columns, row)) for row in gen_result.rows]

        return self.compare(gold_dicts, gen_dicts, atol=atol, rtol=rtol)

    @staticmethod
    def _to_row_dicts(rows: list[dict[str, Any]] | list[list[Any]]) -> list[dict[str, Any]]:
        """Ensures input is a list of dictionaries."""
        if not rows:
            return []
        if isinstance(rows[0], dict):
            return rows  # type: ignore[return-value]
        # Otherwise list of lists
        return [
            {f"col_{i}": val for i, val in enumerate(row)}
            for row in rows  # type: ignore[union-attr]
        ]

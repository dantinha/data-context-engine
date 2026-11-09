import re
import unicodedata

from dce.models import (
    ClarificationOption,
    ClarificationRequest,
    MetadataCatalog,
    MetricMetadata,
)


def _normalize_text(text: str) -> str:
    """Lowercases, strips accents, replaces underscores/punctuation, and removes excess whitespace."""
    text = text.lower().replace("_", " ")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class SemanticClarifier:
    """Analyzes user questions to detect semantic ambiguity and resolve canonical business metrics."""

    def __init__(self, catalog: MetadataCatalog) -> None:
        self.catalog = catalog
        self._ambiguous_triggers: set[str] = self._collect_ambiguous_triggers()

    def _collect_ambiguous_triggers(self) -> set[str]:
        triggers = set()
        for g in self.catalog.ambiguity_groups:
            triggers.add(_normalize_text(g.id))
            triggers.add(_normalize_text(g.name))
            for t in g.trigger_terms:
                triggers.add(_normalize_text(t))
        return triggers

    def _extract_business_rule_reference(self, metric: MetricMetadata) -> str | None:
        if metric.description:
            match = re.search(r"RN-\d+", metric.description)
            if match:
                return match.group(0)
        for rule in self.catalog.business_rules:
            if metric.id in rule.description or (rule.rule_sql_condition and metric.id in rule.rule_sql_condition):
                return rule.id
        return None

    def _find_unambiguous_metric(self, question: str) -> str | None:
        norm_q = _normalize_text(question)
        if not norm_q:
            return None

        # Gather unambiguous terms mapped to metrics, sorted by term length descending
        candidates: list[tuple[str, str]] = []
        for metric in self.catalog.metrics:
            terms = [metric.name, metric.id] + metric.synonyms
            for term in terms:
                norm_term = _normalize_text(term)
                if not norm_term or len(norm_term) < 2:
                    continue
                # If term is an ambiguous trigger, skip it
                if norm_term in self._ambiguous_triggers:
                    continue
                candidates.append((norm_term, metric.id))

        # Sort candidate terms by length descending to match longest specific term first
        candidates.sort(key=lambda x: len(x[0]), reverse=True)

        for norm_term, metric_id in candidates:
            pattern = rf"\b{re.escape(norm_term)}\b"
            if re.search(pattern, norm_q):
                return metric_id

        return None

    def analyze(self, question: str, selected_metric_id: str | None = None) -> ClarificationRequest:
        """Analyzes the question for ambiguities or verifies the pre-selected metric.

        Args:
            question: The user natural language question.
            selected_metric_id: An optional explicitly chosen metric ID (e.g. from UI shortcut).

        Returns:
            ClarificationRequest with ambiguity status and candidate options if clarification is needed.
        """
        # 1. Pre-selected metric ID supplied
        if selected_metric_id is not None:
            metric = self.catalog.get_metric(selected_metric_id)
            if metric is None:
                raise ValueError(f"Métrica '{selected_metric_id}' não encontrada no catálogo.")
            return ClarificationRequest(
                needs_clarification=False,
                is_ambiguous=False,
                question=question,
                resolved_metric_id=selected_metric_id,
            )

        # 2. Check if question directly mentions an unambiguous metric
        direct_metric_id = self._find_unambiguous_metric(question)
        if direct_metric_id is not None:
            return ClarificationRequest(
                needs_clarification=False,
                is_ambiguous=False,
                question=question,
                resolved_metric_id=direct_metric_id,
            )

        # 3. Check for ambiguity group trigger
        group = self.catalog.find_ambiguity_group(question)
        if group is None:
            # Also check normalized version against ambiguity groups
            norm_q = _normalize_text(question)
            for g in self.catalog.ambiguity_groups:
                for trig in g.trigger_terms:
                    norm_trig = _normalize_text(trig)
                    if norm_trig and norm_trig in norm_q:
                        group = g
                        break
                if group:
                    break

        if group is not None:
            options: list[ClarificationOption] = []
            for cand_id in group.candidate_metrics:
                cand_metric = self.catalog.get_metric(cand_id)
                label = cand_metric.name if cand_metric else cand_id
                description = cand_metric.description if cand_metric else ""
                rule_ref = self._extract_business_rule_reference(cand_metric) if cand_metric else None
                options.append(
                    ClarificationOption(
                        metric_id=cand_id,
                        label=label,
                        description=description,
                        business_rule_reference=rule_ref,
                    )
                )

            return ClarificationRequest(
                needs_clarification=True,
                is_ambiguous=True,
                ambiguity_group_id=group.id,
                question=question,
                message=group.description,
                options=options,
            )

        # 4. No ambiguity detected and no specific metric identified
        return ClarificationRequest(
            needs_clarification=False,
            is_ambiguous=False,
            question=question,
            resolved_metric_id=None,
        )

    def clarify(self, question: str, selected_metric_id: str | None = None) -> ClarificationRequest:
        """Alias for analyze() to ensure backward compatibility."""
        return self.analyze(question, selected_metric_id=selected_metric_id)


from pathlib import Path

import yaml

from dce.models import (
    AmbiguityGroup,
    BusinessRule,
    ColumnMetadata,
    FewShotExample,
    ForbiddenJoin,
    JoinRelationship,
    MetadataCatalog,
    MetricMetadata,
    TableMetadata,
)


def load_metadata_catalog(metadata_dir: Path | str = Path("metadata")) -> MetadataCatalog:
    """Loads and validates the dbt schema catalog, semantic layer, and few-shot examples from YAML files."""
    metadata_path = Path(metadata_dir)
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata directory not found: {metadata_path}")

    # 1. Load schema.yml
    schema_file = None
    for candidate in ["schema.yml", "schema.yaml"]:
        p = metadata_path / candidate
        if p.exists():
            schema_file = p
            break

    tables: list[TableMetadata] = []
    if schema_file:
        with open(schema_file, "r", encoding="utf-8") as f:
            raw_schema = yaml.safe_load(f) or {}
            raw_tables = raw_schema.get("tables") or raw_schema.get("models") or []
            for t_dict in raw_tables:
                raw_cols = t_dict.get("columns", [])
                cols = [ColumnMetadata.model_validate(c) for c in raw_cols]
                pk_list = [c.name for c in cols if c.is_primary_key]
                tables.append(
                    TableMetadata(
                        name=t_dict.get("name", ""),
                        schema_name=t_dict.get("schema_name", "marts"),
                        description=t_dict.get("description", ""),
                        columns=cols,
                        primary_key=pk_list,
                    )
                )

    # 2. Load semantic_layer.yml
    semantic_file = None
    for candidate in ["semantic_layer.yml", "semantic_layer.yaml"]:
        p = metadata_path / candidate
        if p.exists():
            semantic_file = p
            break

    metrics: list[MetricMetadata] = []
    ambiguity_groups: list[AmbiguityGroup] = []
    business_rules: list[BusinessRule] = []
    allowed_joins: list[JoinRelationship] = []
    forbidden_joins: list[ForbiddenJoin] = []

    if semantic_file:
        with open(semantic_file, "r", encoding="utf-8") as f:
            raw_semantic = yaml.safe_load(f) or {}

            for m in raw_semantic.get("metrics", []):
                metrics.append(MetricMetadata.model_validate(m))

            for g in raw_semantic.get("ambiguity_groups", []):
                ambiguity_groups.append(AmbiguityGroup.model_validate(g))

            for r in raw_semantic.get("business_rules", []):
                business_rules.append(BusinessRule.model_validate(r))

            rel = raw_semantic.get("relationships", {})
            for aj in rel.get("allowed_joins", []):
                allowed_joins.append(JoinRelationship.model_validate(aj))

            for fj in rel.get("forbidden_joins", []):
                forbidden_joins.append(ForbiddenJoin.model_validate(fj))

    # 3. Load few_shot_examples.yml
    few_shot_file = None
    for candidate in ["few_shot_examples.yml", "few_shot_examples.yaml"]:
        p = metadata_path / candidate
        if p.exists():
            few_shot_file = p
            break

    few_shot_examples: list[FewShotExample] = []
    if few_shot_file:
        with open(few_shot_file, "r", encoding="utf-8") as f:
            raw_few_shot = yaml.safe_load(f) or {}
            raw_examples = raw_few_shot.get("few_shot_examples") or raw_few_shot.get("examples") or []
            for ex in raw_examples:
                few_shot_examples.append(FewShotExample.model_validate(ex))

    return MetadataCatalog(
        tables=tables,
        metrics=metrics,
        ambiguity_groups=ambiguity_groups,
        business_rules=business_rules,
        allowed_joins=allowed_joins,
        forbidden_joins=forbidden_joins,
        few_shot_examples=few_shot_examples,
    )

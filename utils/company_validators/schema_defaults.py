from typing import Dict, List


def get_required_top_level_fields(company: str, fields_config: Dict, fallback_fields: List[str]) -> List[str]:
    """
    Resolve required top-level fields by company config.
    Falls back to legacy defaults when config is unavailable.
    """
    if not isinstance(fields_config, dict):
        return fallback_fields

    fields = fields_config.get("fields")
    if not isinstance(fields, dict) or not fields:
        return fallback_fields

    # Keep source order from config for deterministic output.
    return list(fields.keys())

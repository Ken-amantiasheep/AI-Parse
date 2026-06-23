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
    # Sections with required: false are omitted (e.g. second_applicant_information).
    required = []
    for name, cfg in fields.items():
        if isinstance(cfg, dict) and cfg.get("required") is False:
            continue
        required.append(name)
    return required

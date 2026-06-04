from typing import Dict, Optional

from . import caa_auto, intact_auto, caa_property, intact_property


def run(generator, data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
    """Route post-processing by company while preserving current behavior."""
    company_upper = (getattr(generator, "company", "") or "").upper()

    if generator._should_apply_caa_dob_normalization(data):
        data = caa_auto.apply(generator, data, documents)

    if generator._is_intact_auto_company():
        data = intact_auto.apply(generator, data, documents)

    if company_upper == "CAA_PROPERTY":
        data = caa_property.apply(generator, data)
    elif company_upper == "INTACT_PROPERTY":
        data = intact_property.apply(generator, data, documents)

    return data

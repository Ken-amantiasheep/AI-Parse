from typing import Dict, Optional

from . import caa_auto, intact_auto, caa_property


def run(generator, data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
    """Route post-processing by company while preserving current behavior."""
    if generator._should_apply_caa_dob_normalization(data):
        data = caa_auto.apply(generator, data, documents)

    if generator._is_intact_company():
        data = intact_auto.apply(generator, data, documents)

    if generator.company.endswith("_property"):
        data = caa_property.apply(generator, data)

    return data

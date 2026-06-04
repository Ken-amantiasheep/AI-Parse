from typing import Dict


def apply(generator, data: Dict) -> Dict:
    """Run CAA property post-processing."""
    data = generator._normalize_property_names(data)
    if hasattr(generator, "_normalize_caa_property_structure"):
        return generator._normalize_caa_property_structure(data)
    return generator._normalize_property_structure(data)

from typing import Dict


def apply(generator, data: Dict) -> Dict:
    """Run property post-processing in existing order."""
    data = generator._normalize_property_names(data)
    return generator._normalize_property_structure(data)

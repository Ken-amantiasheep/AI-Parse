import json
import os
from typing import Dict


def load_company_routing(config_dir: str) -> Dict:
    routing_path = os.path.join(config_dir, "company_routing.json")
    if not os.path.exists(routing_path):
        return {}
    with open(routing_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_fields_config_name(company: str, routing: Dict) -> str:
    company_lower = company.lower()

    suffix_patterns = routing.get("company_suffix_patterns", [])
    for suffix in suffix_patterns:
        if company_lower.endswith(suffix):
            return f"{company_lower}_fields_config.json"

    legacy_aliases = routing.get("legacy_aliases", {})
    if company_lower in legacy_aliases:
        return legacy_aliases[company_lower]

    template = routing.get("default_template", "{company_lower}_fields_config.json")
    return template.format(company_lower=company_lower)

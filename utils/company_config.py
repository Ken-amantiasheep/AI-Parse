import json
import os
from typing import Any, Dict


def load_company_routing(config_dir: str) -> Dict:
    routing_path = os.path.join(config_dir, "company_routing.json")
    if not os.path.exists(routing_path):
        return {}
    with open(routing_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_fields_config_name(company: str, routing: Dict) -> str:
    company_lower = company.lower()

    legacy_aliases = routing.get("legacy_aliases", {})
    if company_lower in legacy_aliases:
        return legacy_aliases[company_lower]

    suffix_patterns = routing.get("company_suffix_patterns", [])
    for suffix in suffix_patterns:
        if company_lower.endswith(suffix):
            return f"{company_lower}_fields_config.json"

    template = routing.get("default_template", "{company_lower}_fields_config.json")
    return template.format(company_lower=company_lower)


def resolve_config_includes(node: Any, config_dir: str) -> Any:
    """Recursively expand ``{\"$include\": \"relative/path.json\"}`` markers."""
    if isinstance(node, dict):
        if set(node.keys()) == {"$include"}:
            include_path = os.path.join(config_dir, node["$include"])
            with open(include_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            return resolve_config_includes(loaded, config_dir)
        return {key: resolve_config_includes(value, config_dir) for key, value in node.items()}
    if isinstance(node, list):
        return [resolve_config_includes(item, config_dir) for item in node]
    return node


def load_fields_config(config_dir: str, config_name: str) -> Dict:
    fields_config_path = os.path.join(config_dir, config_name)
    with open(fields_config_path, "r", encoding="utf-8") as f:
        fields_config = json.load(f)
    return resolve_config_includes(fields_config, config_dir)

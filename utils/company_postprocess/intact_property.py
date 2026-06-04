import re
from typing import Dict, Optional

from .intact_auto import _is_missing


def _application_documents(documents: Optional[Dict[str, str]]) -> str:
    if not isinstance(documents, dict):
        return ""
    parts = []
    for doc_name, content in documents.items():
        if not isinstance(content, str):
            continue
        if "application" in str(doc_name).lower():
            parts.append(content)
    return "\n".join(parts)


def _extract_insured_since_from_application(documents: Optional[Dict[str, str]]) -> Optional[str]:
    """Extract property insured-since date from Application text."""
    text = _application_documents(documents)
    if not text.strip():
        return None

    patterns = [
        r"Property\s*[-–]?\s*Insured\s*Since[^\d]{0,40}(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"Insured\s*Without\s*Interruption\s*Since[^\d]{0,40}(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"Insured\s*With\s*Broker\s*Since[^\d]{0,40}(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s*Property\s*[-–]?\s*Insured\s*Since",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def _policy_effective_date(data: Dict, generator) -> Optional[str]:
    term = data.get("term")
    if not isinstance(term, dict):
        return None
    raw = term.get("policy_effective_date")
    if _is_missing(raw):
        return None
    return generator._format_to_yyyymmdd(str(raw).strip())


def _quote_documents(documents: Optional[Dict[str, str]]) -> str:
    if not isinstance(documents, dict):
        return ""
    parts = []
    for doc_name, content in documents.items():
        if not isinstance(content, str):
            continue
        if "quote" in str(doc_name).lower():
            parts.append(content)
    return "\n".join(parts)


def _extract_smoke_free_household(documents: Optional[Dict[str, str]]) -> Optional[str]:
    """Return 'Yes' or 'No' for Smoke-Free Household (not smokers_reside)."""
    text = _quote_documents(documents)
    if not text.strip():
        return None

    patterns = [
        r"Smoke[- ]Free\s*Household[^\w]{0,30}(Yes|No)\b",
        r"(Yes|No)\b[^\w]{0,30}Smoke[- ]Free\s*Household",
        r"Smoke[- ]Free\s*Household\s*[\r\n]+\s*(Yes|No)\b",
        r"(Yes|No)\b\s*[\r\n]+\s*Smoke[- ]Free\s*Household",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip().capitalize()
    return None


def _smokers_reside_from_smoke_free(smoke_free: str) -> Optional[str]:
    normalized = smoke_free.strip().lower()
    if normalized == "yes":
        return "No"
    if normalized == "no":
        return "Yes"
    return None


def _normalize_risk_smokers(data: Dict, documents: Optional[Dict[str, str]]) -> None:
    smoke_free = _extract_smoke_free_household(documents)
    if smoke_free is None:
        return

    smokers_value = _smokers_reside_from_smoke_free(smoke_free)
    if smokers_value is None:
        return

    risk = data.get("risk")
    if isinstance(risk, dict):
        risk_items = [risk]
    elif isinstance(risk, list):
        risk_items = [item for item in risk if isinstance(item, dict)]
    else:
        return

    for item in risk_items:
        if "smokers_reside_at_this_location" in item:
            item["smokers_reside_at_this_location"] = smokers_value


def _is_no_prior_insurer(previous_insurer) -> bool:
    return isinstance(previous_insurer, str) and previous_insurer.strip().lower() == "no prior insurer"


def _normalize_insureds(data: Dict, generator, documents: Optional[Dict[str, str]], insureds: Dict) -> None:
    previous_insurer = insureds.get("previous_insurer")
    effective = _policy_effective_date(data, generator)

    if _is_no_prior_insurer(previous_insurer):
        for key in (
            "number_of_years_with_previous_insurer",
            "previous_insurer_policy_number",
            "previous_insurer_expiry_date",
        ):
            insureds.pop(key, None)

        if not _is_missing(effective):
            insureds["insured_with_broker_since"] = effective
            insureds["insured_without_interruption_since"] = effective
        return

    app_date = _extract_insured_since_from_application(documents)
    normalized = None
    if isinstance(app_date, str) and app_date.strip():
        normalized = generator._format_to_yyyymmdd(app_date.strip())
    if _is_missing(normalized):
        current = insureds.get("insured_with_broker_since")
        if isinstance(current, str) and current.strip():
            normalized = generator._format_to_yyyymmdd(current.strip())
    if _is_missing(normalized) and not _is_missing(effective):
        normalized = effective

    if not _is_missing(normalized):
        insureds["insured_with_broker_since"] = normalized
        insureds["insured_without_interruption_since"] = normalized


def apply(generator, data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
    """Run Intact property post-processing without CAA-specific rules."""
    data = generator._normalize_property_names(data)
    data = generator._normalize_property_structure(data)
    insureds = data.get("insureds")
    if not isinstance(insureds, dict):
        insureds = {}
        data["insureds"] = insureds

    insureds.pop("automobile_insurance_cancelled_or_refused_in_last_3_years", None)
    insureds.pop("ubi_consent", None)

    _normalize_insureds(data, generator, documents, insureds)
    _normalize_risk_smokers(data, documents)

    if hasattr(generator, "_merge_missing_property_coverages_from_quote"):
        data = generator._merge_missing_property_coverages_from_quote(data, documents)
    return data

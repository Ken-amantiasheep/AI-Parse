import re
import json
from typing import Dict, Optional
from datetime import datetime, date
from urllib import parse, request


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _beacon_interest(stage: str, **details) -> None:
    """Diagnostic beacon for tracing risk[].interest / has_loan pipeline (grep: BEACON:interest)."""
    parts = [f"[BEACON:interest] {stage}"]
    for key, value in details.items():
        parts.append(f"{key}={value}")
    print(" | ".join(parts))


def _summarize_risk_interest(data: Dict) -> str:
    risks = data.get("risk")
    if isinstance(risks, dict):
        risks = [risks]
    if not isinstance(risks, list):
        return "(no risk list)"
    chunks = []
    for idx, risk in enumerate(risks):
        if isinstance(risk, dict):
            chunks.append(f"risk[{idx}]={risk.get('interest')!r}")
    return "; ".join(chunks) if chunks else "(empty risk list)"


def _snippet_around(text: str, needle: str, radius: int = 100) -> str:
    if not isinstance(text, str) or not text or not needle:
        return "(empty)"
    idx = text.upper().find(needle.upper())
    if idx < 0:
        return f"(not found: {needle!r})"
    start = max(0, idx - 40)
    end = min(len(text), idx + radius)
    snippet = text[start:end].replace("\n", "\\n")
    return repr(snippet)


def _summarize_documents_for_interest(documents: Optional[Dict[str, str]]) -> str:
    if not isinstance(documents, dict):
        return f"type={type(documents).__name__}"
    if not documents:
        return "keys=(none)"
    parts = []
    for key, value in documents.items():
        if isinstance(value, str):
            parts.append(f"{key}:{len(value)}ch")
        else:
            parts.append(f"{key}:{type(value).__name__}")
    return "keys=[" + ", ".join(parts) + "]"


# Staging keys on driver[i] (i>=1); promoted to root driver_{i+1}_information / driver_{i+1}_address.
_DRIVER_IDENTITY_KEYS = (
    "last_name",
    "first_name",
    "gender",
    "date_of_birth",
    "marital_status",
)
_APPLICANT_ADDRESS_KEYS = ("postal_code", "unit_number", "full_address")
_APPLICANT_CONTACT_KEYS = _APPLICANT_ADDRESS_KEYS + ("phone", "email")
_DRIVER_ADDRESS_KEYS = _APPLICANT_ADDRESS_KEYS
_ASSIGNMENT_COMMON_KEYS = (
    "type_of_use",
    "km_toward_work",
    "annual_km",
    "annual_business_km",
    "automobile_rented_or_leased_to_others",
    "automobile_used_to_carry_passengers_for_compensation_or_hire",
    "automobile_carry_explosives_or_radioactive_materials",
)


def _merge_root_address_into_applicant_information(data: Dict) -> Dict:
    """Hoist legacy root `address` (and phone/email if nested there) into applicant_information."""
    if not isinstance(data, dict):
        return data

    legacy_address = data.pop("address", None)
    if not isinstance(legacy_address, dict) or not legacy_address:
        return data

    applicant = data.get("applicant_information")
    if not isinstance(applicant, dict):
        applicant = {}
        data["applicant_information"] = applicant

    for key in _APPLICANT_ADDRESS_KEYS + ("phone", "email"):
        value = legacy_address.get(key)
        if not _is_missing(value) and _is_missing(applicant.get(key)):
            applicant[key] = value

    _normalize_applicant_phone(applicant)
    return data


def _normalize_applicant_phone(applicant: Dict) -> None:
    """Strip phone to digits only (no hyphens, spaces, or other separators)."""
    if not isinstance(applicant, dict):
        return
    phone = applicant.get("phone")
    if _is_missing(phone):
        return
    digits = re.sub(r"\D", "", str(phone))
    if digits:
        applicant["phone"] = digits


def _normalize_intact_applicant_information(data: Dict) -> Dict:
    if not isinstance(data, dict):
        return data
    applicant = data.get("applicant_information")
    if isinstance(applicant, dict):
        _normalize_applicant_phone(applicant)
        _fill_unit_number_from_address(applicant)
    second = data.get("second_applicant_information")
    if isinstance(second, dict):
        _normalize_applicant_phone(second)
        if isinstance(applicant, dict):
            if _is_missing(second.get("unit_number")) and not _is_missing(applicant.get("unit_number")):
                second["unit_number"] = applicant["unit_number"]
        _fill_unit_number_from_address(second)
    return data


def _extract_unit_number_from_address_text(text: str) -> Optional[str]:
    """Best-effort unit from a single address line when not extracted separately."""
    if not isinstance(text, str):
        return None
    value = text.strip()
    if not value:
        return None

    leading = re.match(r"^(\d+)\s*-\s*\d", value)
    if leading:
        return leading.group(1)

    labeled = re.search(
        r"(?i)\b(?:unit|suite|ste|apt|apartment|#)\s*\.?\s*([A-Za-z0-9-]+)",
        value,
    )
    if labeled:
        return labeled.group(1)
    return None


def _fill_unit_number_from_address(record: Dict) -> None:
    if not isinstance(record, dict) or not _is_missing(record.get("unit_number")):
        return
    unit = _extract_unit_number_from_address_text(record.get("full_address"))
    if unit:
        record["unit_number"] = unit


def _strip_parenthetical_suffix(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()


_SECTION1_HEADER_LABEL_PATTERN = re.compile(
    r"(?i)^\s*(?:1\s*[\.\):\-]?\s*)?applicant'?s?\s+(?:full\s+)?name"
    r"|^name\s+and\s+address\s*$"
)

_SECTION1_START_PATTERN = re.compile(
    r"(?i)applicant'?s?\s+(?:full\s+)?name|name\s+and\s+address"
)
_SECTION1_END_PATTERN = re.compile(
    r"(?i)(?:^|\n)\s*2\s*[\.\):\-]?\s*(?:policy\s+period|length\s+of\s+(?:policy|contract))"
    r"|(?:^|\n)\s*3\s*[\.\):\-]?\s*described\s+automobile"
)

_SECTION1_NAME_FIELD_STOP_PATTERN = re.compile(
    r"(?i)^\s*(?:postal\s+code|phone\s+no|email\b|work\s*\(|home\s*\(|cell\s*\()"
)
_STREET_OR_UNIT_LINE_PATTERN = re.compile(r"^\s*\d")
_CITY_PROVINCE_LINE_PATTERN = re.compile(
    r",\s*(?:ON|QC|BC|AB|MB|SK|NS|NB|PE|NL|NT|NU|YT)\s*$",
    flags=re.IGNORECASE,
)


def _get_application_form_only_text(documents: Optional[Dict[str, str]]) -> str:
    """Application_Form text only — never Quote/MVR/lienholder fallbacks."""
    if not isinstance(documents, dict):
        return ""
    parts = []
    for key, value in documents.items():
        if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
            continue
        if "application" in key.strip().lower():
            parts.append(value)
    return "\n".join(parts)


def _extract_application_section1_text(app_text: str) -> str:
    """Return Application Section 1 block only (applicant name/address — not later sections)."""
    if not isinstance(app_text, str) or not app_text.strip():
        return ""

    start_match = _SECTION1_START_PATTERN.search(app_text)
    if not start_match:
        return "\n".join(app_text.splitlines()[:25])

    section = app_text[start_match.start() :]
    end_match = _SECTION1_END_PATTERN.search(section)
    if end_match:
        section = section[: end_match.start()]
    return section[:1200]


def _line_looks_like_address_not_name(line: str) -> bool:
    if not isinstance(line, str) or not line.strip():
        return False
    if _SECTION1_NAME_FIELD_STOP_PATTERN.match(line):
        return True
    if _STREET_OR_UNIT_LINE_PATTERN.match(line):
        return True
    if _CITY_PROVINCE_LINE_PATTERN.search(line):
        return True
    return False


def _extract_section1_name_field_text(section1: str) -> str:
    """
    Applicant name VALUE from Section 1 'Name and Address' box — the line(s) a
    human reads above the street address, not headers or later form sections.
    """
    if not isinstance(section1, str) or not section1.strip():
        return ""

    lines = [ln.strip() for ln in section1.splitlines()]
    capture = False
    name_lines = []

    for line in lines:
        if not line:
            continue
        if re.match(r"(?i)^name\s+and\s+address\s*$", line):
            capture = True
            continue
        if not capture:
            if _SECTION1_HEADER_LABEL_PATTERN.match(line):
                continue
            continue
        if _line_looks_like_address_not_name(line):
            break
        if re.match(r"(?i)^(?:name|address)\s*$", line):
            continue
        name_lines.append(line)
        if len(name_lines) >= 2 and "&" not in " ".join(name_lines):
            break

    return " ".join(name_lines).strip()


def _get_section1_name_field_text(documents: Optional[Dict[str, str]]) -> str:
    app_text = _get_application_form_only_text(documents)
    if not app_text:
        return ""
    return _extract_section1_name_field_text(_extract_application_section1_text(app_text))


def _parse_dual_names_from_section1_name_field(name_field: str):
    """
    Intact OAF prints two applicants on one name-box line joined by '&'.
    Only parse that box — never scan Accident Benefits or other sections.
    """
    if not isinstance(name_field, str) or "&" not in name_field:
        return None
    text = _strip_parenthetical_suffix(name_field.strip())
    parts = re.split(r"\s*&\s*", text, maxsplit=1)
    if len(parts) != 2:
        return None
    left = _strip_parenthetical_suffix(parts[0].strip())
    right = _strip_parenthetical_suffix(parts[1].strip())
    if not left or not right:
        return None
    parsed1 = _parse_mvr_name(left)
    parsed2 = _parse_mvr_name(right)
    if not parsed1 or not parsed2:
        return None
    return left, right


def _extract_dual_applicant_names_from_application(documents: Optional[Dict[str, str]]):
    """Return (name1_raw, name2_raw) only when Section 1 name box lists two people."""
    name_field = _get_section1_name_field_text(documents)
    if not name_field:
        return None
    return _parse_dual_names_from_section1_name_field(name_field)


def _second_applicant_grounded_in_section1_name_field(second: Dict, name_field: str) -> bool:
    """Second applicant must appear in the Section 1 name box (not hallucinated elsewhere)."""
    if not isinstance(second, dict) or not isinstance(name_field, str) or not name_field.strip():
        return False
    upper = name_field.upper()
    for key in ("last_name", "first_name"):
        value = second.get(key)
        if isinstance(value, str) and value.strip() and value.strip().upper() in upper:
            return True
    return False


def _application_has_dual_applicant_names(documents: Optional[Dict[str, str]]) -> bool:
    """True only when Section 1 name box lists two applicants."""
    return _extract_dual_applicant_names_from_application(documents) is not None


def _sync_shared_applicant_contact_fields(primary: Dict, secondary: Dict) -> None:
    """Copy shared household address/phone/email from primary to secondary when missing."""
    if not isinstance(primary, dict) or not isinstance(secondary, dict):
        return
    for key in _APPLICANT_CONTACT_KEYS:
        if _is_missing(secondary.get(key)) and not _is_missing(primary.get(key)):
            secondary[key] = primary[key]


def _remove_second_applicant_unless_dual_on_application(
    data: Dict, documents: Optional[Dict[str, str]]
) -> Dict:
    """
    Keep second_applicant_information only when Section 1 'Name and Address' name
    box lists two applicants. LLM hallucinations (coverage text, extra drivers)
    are dropped when the name box does not contain that second person.
    """
    if not isinstance(data, dict):
        return data

    name_field = _get_section1_name_field_text(documents)
    dual = _parse_dual_names_from_section1_name_field(name_field)

    if not dual:
        if "second_applicant_information" in data:
            print(
                "[INFO] Removed second_applicant_information — Section 1 name box "
                f"lists one applicant only: {name_field!r}"
            )
        data.pop("second_applicant_information", None)
        return data

    second = data.get("second_applicant_information")
    if isinstance(second, dict) and not _second_applicant_grounded_in_section1_name_field(
        second, name_field
    ):
        print(
            "[INFO] Removed second_applicant_information — second person not in "
            f"Section 1 name box {name_field!r}"
        )
        data.pop("second_applicant_information", None)
    return data


def _apply_dual_applicant_from_application(data: Dict, documents: Optional[Dict[str, str]]) -> Dict:
    """
    When Application Section 1 lists two names joined by '&', populate
    applicant_information (first) and second_applicant_information (second).
    Otherwise remove second_applicant_information.
    """
    if not isinstance(data, dict):
        return data

    data = _remove_second_applicant_unless_dual_on_application(data, documents)

    dual = _extract_dual_applicant_names_from_application(documents)
    if not dual:
        return data

    name1_raw, name2_raw = dual
    parsed1 = _parse_mvr_name(name1_raw)
    parsed2 = _parse_mvr_name(name2_raw)
    if not parsed1 or not parsed2:
        data.pop("second_applicant_information", None)
        return data

    applicant = data.get("applicant_information")
    if not isinstance(applicant, dict):
        applicant = {}
        data["applicant_information"] = applicant

    second = data.get("second_applicant_information")
    if not isinstance(second, dict):
        second = {}
        data["second_applicant_information"] = second

    applicant["last_name"] = parsed1[0]
    applicant["first_name"] = parsed1[1]
    second["last_name"] = parsed2[0]
    second["first_name"] = parsed2[1]
    _sync_shared_applicant_contact_fields(applicant, second)

    print(
        "[INFO] Split dual Intact Auto applicants from Application: "
        f"{parsed1[1]} {parsed1[0]} & {parsed2[1]} {parsed2[0]}"
    )
    return data


def _apply_mvr_name_to_second_applicant(data: Dict, documents: Optional[Dict[str, str]]) -> Dict:
    """Overwrite second_applicant_information names from matching MVR when dual-applicant."""
    if not isinstance(data, dict):
        return data

    second = data.get("second_applicant_information")
    if not isinstance(second, dict):
        return data

    mvr_index = _build_mvr_name_index(documents)
    if not mvr_index:
        return data

    applicant_info = data.get("applicant_information") if isinstance(data.get("applicant_information"), dict) else {}
    primary_last = applicant_info.get("last_name")
    primary_first = applicant_info.get("first_name")

    # Prefer MVR whose name matches the second applicant but not the primary applicant.
    second_last = second.get("last_name")
    second_first = second.get("first_name")
    sl = second_last.strip().upper() if isinstance(second_last, str) else ""
    sf = second_first.strip().upper() if isinstance(second_first, str) else ""
    pl = primary_last.strip().upper() if isinstance(primary_last, str) else ""
    pf = primary_first.strip().upper() if isinstance(primary_first, str) else ""

    for entry in mvr_index:
        mvr_last, mvr_first = entry[1], entry[2]
        ml = mvr_last.strip().upper() if isinstance(mvr_last, str) else ""
        mf = mvr_first.strip().upper() if isinstance(mvr_first, str) else ""
        if sl and sf and ml == sl and mf == sf and not (ml == pl and mf == pf):
            second["last_name"] = mvr_last
            second["first_name"] = mvr_first
            return data
        upper_content = entry[4]
        if sl and sf and sl in upper_content and sf in upper_content:
            if not (pl and pf and pl in upper_content and pf in upper_content):
                second["last_name"] = mvr_last
                second["first_name"] = mvr_first
                return data

    drivers = data.get("driver")
    if isinstance(drivers, list) and len(drivers) >= 2 and isinstance(drivers[1], dict):
        parsed = _find_mvr_name_for_driver(
            drivers[1],
            second,
            is_primary=True,
            driver_idx=1,
            mvr_index=mvr_index,
        )
        if parsed:
            last_name, first_name = parsed
            if _is_valid_mvr_name_part(last_name) and _is_valid_mvr_name_part(first_name):
                if not (
                    isinstance(primary_last, str)
                    and isinstance(primary_first, str)
                    and last_name.strip().upper() == pl
                    and first_name.strip().upper() == pf
                ):
                    second["last_name"] = last_name
                    second["first_name"] = first_name

    return data


def _promote_additional_driver_identity_blocks(data: Dict) -> Dict:
    """
    For Intact Auto, second and subsequent drivers get root-level blocks matching
    applicant_information shape: driver_2_information, driver_2_address, etc.
    Values are taken from the corresponding driver[] element, then those keys are removed
    from the driver object. The first driver must not carry these staging keys.
    """
    if not isinstance(data, dict):
        return data

    drivers = data.get("driver")
    if not isinstance(drivers, list):
        return data

    applicant = data.get("applicant_information") if isinstance(data.get("applicant_information"), dict) else {}

    # Strip staging keys from first driver if the model duplicated them.
    if drivers and isinstance(drivers[0], dict):
        for k in _DRIVER_IDENTITY_KEYS + _DRIVER_ADDRESS_KEYS:
            drivers[0].pop(k, None)

    for idx in range(1, len(drivers)):
        d = drivers[idx]
        if not isinstance(d, dict):
            continue
        n = idx + 1
        info_key = f"driver_{n}_information"
        addr_key = f"driver_{n}_address"

        info = {}
        for k in _DRIVER_IDENTITY_KEYS:
            v = d.get(k)
            if not _is_missing(v):
                info[k] = v

        addr = {}
        for k in _DRIVER_ADDRESS_KEYS:
            v = d.get(k)
            if not _is_missing(v):
                addr[k] = v

        if not addr.get("postal_code") and not _is_missing(applicant.get("postal_code")):
            addr["postal_code"] = applicant["postal_code"]
        if not addr.get("full_address") and not _is_missing(applicant.get("full_address")):
            addr["full_address"] = applicant["full_address"]

        if info:
            data[info_key] = info
        if addr:
            data[addr_key] = addr

        for k in _DRIVER_IDENTITY_KEYS + _DRIVER_ADDRESS_KEYS:
            d.pop(k, None)

    # Drop stale driver_N_* from a previous extraction if driver count shrank.
    for n in range(2, 30):
        if n > len(drivers):
            data.pop(f"driver_{n}_information", None)
            data.pop(f"driver_{n}_address", None)

    return data


def _get_quote_document_text(documents: Optional[Dict[str, str]]) -> Optional[str]:
    if not isinstance(documents, dict):
        return None
    for key, value in documents.items():
        if isinstance(key, str) and key.strip().lower() == "quote" and isinstance(value, str) and value.strip():
            return value
    return None


def _get_application_document_text(documents: Optional[Dict[str, str]]) -> str:
    if not isinstance(documents, dict):
        return ""
    parts = []
    for key, value in documents.items():
        if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
            continue
        if "application" in key.strip().lower():
            parts.append(value)
    if parts:
        return "\n".join(parts)

    # Some PDF bundles place the lienholder table outside Application_Form extract.
    for value in documents.values():
        if not isinstance(value, str) or not value.strip():
            continue
        if re.search(r"lienholder\s+name", value, flags=re.IGNORECASE):
            parts.append(value)
    if parts:
        return "\n".join(parts)

    for value in documents.values():
        if not isinstance(value, str) or not value.strip():
            continue
        upper = value.upper()
        if any(name.upper() in upper for name in _FINANCE_COMPANY_OPTIONS):
            parts.append(value)
    return "\n".join(parts)


_FINANCE_COMPANY_OPTIONS = (
    "Acura Financial Services",
    "Alphera Financial Services",
    "Audi Finance Services",
    "Bank of Montreal",
    "Banque Nationale Du Canada",
    "Banque Royal Prets Auto",
    "BMW Financial Services",
    "CIBC",
    "Edenpark",
    "FCA Canada Inc.",
    "Fédération des Caisses Desjardins du Québec",
    "Ford Credit Canada",
    "General Bank Of Canada",
    "Genesis Finance",
    "GM Financial",
    "Honda Finance Services",
    "Hyundai Motor Finance",
    "IA Financement Auto",
    "Kia Finance",
    "Lendcare Capital Inc.",
    "Libro Credit Union",
    "Lincoln Automotive Financial Services",
    "Manulife Bank Of Canada",
    "Mercedes-Benz Financial Services",
    "Mini Financial Services Canada",
    "Nissan Canada Inc.",
    "Porsche Financial Services Canada",
    "Royal Bank of Canada",
    "Scotia Dealer Advantage",
    "Services Financiers Mini Cooper",
    "TD Auto Finance",
    "Toyota Credit Canada",
    "Tricor Lease Finance Corp.",
    "Volkswagen Credit Canada Inc.",
)
_CANADIAN_POSTAL_PATTERN = re.compile(
    r"([A-Za-z]\d[A-Za-z])\s*(\d[A-Za-z]\d)",
)
_OAF_LIENHOLDER_ROW_PATTERN = re.compile(r"^(\d+)\.\s*(.+)$")
_MAX_LIENHOLDER_AUTO_NO = 6


def _looks_like_person_name(candidate: str) -> bool:
    """Reject 'LAST, FIRST' applicant/driver names mistaken for lienholder companies."""
    if not isinstance(candidate, str):
        return False
    text = candidate.strip()
    if re.match(r"^[A-Z][A-Za-z'\-]+,\s*[A-Z][A-Za-z'\-]+", text):
        return True
    if re.search(r"\b(?:19|20)\d{2}\s+\d{1,2}\s+\d{1,2}\b", text):
        return True
    if re.search(r"\b[A-Z]\d{6,}\b", text):
        return True
    return False


def _match_finance_company(text: str) -> Optional[str]:
    if not isinstance(text, str) or not text.strip():
        return None
    upper = text.upper()
    for name in sorted(_FINANCE_COMPANY_OPTIONS, key=len, reverse=True):
        if name.upper() in upper:
            return name
    # Unknown lender: only accept when a PO Box mailing address is present (not DOB/licence noise).
    if not re.search(r"(?:PO\s*Box|P\.?O\.?\s*Box)", text, flags=re.IGNORECASE):
        return None
    po_box_match = re.match(
        r"^(.+?)\s*(?:-\s*)?(?:PO\s*Box|P\.?O\.?\s*Box)",
        text,
        flags=re.IGNORECASE,
    )
    if not po_box_match:
        return None
    candidate = po_box_match.group(1).strip(" ,-")
    if not candidate or not re.search(r"[A-Za-z]", candidate):
        return None
    if _looks_like_person_name(candidate):
        return None
    return candidate


def _extract_canadian_postal_code(text: str) -> Optional[str]:
    if not isinstance(text, str):
        return None
    match = _CANADIAN_POSTAL_PATTERN.search(text)
    if not match:
        return None
    return f"{match.group(1)}{match.group(2)}".upper()


def _split_lienholder_company_address(line_body: str, company_name: str):
    remainder = line_body
    if company_name:
        idx = line_body.upper().find(company_name.upper())
        if idx >= 0:
            remainder = line_body[idx + len(company_name) :].strip(" ,-")

    postal_code = _extract_canadian_postal_code(remainder)
    address = remainder
    if postal_code:
        address = _CANADIAN_POSTAL_PATTERN.sub("", remainder, count=1).strip(" ,")
    unit_number = _extract_unit_number_from_address_text(address)
    if unit_number:
        address = re.sub(
            rf"(?i)^\s*{re.escape(unit_number)}\s*-\s*",
            "",
            address,
            count=1,
        )
        address = re.sub(
            rf"(?i)\b(?:unit|suite|ste|apt|apartment|#)\s*\.?\s*{re.escape(unit_number)}\b[,]?\s*",
            "",
            address,
            count=1,
        )
    address = re.sub(r",\s*,", ", ", address)
    address = re.sub(r"\s+", " ", address).strip(" ,")
    return address, postal_code, unit_number


def _parse_lienholder_row_body(body: str) -> Optional[Dict]:
    if not isinstance(body, str):
        return None
    text = body.strip()
    if len(text) < 4 or not re.search(r"[A-Za-z]", text):
        return None
    company_name = _match_finance_company(text)
    if not company_name:
        return None
    address, postal_code, unit_number = _split_lienholder_company_address(text, company_name)
    if not postal_code and not re.search(r"(?:PO\s*Box|P\.?O\.?\s*Box)", text, flags=re.IGNORECASE):
        return None
    if _looks_like_person_name(company_name):
        return None
    parsed = {
        "company_name": company_name,
        "address": address,
        "postal_code": postal_code or "",
    }
    if unit_number:
        parsed["unit_number"] = unit_number
    return parsed


def _store_lienholder_row(result: Dict[int, Dict], auto_no: int, body: str, parsed: Dict) -> None:
    """Prefer authoritative finance-company rows when the same auto no appears twice."""
    if auto_no in result:
        existing = result[auto_no]
        existing_known = existing.get("company_name") in _FINANCE_COMPANY_OPTIONS
        new_known = parsed.get("company_name") in _FINANCE_COMPANY_OPTIONS
        if existing_known and not new_known:
            return
        if existing.get("postal_code") and not parsed.get("postal_code"):
            return
    result[auto_no] = parsed


def _is_lienholder_table_header(line: str) -> bool:
    lower = line.lower()
    return ("auto no" in lower and "lienholder" in lower) or (
        "lienholder" in lower and "postal address" in lower
    )


def _is_oaf_auto_no_only_line(line: str) -> bool:
    return line.strip().lower() in {"no.", "no"}


def _is_next_lienholder_row_line(line: str) -> bool:
    return bool(_OAF_LIENHOLDER_ROW_PATTERN.match(line or "")) or bool(
        re.fullmatch(r"\d+", line or "")
    )


def _is_lienholder_section_boundary(line: str) -> bool:
    if not line:
        return True
    if _is_lienholder_table_header(line):
        return True
    return bool(re.match(r"^(AUTOMOBILE|DRIVER|VEHICLE|COVERAGE|DECLARATION)\b", line, flags=re.IGNORECASE))


def _find_lienholder_section_block(application_text: str) -> str:
    # OAF 1 Section 3: PDF often splits header across lines
    #   "Auto Lienholder Name & Postal Address" / "No." / "1. TD Auto Finance - ..."
    oaf_marker = re.search(
        r"Auto\s+Lienholder\s+Name\s*&\s*Postal\s+Address",
        application_text,
        flags=re.IGNORECASE,
    )
    if oaf_marker:
        return application_text[oaf_marker.start() : oaf_marker.start() + 1200]

    marker = re.search(
        r"Lienholder[\s\S]{0,80}?(?:Postal\s+Address|Name\s*&)",
        application_text,
        flags=re.IGNORECASE,
    )
    if not marker:
        marker = re.search(r"Auto\s+No\.?\s*[\s\S]{0,40}?Lienholder", application_text, flags=re.IGNORECASE)
    if marker:
        return application_text[marker.start() : marker.start() + 2000]

    # PDF extract may drop the section header but keep finance-company rows.
    upper = application_text.upper()
    for name in sorted(_FINANCE_COMPANY_OPTIONS, key=len, reverse=True):
        if name.upper() in upper:
            idx = upper.find(name.upper())
            return application_text[max(0, idx - 200) : idx + 800]
    return ""


def _extract_lienholders_by_auto_no(application_text: str) -> Dict[int, Dict]:
    """
    Parse Application table: Auto No. | Lienholder Name & Postal Address.

    Supports common PDF text layouts:
      - Same line:  '1 TD Auto Finance PO Box 4086, ...'
      - Split lines: '1' then 'TD Auto Finance PO Box 4086, ...'
      - Fallback: any finance-company line in the lienholder section
    """
    if not isinstance(application_text, str) or not application_text.strip():
        return {}

    block = _find_lienholder_section_block(application_text)
    if not block:
        return {}

    result: Dict[int, Dict] = {}
    lines = [line.strip() for line in block.splitlines()]

    # Pass 0 (OAF PP): "1. TD Auto Finance - PO Box 4086, ..."
    for line in lines:
        if not line or _is_lienholder_table_header(line) or _is_oaf_auto_no_only_line(line):
            continue
        match = _OAF_LIENHOLDER_ROW_PATTERN.match(line)
        if not match:
            continue
        auto_no = int(match.group(1))
        if auto_no < 1 or auto_no > _MAX_LIENHOLDER_AUTO_NO:
            continue
        body = match.group(2)
        parsed = _parse_lienholder_row_body(body)
        if parsed:
            _store_lienholder_row(result, auto_no, body, parsed)

    # Pass 1: AutoNo and body on the same line (no dot).
    for line in lines:
        if not line or _is_lienholder_table_header(line):
            continue
        match = re.match(r"^(\d+)\s+(.+)$", line)
        if not match:
            continue
        auto_no = int(match.group(1))
        if auto_no < 1 or auto_no > _MAX_LIENHOLDER_AUTO_NO or auto_no in result:
            continue
        body = match.group(2)
        parsed = _parse_lienholder_row_body(body)
        if parsed:
            _store_lienholder_row(result, auto_no, body, parsed)

    # Pass 2: AutoNo alone on one line, body on following line(s) — strict window only.
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.fullmatch(r"\d+", line or ""):
            auto_no = int(line)
            if 1 <= auto_no <= _MAX_LIENHOLDER_AUTO_NO and auto_no not in result:
                body_parts = []
                j = i + 1
                while j < len(lines) and len(body_parts) < 4:
                    nxt = lines[j].strip()
                    if not nxt:
                        j += 1
                        continue
                    if _is_next_lienholder_row_line(nxt) or _is_oaf_auto_no_only_line(nxt):
                        break
                    if _is_lienholder_section_boundary(nxt):
                        break
                    body_parts.append(nxt)
                    j += 1
                if body_parts:
                    body = " ".join(body_parts)
                    parsed = _parse_lienholder_row_body(body)
                    if parsed:
                        _store_lienholder_row(result, auto_no, body, parsed)
                i = j
                continue
        i += 1

    # Pass 3: finance-company rows without leading auto no (assign in order).
    if not result:
        next_auto_no = 1
        for line in lines:
            if not line or _is_lienholder_table_header(line) or _is_oaf_auto_no_only_line(line):
                continue
            if re.fullmatch(r"\d+", line) or _OAF_LIENHOLDER_ROW_PATTERN.match(line):
                continue
            if _is_lienholder_section_boundary(line):
                break
            parsed = _parse_lienholder_row_body(line)
            if parsed and next_auto_no <= _MAX_LIENHOLDER_AUTO_NO:
                result[next_auto_no] = parsed
                next_auto_no += 1

    # Pass 4: multi-line cell — finance company on one line, address/postal on following lines.
    if not result:
        i = 0
        next_auto_no = 1
        while i < len(lines):
            line = lines[i]
            if not line or _is_lienholder_table_header(line) or _is_oaf_auto_no_only_line(line):
                i += 1
                continue
            if re.fullmatch(r"\d+", line) or _OAF_LIENHOLDER_ROW_PATTERN.match(line):
                i += 1
                continue
            if _is_lienholder_section_boundary(line):
                break
            if _match_finance_company(line):
                body_parts = [line]
                j = i + 1
                while j < len(lines) and len(body_parts) < 4:
                    nxt = lines[j].strip()
                    if (
                        not nxt
                        or _is_next_lienholder_row_line(nxt)
                        or _is_oaf_auto_no_only_line(nxt)
                        or _is_lienholder_section_boundary(nxt)
                    ):
                        break
                    if _match_finance_company(nxt) and not _extract_canadian_postal_code(" ".join(body_parts)):
                        break
                    body_parts.append(nxt)
                    j += 1
                parsed = _parse_lienholder_row_body(" ".join(body_parts))
                if parsed and next_auto_no <= _MAX_LIENHOLDER_AUTO_NO:
                    result[next_auto_no] = parsed
                    next_auto_no += 1
                i = j
                continue
            i += 1

    return result


def _vehicle_is_leased_on_application(
    application_text: str, vehicle_index: int
) -> bool:
    """Detect lease from Application Section 3 — not from Quote."""
    if not isinstance(application_text, str) or not application_text.strip():
        return False

    auto_no = vehicle_index + 1
    patterns = (
        rf"(?:^|\n){auto_no}\.[\s\S]{{0,800}}?Leased[\s\S]{{0,40}}?\bYes\b",
        rf"Auto\s+No\.?\s*{auto_no}[\s\S]{{0,800}}?Leased[\s\S]{{0,40}}?\bYes\b",
        rf"Ownership[\s\S]{{0,400}}?Leased[\s\S]{{0,40}}?\bYes\b",
    )
    for pattern in patterns:
        if re.search(pattern, application_text, flags=re.IGNORECASE):
            return True
    return False


def _llm_company_name_needs_correction(company_name, app_company: str) -> bool:
    """True when post-process should replace LLM company_name with Application parse."""
    if _is_missing(company_name):
        return True
    if not isinstance(company_name, str):
        return True
    if _looks_like_person_name(company_name):
        return True
    if not app_company:
        return False
    if app_company in _FINANCE_COMPANY_OPTIONS and company_name != app_company:
        if company_name.upper() not in app_company.upper():
            return True
    return False


def _apply_interest_from_application(data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
    """
    Correct risk[].interest using Application 'Lienholder Name & Postal Address' table.

    Post-process: always corrects has_loan (+ company_name when wrong).
    address / postal_code: prefer LLM; fill from Application only when LLM left them empty.
    """
    if not isinstance(data, dict):
        _beacon_interest("apply_interest_skip", reason="data_not_dict")
        return data

    _beacon_interest(
        "apply_interest_enter",
        llm_interest=_summarize_risk_interest(data),
        documents=_summarize_documents_for_interest(documents),
    )

    application_text = _get_application_document_text(documents)
    if not application_text.strip():
        _beacon_interest(
            "apply_interest_exit",
            reason="no_application_text",
            hint="select Application Form PDF or check PDF text extraction",
        )
        return data

    block = _find_lienholder_section_block(application_text)
    _beacon_interest(
        "application_text_loaded",
        chars=len(application_text),
        block_chars=len(block),
        has_lienholder_label=("lienholder" in application_text.lower()),
        has_td_auto_finance=("td auto finance" in application_text.lower()),
        snippet_lienholder=_snippet_around(application_text, "Lienholder"),
        snippet_td_auto=_snippet_around(application_text, "TD Auto Finance"),
    )

    lienholders = _extract_lienholders_by_auto_no(application_text)
    if not lienholders:
        _beacon_interest(
            "apply_interest_exit",
            reason="lienholder_parse_empty",
            parsed_auto_nos="(none)",
            hint="PDF extract layout may not match parser; see snippet_* above",
        )
        return data

    _beacon_interest(
        "lienholder_parse_ok",
        parsed_auto_nos=list(lienholders.keys()),
        row1_company=lienholders.get(1, {}).get("company_name"),
    )

    risks = data.get("risk")
    if isinstance(risks, dict):
        risks = [risks]
        data["risk"] = risks
    if not isinstance(risks, list):
        _beacon_interest("apply_interest_exit", reason="risk_not_list", risk_type=type(risks).__name__)
        return data

    for idx, risk in enumerate(risks):
        if not isinstance(risk, dict):
            _beacon_interest("risk_skip", index=idx, reason="not_dict")
            continue

        row = lienholders.get(idx + 1)
        if not row:
            _beacon_interest(
                "risk_skip",
                index=idx,
                auto_no=idx + 1,
                reason="no_lienholder_row_for_auto_no",
                available_auto_nos=list(lienholders.keys()),
            )
            continue

        interest = risk.get("interest")
        before_has_loan = interest.get("has_loan") if isinstance(interest, dict) else None
        if not isinstance(interest, dict):
            interest = {}
            risk["interest"] = interest

        interest["has_loan"] = "Yes"
        if _is_missing(interest.get("type_of_interest")):
            interest["type_of_interest"] = (
                "Lessor"
                if _vehicle_is_leased_on_application(application_text, idx)
                else "Lienholder"
            )

        app_company = row.get("company_name")
        if app_company and _llm_company_name_needs_correction(interest.get("company_name"), app_company):
            interest["company_name"] = app_company

        if _is_missing(interest.get("address")) and row.get("address"):
            interest["address"] = row["address"]
        if _is_missing(interest.get("unit_number")) and row.get("unit_number"):
            interest["unit_number"] = row["unit_number"]
        if _is_missing(interest.get("postal_code")) and row.get("postal_code"):
            interest["postal_code"] = row["postal_code"]

        _beacon_interest(
            "risk_interest_filled",
            index=idx,
            auto_no=idx + 1,
            before_has_loan=before_has_loan,
            after_interest=interest,
            note="has_loan+company_name corrected; address/postal_code filled only if LLM empty",
        )

    _beacon_interest("apply_interest_done", final_interest=_summarize_risk_interest(data))
    return data


def _extract_brokerage_insured_date_from_quote(documents: Optional[Dict[str, str]]) -> Optional[str]:
    """
    Return raw date text from Quote 'Brokerage Insured' when present; None if blank or missing.
    """
    quote = _get_quote_document_text(documents)
    if not quote:
        return None

    match = re.search(
        r"Brokerage\s+Insured\b\s*:?\s*([^\n\r]{0,60})",
        quote,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    tail = match.group(1).strip()
    if not tail:
        return None

    date_match = re.search(
        r"(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        tail,
    )
    if date_match:
        return date_match.group(1)

    # Date may appear on the next line after the label.
    start = match.end()
    window = quote[start : start + 80]
    date_match = re.search(
        r"(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        window,
    )
    return date_match.group(1) if date_match else None


def _extract_broker_number_from_documents(documents: Optional[Dict[str, str]]) -> Optional[str]:
    if not isinstance(documents, dict) or not documents:
        return None

    text = " ".join(v for v in documents.values() if isinstance(v, str))
    if not text:
        return None

    patterns = [
        r"\bBroker\s*Code\s*[:#]?\s*([A-Za-z]?\s*\d{5,})",
        r"\bBroker\s*#\s*[:#]?\s*([A-Za-z]?\s*\d{5,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        raw_code = re.sub(r"\s+", "", match.group(1))
        digits = re.sub(r"\D", "", raw_code)
        if len(digits) >= 5:
            return digits[:5]
        if digits:
            return digits
    return None


_USAGE_HEADER_LABELS = frozenset(
    {"primary use", "annual km", "business km", "daily km"}
)
_TYPE_OF_USE_OPTIONS = (
    "pleasure",
    "business",
    "farmer personal use",
    "vocational",
)


def _is_usage_header_label(line: str) -> bool:
    return isinstance(line, str) and line.strip().lower() in _USAGE_HEADER_LABELS


def _normalize_type_of_use_value(raw: str) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    lower = text.lower()
    if lower == "pleasure":
        return "Pleasure"
    if lower == "business":
        return "Business"
    if lower == "farmer personal use":
        return "Farmer Personal Use"
    if lower == "vocational":
        return "Vocational"
    if lower in _TYPE_OF_USE_OPTIONS:
        return text.title() if lower == "business" else text
    return text


def _value_immediately_above_label(lines: list, label_idx: int) -> Optional[str]:
    """Return the nearest non-empty line above a header label, unless that line is another label."""
    for j in range(label_idx - 1, -1, -1):
        prev = lines[j].strip()
        if not prev:
            continue
        if _is_usage_header_label(prev):
            return None
        return prev
    return None


def _parse_vertical_usage_block(block: str) -> Optional[Dict]:
    """
    Parse Intact Quote usage fields from vertical value-above-label OCR, e.g.:
      Pleasure / Primary Use / 10000 / Annual km / Business km / 6 / Daily km
    """
    if not isinstance(block, str) or not block.strip():
        return None

    lines = [line.strip() for line in block.splitlines()]
    label_indices = {
        "type_of_use": None,
        "annual_km": None,
        "annual_business_km": None,
        "km_toward_work": None,
    }
    for idx, line in enumerate(lines):
        lower = line.lower()
        if lower == "primary use":
            label_indices["type_of_use"] = idx
        elif lower == "annual km":
            label_indices["annual_km"] = idx
        elif lower == "business km":
            label_indices["annual_business_km"] = idx
        elif lower == "daily km":
            label_indices["km_toward_work"] = idx

    if label_indices["km_toward_work"] is None and label_indices["annual_km"] is None:
        return None

    parsed: Dict = {}

    primary_raw = (
        _value_immediately_above_label(lines, label_indices["type_of_use"])
        if label_indices["type_of_use"] is not None
        else None
    )
    type_of_use = _normalize_type_of_use_value(primary_raw) if primary_raw else None
    if type_of_use:
        parsed["type_of_use"] = type_of_use

    annual_raw = (
        _value_immediately_above_label(lines, label_indices["annual_km"])
        if label_indices["annual_km"] is not None
        else None
    )
    if annual_raw and re.fullmatch(r"\d+", annual_raw.replace(",", "")):
        parsed["annual_km"] = int(annual_raw.replace(",", ""))

    business_raw = (
        _value_immediately_above_label(lines, label_indices["annual_business_km"])
        if label_indices["annual_business_km"] is not None
        else None
    )
    if business_raw and re.fullmatch(r"\d+", business_raw.replace(",", "")):
        parsed["annual_business_km"] = int(business_raw.replace(",", ""))
    elif label_indices["annual_business_km"] is not None:
        parsed["annual_business_km"] = 0

    daily_raw = (
        _value_immediately_above_label(lines, label_indices["km_toward_work"])
        if label_indices["km_toward_work"] is not None
        else None
    )
    if daily_raw and re.fullmatch(r"\d+", daily_raw.replace(",", "")):
        parsed["km_toward_work"] = int(daily_raw.replace(",", ""))
    elif label_indices["km_toward_work"] is not None:
        parsed["km_toward_work"] = 0

    return parsed or None


def _parse_horizontal_usage_line(block: str) -> Optional[Dict]:
    """Fallback: one data row above a horizontal Primary Use ... Daily km header row."""
    marker = re.search(r"Primary\s+Use[\s\S]{0,80}?Daily\s*km", block, flags=re.IGNORECASE)
    if not marker:
        return None

    prefix = block[: marker.start()]
    candidate_line = None
    for raw_line in reversed(prefix.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        if not re.search(r"\d", line):
            continue
        candidate_line = line
        break

    if not candidate_line:
        return None

    number_matches = list(re.finditer(r"\d+", candidate_line))
    if not number_matches:
        return None

    first_num_start = number_matches[0].start()
    type_of_use = _normalize_type_of_use_value(candidate_line[:first_num_start].strip())
    nums = [int(m.group()) for m in number_matches]
    if not type_of_use or not nums:
        return None

    annual_km = nums[0]
    if len(nums) >= 3:
        annual_business_km = nums[1]
        daily_km = nums[2]
    elif len(nums) == 2:
        annual_business_km = 0
        daily_km = nums[1]
    else:
        annual_business_km = 0
        daily_km = 0

    return {
        "type_of_use": type_of_use,
        "annual_km": annual_km,
        "annual_business_km": annual_business_km,
        "km_toward_work": daily_km,
    }


def _parse_usage_fields_from_block(block: str) -> Optional[Dict]:
    """Prefer vertical value-above-label OCR; fall back to horizontal row parsing."""
    vertical = _parse_vertical_usage_block(block)
    if vertical and "km_toward_work" in vertical:
        return vertical
    if vertical:
        horizontal = _parse_horizontal_usage_line(block)
        if horizontal:
            merged = dict(horizontal)
            merged.update(vertical)
            return merged
        return vertical
    return _parse_horizontal_usage_line(block)


def _get_quote_or_full_document_text(documents: Optional[Dict[str, str]]) -> str:
    quote = _get_quote_document_text(documents)
    if quote:
        return quote
    if not isinstance(documents, dict):
        return ""
    return "\n".join(v for v in documents.values() if isinstance(v, str))


_WINTER_TIRE_DISCOUNT_PATTERN = re.compile(
    r"Discount\s*-\s*Winter\s+Tires?\s+included",
    flags=re.IGNORECASE,
)
_WINTER_TIRES_PURCHASE_HEADER_PATTERN = re.compile(
    r"(?i)winter\s+tires.*(?:parking\s+at\s+night|purchase\s+price|list\s+price)"
)
_WINTER_TIRES_BEFORE_PARKING_PATTERN = re.compile(
    r"(?i)\b(Yes|No)\b\s+(?:Private\s+Driveway|Garage|Street|Locked|Unlocked|Carport|"
    r"Driveway|Indoor|Outdoor|Parking|Attached|Detached|Residential|Car\s+Port)"
)


def _quote_has_winter_tire_discount(text: str) -> bool:
    return bool(_WINTER_TIRE_DISCOUNT_PATTERN.search(text or ""))


def _parse_winter_tires_from_purchase_value_row(value_line: str) -> Optional[str]:
    """Parse Yes/No from the purchase-table value row above the Winter Tires header."""
    if not isinstance(value_line, str):
        return None
    text = value_line.strip()
    if not text:
        return None
    if text in ("Yes", "No"):
        return text

    match = _WINTER_TIRES_BEFORE_PARKING_PATTERN.search(text)
    if match:
        return match.group(1).title()

    # Horizontal row with empty List/Purchase Price columns: ... <km> Yes|No <parking>
    tail = re.search(
        r"(?i)\b(\d{3,6})\s+(Yes|No)\s+(.+)$",
        text,
    )
    if tail:
        return tail.group(2).title()
    return None


def _parse_winter_tires_from_purchase_table(block: str) -> Optional[str]:
    """
    Read winter_tires from Quote purchase table for one vehicle block.

    Supports vertical OCR (value line above 'Winter Tires' label) and horizontal rows
    like 'Used 06/13/2026 29662 Yes Private Driveway' above the column headers.
    """
    if not isinstance(block, str) or not block.strip():
        return None

    lines = [ln.strip() for ln in block.splitlines() if ln and ln.strip()]
    for idx, line in enumerate(lines):
        if re.fullmatch(r"(?i)winter\s+tires", line) and idx > 0:
            prev = lines[idx - 1]
            if prev in ("Yes", "No"):
                return prev

        if not _WINTER_TIRES_PURCHASE_HEADER_PATTERN.search(line):
            continue
        if idx == 0:
            continue
        parsed = _parse_winter_tires_from_purchase_value_row(lines[idx - 1])
        if parsed in ("Yes", "No"):
            return parsed
    return None


def _resolve_winter_tires_for_vehicle_block(block: str) -> str:
    """Discount line => Yes; otherwise purchase-table Winter Tires column; else No."""
    if _quote_has_winter_tire_discount(block):
        return "Yes"
    table_value = _parse_winter_tires_from_purchase_table(block)
    if table_value in ("Yes", "No"):
        return table_value
    return "No"


def _resolve_winter_tires_from_blocks(blocks) -> str:
    """Any 'Discount - Winter Tire included' => Yes; else merge purchase-table values."""
    for block in blocks:
        if _quote_has_winter_tire_discount(block):
            return "Yes"

    table_values = []
    for block in blocks:
        table_value = _parse_winter_tires_from_purchase_table(block)
        if table_value in ("Yes", "No"):
            table_values.append(table_value)
    if "Yes" in table_values:
        return "Yes"
    if table_values:
        return table_values[0]
    return "No"


def _extract_winter_tires_by_vehicle(documents: Optional[Dict[str, str]]) -> Dict[int, str]:
    """Determine winter_tires per vehicle from Quote purchase table and DIS discounts."""
    quote = _get_quote_document_text(documents)
    if not quote:
        return {}

    vehicle_pattern = re.compile(
        r"(?im)^\s*(?:Vehicle\s*)?(\d+)\s+of\s+\d+(?:\s*\||\b)"
    )
    matches = list(vehicle_pattern.finditer(quote))
    if not matches:
        return {1: _resolve_winter_tires_for_vehicle_block(quote)}

    blocks_by_vehicle: Dict[int, list] = {}
    for idx, match in enumerate(matches):
        vehicle_no = int(match.group(1))
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(quote)
        block = quote[match.start() : end]
        blocks_by_vehicle.setdefault(vehicle_no, []).append(block)

    return {
        vehicle_no: _resolve_winter_tires_from_blocks(blocks)
        for vehicle_no, blocks in blocks_by_vehicle.items()
    }


def _normalize_winter_tires_from_quote_discount(data: Dict, documents: Optional[Dict[str, str]]) -> Dict:
    """Set risk[].winter_tires from Quote purchase-table column and DIS discount lines."""
    if not isinstance(data, dict):
        return data

    risks = data.get("risk")
    if isinstance(risks, dict):
        risks = [risks]
        data["risk"] = risks
    if not isinstance(risks, list) or not risks:
        return data

    winter_by_vehicle = _extract_winter_tires_by_vehicle(documents)
    if not winter_by_vehicle:
        return data

    for idx, risk in enumerate(risks):
        if not isinstance(risk, dict):
            continue
        risk["winter_tires"] = winter_by_vehicle.get(idx + 1, "No")
    return data


def _extract_assignment_values_by_vehicle_from_documents(documents: Optional[Dict[str, str]]) -> Dict[int, Dict]:
    """
    Extract per-vehicle assignment usage values from Quote blocks.
    Supports vertical value-above-label OCR and horizontal table rows.
    """
    full_text = _get_quote_or_full_document_text(documents)
    if not full_text:
        return {}

    vehicle_values: Dict[int, Dict] = {}
    block_pattern = re.compile(
        r"Vehicle\s+(\d+)\s+of\s+\d+([\s\S]*?)(?=Vehicle\s+\d+\s+of\s+\d+|$)",
        flags=re.IGNORECASE,
    )
    matches = list(block_pattern.finditer(full_text))

    if matches:
        for match in matches:
            vehicle_idx = int(match.group(1))
            parsed = _parse_usage_fields_from_block(match.group(2))
            if parsed:
                vehicle_values[vehicle_idx] = parsed
        return vehicle_values

    parsed = _parse_usage_fields_from_block(full_text)
    if parsed:
        vehicle_values[1] = parsed
    return vehicle_values


def _apply_parsed_usage_to_assignment_target(target: Dict, parsed: Dict) -> None:
    if not isinstance(target, dict) or not isinstance(parsed, dict):
        return
    for field_key in _ASSIGNMENT_COMMON_KEYS:
        if field_key in parsed:
            target[field_key] = parsed[field_key]


def _normalize_assignment_usage_from_quote(data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
    """
    Fill assignment usage fields from Quote OCR (single- and multi-risk).
    Single-risk: writes to assignment root (and vehicle_1 when present).
    Multi-risk: distributes per vehicle_N and removes duplicated root fields.
    """
    if not isinstance(data, dict):
        return data

    risks = data.get("risk")
    if not isinstance(risks, list) or not risks:
        return data

    assignment = data.get("assignment")
    if not isinstance(assignment, dict):
        return data

    parsed_vehicle_values = _extract_assignment_values_by_vehicle_from_documents(documents)

    if len(risks) == 1:
        if parsed_vehicle_values:
            parsed = parsed_vehicle_values.get(1) or next(iter(parsed_vehicle_values.values()))
            _apply_parsed_usage_to_assignment_target(assignment, parsed)
            vehicle_1 = assignment.get("vehicle_1")
            if isinstance(vehicle_1, dict):
                _apply_parsed_usage_to_assignment_target(vehicle_1, parsed)
        return data

    default_values = {}
    for field_key in _ASSIGNMENT_COMMON_KEYS:
        if field_key in assignment:
            default_values[field_key] = assignment[field_key]

    vehicle_1 = assignment.get("vehicle_1")
    if isinstance(vehicle_1, dict):
        for field_key in _ASSIGNMENT_COMMON_KEYS:
            if field_key not in default_values and field_key in vehicle_1:
                default_values[field_key] = vehicle_1[field_key]

    if not default_values and not parsed_vehicle_values:
        return data

    for i in range(1, len(risks) + 1):
        vehicle_key = f"vehicle_{i}"
        vehicle_assignment = assignment.get(vehicle_key)
        if not isinstance(vehicle_assignment, dict):
            vehicle_assignment = {}
            assignment[vehicle_key] = vehicle_assignment

        if i in parsed_vehicle_values:
            vehicle_assignment.update(parsed_vehicle_values[i])

        for field_key in _ASSIGNMENT_COMMON_KEYS:
            if field_key in default_values and field_key not in vehicle_assignment:
                vehicle_assignment[field_key] = default_values[field_key]

    if default_values:
        for field_key in _ASSIGNMENT_COMMON_KEYS:
            assignment.pop(field_key, None)

    return data


def _decode_vin_model_detail(vin: str) -> Optional[str]:
    vin_clean = (vin or "").strip().upper()
    if len(vin_clean) != 17:
        return None

    try:
        encoded_vin = parse.quote(vin_clean)
        url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{encoded_vin}?format=json"
        with request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    except Exception:
        return None

    results = payload.get("Results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or not results:
        return None

    row = results[0] if isinstance(results[0], dict) else {}

    def clean(value) -> str:
        if value is None:
            return ""
        text = str(value).strip()
        if text in {"", "0", "Not Applicable"}:
            return ""
        return text

    year = clean(row.get("ModelYear"))
    make = clean(row.get("Make")).title()
    model = clean(row.get("Model"))
    trim = clean(row.get("Trim"))
    body = clean(row.get("BodyClass"))
    doors = clean(row.get("Doors"))
    drive = clean(row.get("DriveType"))
    displacement_l = clean(row.get("DisplacementL"))
    cylinders = clean(row.get("EngineCylinders"))

    base_parts = [part for part in (year, make, model, trim) if part]
    if not base_parts:
        return None

    detail_parts = []
    if body:
        body_text = body
        if doors:
            body_text = f"{body_text} {doors}dr"
        detail_parts.append(body_text)
    elif doors:
        detail_parts.append(f"{doors}dr")

    if drive:
        detail_parts.append(drive)

    engine_parts = []
    if displacement_l:
        engine_parts.append(f"{displacement_l}L")
    if cylinders:
        engine_parts.append(f"I{cylinders}")
    if engine_parts:
        detail_parts.append(" ".join(engine_parts))

    model_detail = " ".join(base_parts)
    if detail_parts:
        model_detail = f"{model_detail} {' '.join(detail_parts)}"
    return re.sub(r"\s+", " ", model_detail).strip()


def _is_no_insurance_record(driver: Dict) -> bool:
    status = driver.get("insurance_history_report_status")
    if isinstance(status, str) and status.strip().lower() == "not found":
        return True

    previous_insurer = driver.get("previous_insurer")
    if isinstance(previous_insurer, str) and previous_insurer.strip().lower() == "no prior insurer":
        return True

    return False


def _has_conviction_detail(convictions_value) -> bool:
    if convictions_value is None:
        return False
    if isinstance(convictions_value, str):
        return convictions_value.strip().lower() != "no"
    if isinstance(convictions_value, list):
        for item in convictions_value:
            if isinstance(item, str) and item.strip().lower() == "no":
                continue
            if item is not None and str(item).strip():
                return True
        return False
    return bool(str(convictions_value).strip())


def _to_full_date(generator, value) -> Optional[str]:
    """Normalize to YYYY-MM-DD for Intact fields; pad YYYY-MM with day 01."""
    if _is_missing(value):
        return None
    normalized = generator._format_to_yyyymmdd(value)
    if isinstance(normalized, str) and re.match(r"^\d{4}-\d{2}$", normalized):
        return f"{normalized}-01"
    return normalized if isinstance(normalized, str) else None


def _parse_date_text(value: str) -> Optional[date]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _compute_years_with_previous_insurer(start: date, end: date) -> int:
    """
    Full years with previous insurer — floor partial years.

    A period counts as N years only after the N-th anniversary has passed
    (end date must be strictly after the anniversary, not on it).
    E.g. 2024-01-02 → 2025-01-02 = 0; 2024-01-02 → 2025-01-03 = 1.
    """
    if end < start:
        return 0
    years = end.year - start.year
    if (end.month, end.day) <= (start.month, start.day):
        years -= 1
    return max(0, years)


def _years_with_previous_insurer_from_driver_dates(
    generator,
    insured_since_value,
    expiry_value,
) -> Optional[int]:
    start_text = _to_full_date(generator, insured_since_value)
    end_text = _to_full_date(generator, expiry_value)
    if not start_text or not end_text:
        return None
    start = _parse_date_text(start_text)
    end = _parse_date_text(end_text)
    if not start or not end:
        return None
    return _compute_years_with_previous_insurer(start, end)


# MVR pull time: upper-right black timestamp on CGI/Ontario abstracts, e.g.
#   Monday, June 22, 2026 03:30 PM
# Do NOT use the red "Duplicate request ... submitted on DD/MM/YYYY" banner (top-left).
_MVR_TOP_RIGHT_DATETIME_PATTERN = re.compile(
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{1,2}),\s+(\d{4})\s+\d{1,2}:\d{2}\s*(?:AM|PM)",
    flags=re.IGNORECASE,
)
_MVR_TOP_RIGHT_DATETIME_NO_WEEKDAY_PATTERN = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+"
    r"(\d{1,2}),\s+(\d{4})\s+\d{1,2}:\d{2}\s*(?:AM|PM)",
    flags=re.IGNORECASE,
)
# Legacy Ontario MVR header at upper-right:
#   *** MOTOR VEHICLE RECORD - YYYY/MM/DD ***
_MVR_HEADER_PATTERN = re.compile(
    r"MOTOR\s+VEHICLE\s+RECORD\s*-\s*(\d{4}[/-]\d{2}[/-]\d{2})",
    flags=re.IGNORECASE,
)
_MVR_LICENCE_PATTERN = re.compile(
    r"Licence(?:\s+Number)?\s*:\s*(\S+)",
    flags=re.IGNORECASE,
)
_MVR_NAME_FIELD_LABELS = frozenset(
    {
        "name",
        "birth date",
        "expiry date",
        "issue date",
        "gender",
        "address",
        "licence number",
        "height",
        "status",
    }
)
_MVR_DATE_LIKE_PATTERN = re.compile(
    r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$|^\d{4}[/-]\d{2}[/-]\d{2}$"
)
_MVR_NAME_JUNK_SUFFIX_PATTERN = re.compile(
    r"\s+(?:Birth\s+Date|Expiry\s+Date|Issue\s+Date|BirDt|ExpDt|Gender|Address)\b",
    flags=re.IGNORECASE,
)


def _normalize_licence_key(value) -> str:
    if _is_missing(value):
        return ""
    return re.sub(r"[\s\-]", "", str(value)).upper()


def _sanitize_mvr_name_token(token: str) -> str:
    """Strip dates and non-name field labels accidentally merged into a name token."""
    if not isinstance(token, str):
        return ""
    text = token.strip()
    if not text:
        return ""
    text = _MVR_NAME_JUNK_SUFFIX_PATTERN.split(text, maxsplit=1)[0].strip()
    text = re.sub(
        r"\s*:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}.*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return text


def _is_valid_mvr_name_part(value: str) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or len(text) > 80:
        return False
    if _MVR_DATE_LIKE_PATTERN.match(text):
        return False
    if re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", text):
        return False
    lower = text.lower()
    for label in _MVR_NAME_FIELD_LABELS:
        if label in lower:
            return False
    if not re.search(r"[A-Za-z]", text):
        return False
    return True


def _parse_mvr_name(name_raw: str):
    """
    Parse MVR 'Name:' value into (last_name, first_name).

    MVR formats:
      1) LAST, FIRST, MIDDLE  -> ignore middle name
      2) LAST, FIRST
      3) LAST only (or LAST, with trailing comma but no first name)
         -> first_name = last_name (copy)
    Comma is the only delimiter; never split on whitespace.
    """
    if not isinstance(name_raw, str):
        return None
    text = _sanitize_mvr_name_token(name_raw)
    if not text:
        return None

    parts = [_sanitize_mvr_name_token(part) for part in text.split(",")]
    parts = [part for part in parts if part]
    if not parts:
        return None

    last_name = parts[0]
    first_name = parts[1] if len(parts) >= 2 else last_name

    if not _is_valid_mvr_name_part(last_name) or not _is_valid_mvr_name_part(first_name):
        return None

    return last_name, first_name


def _extract_mvr_name_raw_from_content(content: str) -> Optional[str]:
    """
    Extract the raw MVR name string from Ontario / Intact MVR text.

    Supports:
      - Inline:  Name : HE, XINYI
      - Next line: Name :\\nHE, XINYI
      - Value above label (common PDF extract): HE, XINYI\\nName
    """
    if not isinstance(content, str) or not content.strip():
        return None

    inline = re.search(r"Name\s*:\s*([^\n\r]+)", content, flags=re.IGNORECASE)
    if inline:
        inline_value = inline.group(1).strip()
        if inline_value and inline_value.lower() not in _MVR_NAME_FIELD_LABELS:
            return inline_value

    next_line = re.search(
        r"Name\s*:\s*\n\s*([^\n\r]+)",
        content,
        flags=re.IGNORECASE,
    )
    if next_line:
        candidate = next_line.group(1).strip()
        if candidate and candidate.lower() not in _MVR_NAME_FIELD_LABELS:
            return candidate

    lines = [line.strip() for line in content.splitlines()]
    for idx, line in enumerate(lines):
        if line.lower() != "name" and not re.match(r"^Name\s*:?\s*$", line, flags=re.IGNORECASE):
            continue
        for j in range(idx - 1, -1, -1):
            prev = lines[j].strip()
            if not prev:
                continue
            if prev.lower() in _MVR_NAME_FIELD_LABELS:
                break
            if _MVR_DATE_LIKE_PATTERN.match(prev):
                break
            if re.search(r"[A-Za-z]", prev):
                return prev
            break

    return None


def _build_mvr_name_index(documents: Optional[Dict[str, str]]):
    """Return list of (doc_key, last_name, first_name, licence, upper_content) per MVR doc."""
    index = []
    if not isinstance(documents, dict):
        return index

    for doc_key, content in documents.items():
        if not isinstance(doc_key, str) or not isinstance(content, str) or not content:
            continue
        if not doc_key.upper().startswith("MVR"):
            continue

        name_raw = _extract_mvr_name_raw_from_content(content)
        if not name_raw:
            continue
        parsed = _parse_mvr_name(name_raw)
        if not parsed:
            continue

        licence_match = _MVR_LICENCE_PATTERN.search(content)
        licence = _normalize_licence_key(licence_match.group(1)) if licence_match else ""
        index.append((doc_key, parsed[0], parsed[1], licence, content.upper()))
    return index


def _find_mvr_name_for_driver(
    driver: Dict,
    applicant_info: Optional[Dict],
    is_primary: bool,
    driver_idx: int,
    mvr_index,
):
    """
    Pick the MVR name entry for this driver.

    Priority: licence number match -> name token match -> positional MVR index.
    """
    if not mvr_index:
        return None

    licence_key = _normalize_licence_key(driver.get("licence_number"))

    if licence_key:
        for entry in mvr_index:
            if entry[3] and entry[3] == licence_key:
                return entry[1], entry[2]

    first, last = _driver_name_tokens(driver, applicant_info, is_primary)
    if first or last:
        for entry in mvr_index:
            upper_content = entry[4]
            last_hit = bool(last) and last in upper_content
            first_hit = bool(first) and first in upper_content
            if last and first:
                if last_hit and first_hit:
                    return entry[1], entry[2]
            elif last_hit or first_hit:
                return entry[1], entry[2]

    if driver_idx < len(mvr_index):
        return mvr_index[driver_idx][1], mvr_index[driver_idx][2]

    if len(mvr_index) == 1:
        return mvr_index[0][1], mvr_index[0][2]

    return None


def _apply_mvr_names_from_documents(data: Dict, documents: Optional[Dict[str, str]]) -> Dict:
    """Overwrite applicant/additional-driver names from parsed MVR 'Name:' fields."""
    if not isinstance(data, dict):
        return data

    mvr_index = _build_mvr_name_index(documents)
    if not mvr_index:
        return data

    drivers = data.get("driver")
    if not isinstance(drivers, list) or not drivers:
        return data

    applicant_info = data.get("applicant_information") if isinstance(data.get("applicant_information"), dict) else {}

    for driver_idx, driver in enumerate(drivers):
        if not isinstance(driver, dict):
            continue

        parsed = _find_mvr_name_for_driver(
            driver,
            applicant_info,
            is_primary=(driver_idx == 0),
            driver_idx=driver_idx,
            mvr_index=mvr_index,
        )
        if not parsed:
            continue

        last_name, first_name = parsed
        if not _is_valid_mvr_name_part(last_name) or not _is_valid_mvr_name_part(first_name):
            continue

        if driver_idx == 0:
            target = applicant_info
            if not isinstance(data.get("applicant_information"), dict):
                data["applicant_information"] = target
        else:
            target = driver

        target["last_name"] = last_name
        target["first_name"] = first_name

    return data
_AUTOPLUS_REPORT_DATE_PATTERN = re.compile(
    r"Report\s*Date\s*[:\-]?\s*(\d{4}[/-]\d{2}[/-]\d{2}|\d{2}[/-]\d{2}[/-]\d{4})",
    flags=re.IGNORECASE,
)


def _parse_english_month_date(month_name: str, day: int, year: int) -> Optional[date]:
    for fmt in ("%B %d %Y", "%b %d %Y"):
        try:
            return datetime.strptime(f"{month_name} {day} {year}", fmt).date()
        except ValueError:
            continue
    return None


def _extract_mvr_pull_date_from_content(content: str) -> Optional[date]:
    """
    Extract MVR pull date from the upper-right black timestamp at the top of the page.

    Prefers CGI abstract timestamps like 'Monday, June 22, 2026 03:30 PM'.
    Ignores duplicate-request banner dates ('submitted on 10/06/2026') and summary
    table Request Date / Release Date rows.
    Falls back to legacy '*** MOTOR VEHICLE RECORD - YYYY/MM/DD ***' header.
    """
    if not isinstance(content, str) or not content.strip():
        return None

    head = content[:3500]
    for pattern in (_MVR_TOP_RIGHT_DATETIME_PATTERN, _MVR_TOP_RIGHT_DATETIME_NO_WEEKDAY_PATTERN):
        for match in pattern.finditer(head):
            parsed = _parse_english_month_date(match.group(1), int(match.group(2)), int(match.group(3)))
            if parsed is not None:
                return parsed

    legacy = _MVR_HEADER_PATTERN.search(content)
    if legacy:
        return _parse_date_text(legacy.group(1))
    return None


def _build_mvr_pull_date_index(documents: Optional[Dict[str, str]]):
    """Return list of (doc_key, pull_date, upper_content) per MVR document."""
    index = []
    if not isinstance(documents, dict):
        return index

    for doc_key, content in documents.items():
        if not isinstance(doc_key, str) or not isinstance(content, str) or not content:
            continue
        if not doc_key.upper().startswith("MVR"):
            continue
        pull_date = _extract_mvr_pull_date_from_content(content)
        if pull_date is None:
            continue
        index.append((doc_key, pull_date, content.upper()))
    return index


def _find_mvr_pull_date_for_driver(
    driver: Dict,
    applicant_info: Optional[Dict],
    is_primary: bool,
    driver_idx: int,
    mvr_index,
) -> Optional[date]:
    """Pick the MVR pull date for this driver (same matching rules as header date)."""
    if not mvr_index:
        return None

    licence_key = _normalize_licence_key(driver.get("licence_number"))
    if licence_key:
        for entry in mvr_index:
            upper_content = entry[2]
            if licence_key in re.sub(r"[\s\-]", "", upper_content):
                return entry[1]

    first, last = _driver_name_tokens(driver, applicant_info, is_primary)
    if first or last:
        for entry in mvr_index:
            upper_content = entry[2]
            last_hit = bool(last) and last in upper_content
            first_hit = bool(first) and first in upper_content
            if last and first:
                if last_hit and first_hit:
                    return entry[1]
            elif last_hit or first_hit:
                return entry[1]

    if driver_idx < len(mvr_index):
        return mvr_index[driver_idx][1]
    if len(mvr_index) == 1:
        return mvr_index[0][1]
    return None


def _apply_mvr_request_datetime_from_documents(
    generator,
    data: Dict,
    documents: Optional[Dict[str, str]],
) -> Dict:
    """Overwrite driver MVR_request_date_time from each MVR's upper-right pull timestamp."""
    if not isinstance(data, dict):
        return data

    drivers = data.get("driver")
    if not isinstance(drivers, list) or not drivers:
        return data

    mvr_index = _build_mvr_pull_date_index(documents)
    if not mvr_index:
        return data

    applicant_info = data.get("applicant_information") if isinstance(data.get("applicant_information"), dict) else None
    for driver_idx, driver in enumerate(drivers):
        if not isinstance(driver, dict):
            continue
        pull_date = _find_mvr_pull_date_for_driver(
            driver,
            applicant_info,
            is_primary=(driver_idx == 0),
            driver_idx=driver_idx,
            mvr_index=mvr_index,
        )
        if pull_date is None:
            continue
        formatted = generator._format_to_ddmmyyyy(pull_date.isoformat())
        if formatted:
            driver["MVR_request_date_time"] = formatted
    return data


def _build_mvr_header_date_index(documents: Optional[Dict[str, str]]):
    """
    Return a list of (doc_key, header_date, upper_content) for every MVR document.
    Uses the upper-right pull timestamp when present (CGI abstracts), otherwise the
    legacy MOTOR VEHICLE RECORD header date.
    """
    return _build_mvr_pull_date_index(documents)


def _extract_earliest_autoplus_report_date(documents: Optional[Dict[str, str]]):
    """Return the earliest AutoPlus 'Report Date' across all documents (as date)."""
    if not isinstance(documents, dict) or not documents:
        return None
    dates = []
    for content in documents.values():
        if not isinstance(content, str) or not content:
            continue
        for match in _AUTOPLUS_REPORT_DATE_PATTERN.findall(content):
            parsed = _parse_date_text(match)
            if parsed is not None:
                dates.append(parsed)
    return min(dates) if dates else None


def _driver_name_tokens(driver: Dict, applicant_info: Optional[Dict], is_primary: bool):
    """Return (first_upper, last_upper) for the given driver."""
    source = applicant_info if (is_primary and isinstance(applicant_info, dict)) else driver
    if not isinstance(source, dict):
        return "", ""
    first = source.get("first_name")
    last = source.get("last_name")
    first = first.strip().upper() if isinstance(first, str) else ""
    last = last.strip().upper() if isinstance(last, str) else ""
    return first, last


def _find_mvr_header_date_for_driver(
    driver: Dict,
    applicant_info: Optional[Dict],
    is_primary: bool,
    mvr_index,
):
    """
    Pick the MVR header date that belongs to THIS driver.

    Priority:
    1) Match by driver name appearing in an MVR document (first_name AND last_name).
    2) If only one MVR document exists, use its header date.
    3) Otherwise, fall back to the earliest MVR header date.
    Returns a `date` or None.
    """
    if not mvr_index:
        return None

    first, last = _driver_name_tokens(driver, applicant_info, is_primary)
    if first or last:
        for _doc_key, header_date, upper_content in mvr_index:
            last_hit = bool(last) and last in upper_content
            first_hit = bool(first) and first in upper_content
            if last and first:
                if last_hit and first_hit:
                    return header_date
            elif last_hit or first_hit:
                return header_date

    if len(mvr_index) == 1:
        return mvr_index[0][1]

    return min(entry[1] for entry in mvr_index)


def _compute_consent_date_for_driver(
    driver: Dict,
    applicant_info: Optional[Dict],
    is_primary: bool,
    mvr_index,
    autoplus_earliest,
) -> Optional[str]:
    """
    Consent_Date for a single driver = earlier of:
      - this driver's MVR header date (upper-right `*** MOTOR VEHICLE RECORD - YYYY/MM/DD ***`)
      - global earliest AutoPlus 'Report Date'
    Returns YYYY-MM-DD string or None.
    """
    mvr_date = _find_mvr_header_date_for_driver(driver, applicant_info, is_primary, mvr_index)

    if mvr_date and autoplus_earliest:
        return min(mvr_date, autoplus_earliest).isoformat()
    if mvr_date:
        return mvr_date.isoformat()
    if autoplus_earliest:
        return autoplus_earliest.isoformat()
    return None


_LAPSE_ARRAY_FIELDS = (
    "lapse_in_insurance_description",
    "lapse_start",
    "lapse_end",
)


def _promote_lapse_fields_to_arrays(driver: Dict) -> None:
    """
    Lapse fields (description, start, end) are configured as parallel arrays so a single
    driver may carry multiple lapses. Older model outputs (or back-compat upstream callers)
    may still emit scalar strings; promote them to one-element arrays in place.

    Also align the three arrays to the same length by right-padding shorter arrays with
    None — this keeps index i aligned across description / start / end.
    """
    if not isinstance(driver, dict):
        return

    promoted = {}
    for key in _LAPSE_ARRAY_FIELDS:
        if key not in driver:
            continue
        value = driver[key]
        if value is None:
            promoted[key] = []
        elif isinstance(value, list):
            promoted[key] = value
        else:
            text = str(value).strip() if not isinstance(value, str) else value.strip()
            promoted[key] = [value] if text else []
        driver[key] = promoted[key]

    if not promoted:
        return

    target_len = max((len(promoted[k]) for k in promoted), default=0)
    if target_len == 0:
        return
    for key, arr in promoted.items():
        if len(arr) < target_len:
            arr.extend([None] * (target_len - len(arr)))
            driver[key] = arr


def _driver_has_non_payment_lapse(driver: Dict) -> bool:
    if not isinstance(driver, dict) or driver.get("lapse_in_insurance") != "Yes":
        return False
    for desc in _lapse_descriptions_iter(driver.get("lapse_in_insurance_description")):
        if isinstance(desc, str) and desc.strip().lower() == "non-payment":
            return True
    return False


def _normalize_non_payment_company(driver: Dict) -> None:
    """Keep non_payment_company only when a Non-Payment lapse exists."""
    if not isinstance(driver, dict):
        return
    if not _driver_has_non_payment_lapse(driver):
        driver.pop("non_payment_company", None)


def _lapse_descriptions_iter(value):
    """Yield lapse description strings whether the field is scalar or list."""
    if value is None:
        return
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                yield item
        return
    if isinstance(value, str):
        yield value


def _strip_empty_trailing_lapses(driver: Dict) -> None:
    """Drop trailing all-empty lapse rows so the arrays don't carry phantom entries."""
    if not isinstance(driver, dict):
        return
    arrays = {k: driver.get(k) for k in _LAPSE_ARRAY_FIELDS if isinstance(driver.get(k), list)}
    if not arrays:
        return
    target_len = min(len(arr) for arr in arrays.values())
    if target_len == 0:
        return

    keep = target_len
    for i in range(target_len - 1, -1, -1):
        all_empty = True
        for arr in arrays.values():
            v = arr[i]
            if v is None:
                continue
            if isinstance(v, str) and not v.strip():
                continue
            all_empty = False
            break
        if all_empty:
            keep = i
        else:
            break

    if keep == target_len:
        return
    for key, arr in arrays.items():
        driver[key] = arr[:keep]


_COVERAGE_LEGACY_ARRAY_KEYS = (
    "section_optional_coverages",
    "accident_benefits_standard_benefits",
)


def _normalize_coverage_label(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _format_intact_coverage_value(raw_value: str) -> Optional[str]:
    text = str(raw_value or "").strip().replace("$", "")
    if not text:
        return None

    unit_match = re.search(r"(\d+(?:,\d{3})*|\d+)\s*([MK])\b", text, flags=re.IGNORECASE)
    if unit_match:
        number = int(unit_match.group(1).replace(",", ""))
        unit = unit_match.group(2).upper()
        if unit == "K":
            return f"{number}K"
        return str(number * 1000000)

    number_match = re.search(r"\b(\d+(?:,\d{3})*|\d+)(?:\.00)?\b", text)
    if number_match:
        return number_match.group(1).replace(",", "")

    return None


def _extract_intact_coverage_value_from_tail(tail: str) -> Optional[str]:
    text = re.sub(r"\s+", " ", str(tail or "").strip(" :-\t"))
    if not text:
        return None

    # Intact rows are usually: coverage name | limit/value | premium | totals.
    # Manual entry should prefer the first limit/value column, not premium/totals.
    # Examples:
    #   "#20 Loss Of Use 5,000 95 95" -> 5000
    #   "#27 Liab to Unowned Veh. 75K 55 55" -> 75K
    #   "Accident Benefits 778 778" -> 778 (no separate limit column)
    token_match = re.search(
        r"\b(\d+(?:,\d{3})*|\d+)\s*(?:([MK])\b)?",
        text,
        flags=re.IGNORECASE,
    )
    if token_match:
        number = token_match.group(1)
        unit = token_match.group(2)
        return _format_intact_coverage_value(f"{number}{unit or ''}")

    return _format_intact_coverage_value(text)


def _tail_after_quote_coverage_label(line: str, label: str) -> Optional[str]:
    pattern = re.compile(re.escape(label), flags=re.IGNORECASE)
    match = pattern.search(line or "")
    if not match:
        return None
    return line[match.end() :]


def _quote_coverage_value_for_label(quote_text: str, label: str) -> Optional[str]:
    if not isinstance(quote_text, str) or not quote_text.strip() or not label:
        return None

    lines = [line.strip() for line in quote_text.splitlines() if line.strip()]
    for idx, line in enumerate(lines):
        tail = _tail_after_quote_coverage_label(line, label)
        if tail is None and idx + 1 < len(lines):
            tail = _tail_after_quote_coverage_label(f"{line} {lines[idx + 1]}", label)
        if tail is None:
            continue
        value = _extract_intact_coverage_value_from_tail(tail)
        if value is not None:
            return value
    return None


def _supplement_missing_intact_coverage_values_from_quote(
    items: list,
    documents: Optional[Dict[str, str]] = None,
    quote_text: Optional[str] = None,
) -> list:
    if quote_text is None:
        quote_text = _get_quote_document_text(documents)
    if not quote_text or not isinstance(items, list):
        return items

    updated = []
    seen = set()
    valued_labels = {
        _normalize_coverage_label(str(item).split(":", 1)[0])
        for item in items
        if isinstance(item, str) and ":" in item
    }

    for item in items:
        text = str(item).strip()
        if not text:
            continue

        label = text.split(":", 1)[0].strip()
        label_key = _normalize_coverage_label(label)
        if ":" not in text and label_key in valued_labels:
            continue

        value = _quote_coverage_value_for_label(quote_text, label)
        if value is not None:
            text = f"{label}: {value}"
            valued_labels.add(label_key)
        elif ":" not in text and label_key in valued_labels:
            continue

        if text not in seen:
            seen.add(text)
            updated.append(text)

    return updated


def _count_intact_risks(data: Dict) -> int:
    risks = data.get("risk")
    if isinstance(risks, dict):
        return 1
    if isinstance(risks, list):
        return sum(1 for risk in risks if isinstance(risk, dict))
    return 0


def _extract_quote_blocks_by_vehicle(documents: Optional[Dict[str, str]]) -> Dict[int, str]:
    """
    Split Quote text into per-vehicle blocks.
    Supports 'Vehicle 1 of 2 ...' and '1 of 2 | 2025 HONDA ...' headers.
    """
    quote = _get_quote_document_text(documents)
    if not quote:
        return {}

    block_pattern = re.compile(
        r"(?im)Vehicle\s+(\d+)\s+of\s+\d+([\s\S]*?)(?=Vehicle\s+\d+\s+of\s+\d+|$)",
    )
    matches = list(block_pattern.finditer(quote))
    if matches:
        result: Dict[int, str] = {}
        for match in matches:
            result[int(match.group(1))] = match.group(0)
        return result

    vehicle_pattern = re.compile(r"(?im)^\s*(\d+)\s+of\s+\d+(?:\s*\||\b)")
    header_matches = list(vehicle_pattern.finditer(quote))
    if not header_matches:
        return {1: quote}

    result = {}
    for idx, match in enumerate(header_matches):
        vehicle_no = int(match.group(1))
        end = header_matches[idx + 1].start() if idx + 1 < len(header_matches) else len(quote)
        result[vehicle_no] = quote[match.start() : end]
    return result


def _normalize_single_coverage_block(
    coverages: Dict,
    quote_text: Optional[str],
    documents: Optional[Dict[str, str]],
) -> None:
    """Merge legacy coverage arrays and supplement additional_coverages from a quote block."""
    if not isinstance(coverages, dict):
        return

    merged = []
    seen = set()
    for key in ("additional_coverages",) + _COVERAGE_LEGACY_ARRAY_KEYS:
        items = coverages.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if item is None:
                continue
            text = str(item).strip()
            if not text:
                continue
            if text not in seen:
                seen.add(text)
                merged.append(text)

    for legacy_key in _COVERAGE_LEGACY_ARRAY_KEYS:
        coverages.pop(legacy_key, None)

    supplement_source = quote_text or _get_quote_document_text(documents)
    if merged:
        coverages["additional_coverages"] = _supplement_missing_intact_coverage_values_from_quote(
            merged,
            documents,
            quote_text=supplement_source,
        )
    elif "additional_coverages" in coverages and isinstance(coverages["additional_coverages"], list):
        coverages["additional_coverages"] = [
            str(x).strip()
            for x in coverages["additional_coverages"]
            if x is not None and str(x).strip()
        ]
        coverages["additional_coverages"] = _supplement_missing_intact_coverage_values_from_quote(
            coverages["additional_coverages"],
            documents,
            quote_text=supplement_source,
        )


def _normalize_intact_coverages(data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
    """
    Normalize coverages (vehicle 1) and optional second_coverage (vehicle 2).
    Removes second_coverage when fewer than two risks are present.
    """
    if not isinstance(data, dict):
        return data

    vehicle_blocks = _extract_quote_blocks_by_vehicle(documents)
    risk_count = _count_intact_risks(data)

    coverages = data.get("coverages")
    if isinstance(coverages, dict):
        block1 = vehicle_blocks.get(1) or _get_quote_document_text(documents)
        _normalize_single_coverage_block(coverages, block1, documents)

    if risk_count < 2:
        data.pop("second_coverage", None)
        return data

    second = data.get("second_coverage")
    if not isinstance(second, dict):
        second = {}
        data["second_coverage"] = second

    block2 = vehicle_blocks.get(2)
    if not block2 and len(vehicle_blocks) >= 2:
        block2 = vehicle_blocks.get(max(vehicle_blocks))
    _normalize_single_coverage_block(second, block2, documents)
    return data


def _normalize_intact_additional_coverages(data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
    """Backward-compatible alias — use _normalize_intact_coverages."""
    return _normalize_intact_coverages(data, documents)


def _normalize_intact_claim_total_amount_paid(data: Dict) -> Dict:
    """
    Intact claim.total_amount_paid should always be integer-like string.
    Examples: "3203.00" -> "3203", "1250.50" -> "1250".
    """
    if not isinstance(data, dict):
        return data

    claim = data.get("claim")
    if not isinstance(claim, dict):
        return data

    amounts = claim.get("total_amount_paid")
    if not isinstance(amounts, list):
        return data

    normalized = []
    for amount in amounts:
        text = str(amount).strip() if amount is not None else ""
        if not text:
            normalized.append(amount)
            continue

        compact = text.replace(",", "")
        if re.fullmatch(r"-?\d+(?:\.\d+)?", compact):
            normalized.append(compact.split(".", 1)[0])
            continue
        normalized.append(amount)

    claim["total_amount_paid"] = normalized
    return data


def _apply_intact_defaults(generator, data: Dict, documents: Optional[Dict[str, str]]) -> Dict:
    if not isinstance(data, dict):
        return data

    broker_info = data.get("broker_information")
    if isinstance(broker_info, dict) and _is_missing(broker_info.get("broker_number")):
        broker_number = _extract_broker_number_from_documents(documents)
        if broker_number:
            broker_info["broker_number"] = broker_number
            print(f"[INFO] Filled Intact broker_number from documents: {broker_number}")

    term = data.get("term")
    effective_date = term.get("policy_effective_date") if isinstance(term, dict) else None
    effective_date_full = _to_full_date(generator, effective_date)

    insureds = data.get("insureds")
    if isinstance(insureds, dict):
        quote_brokerage_date = _extract_brokerage_insured_date_from_quote(documents)
        quote_brokerage_date_full = _to_full_date(generator, quote_brokerage_date)
        if quote_brokerage_date_full is not None:
            insureds["insured_with_broker_since"] = quote_brokerage_date_full
            print(f"[INFO] Set insured_with_broker_since from Quote Brokerage Insured: {quote_brokerage_date_full}")
        elif not _is_missing(effective_date_full):
            insureds["insured_with_broker_since"] = effective_date_full
            print("[INFO] Filled insured_with_broker_since from policy_effective_date (Brokerage Insured empty on Quote)")
        else:
            insured_with_broker_since = _to_full_date(generator, insureds.get("insured_with_broker_since"))
            if insured_with_broker_since is not None:
                insureds["insured_with_broker_since"] = insured_with_broker_since

    drivers = data.get("driver")
    applicant_info = data.get("applicant_information") if isinstance(data.get("applicant_information"), dict) else None
    mvr_index = _build_mvr_header_date_index(documents)
    autoplus_earliest = _extract_earliest_autoplus_report_date(documents)
    if isinstance(drivers, list):
        for driver_idx, driver in enumerate(drivers):
            if not isinstance(driver, dict):
                continue

            # Backward compatibility: migrate legacy request_date_time key.
            if _is_missing(driver.get("MVR_request_date_time")) and not _is_missing(driver.get("request_date_time")):
                driver["MVR_request_date_time"] = driver.get("request_date_time")
            driver.pop("request_date_time", None)

            # Derive MVR report status from convictions when missing.
            if _is_missing(driver.get("MVR_report_status")):
                if _has_conviction_detail(driver.get("convictions")):
                    driver["MVR_report_status"] = "received-with detail"
                else:
                    driver["MVR_report_status"] = "received-clean"

            if (
                _is_missing(driver.get("insured_without_interruption_since"))
                and _is_no_insurance_record(driver)
                and not _is_missing(effective_date)
            ):
                driver["insured_without_interruption_since"] = _to_full_date(generator, effective_date)
                print("[INFO] Filled insured_without_interruption_since from policy_effective_date for no-insurance-record driver")

            insured_since = _to_full_date(generator, driver.get("insured_without_interruption_since"))
            if insured_since is not None:
                driver["insured_without_interruption_since"] = insured_since

            if _is_missing(driver.get("Consent_Date")):
                driver_consent_date = _compute_consent_date_for_driver(
                    driver,
                    applicant_info,
                    is_primary=(driver_idx == 0),
                    mvr_index=mvr_index,
                    autoplus_earliest=autoplus_earliest,
                )
                if driver_consent_date:
                    driver["Consent_Date"] = driver_consent_date

            if driver.get("lapse_in_insurance") == "Yes":
                _promote_lapse_fields_to_arrays(driver)
                _strip_empty_trailing_lapses(driver)

            _normalize_non_payment_company(driver)

            has_no_auto_lapse = any(
                isinstance(desc, str) and desc.strip().lower() == "no automobile"
                for desc in _lapse_descriptions_iter(driver.get("lapse_in_insurance_description"))
            )
            if (
                driver.get("lapse_in_insurance") == "Yes"
                and has_no_auto_lapse
                and _is_missing(driver.get("expiry_date"))
                and not _is_missing(effective_date)
            ):
                driver["expiry_date"] = _to_full_date(generator, effective_date)
                print("[INFO] Filled expiry_date for No Automobile lapse using policy_effective_date")

            expiry_date = _to_full_date(generator, driver.get("expiry_date"))
            if expiry_date is not None:
                driver["expiry_date"] = expiry_date

            previous_insurer = driver.get("previous_insurer")
            if isinstance(previous_insurer, str) and previous_insurer.strip().lower() != "no prior insurer":
                years = _years_with_previous_insurer_from_driver_dates(
                    generator,
                    driver.get("insured_without_interruption_since"),
                    driver.get("expiry_date"),
                )
                if years is not None:
                    driver["number_of_years_with_previous_insurer"] = years

    risks = data.get("risk")
    # Backward compatibility: some model responses still emit a single risk object.
    # Normalize to list so downstream logic supports multi-risk uniformly.
    if isinstance(risks, dict):
        data["risk"] = [risks]
        risks = data["risk"]
        print("[INFO] Normalized Intact risk object to risk array")
    if isinstance(risks, list):
        vin_model_cache: Dict[str, Optional[str]] = {}
        for risk in risks:
            if not isinstance(risk, dict):
                continue
            if not _is_missing(risk.get("model")):
                continue
            vin = risk.get("serial_number")
            if _is_missing(vin):
                continue
            vin_key = str(vin).strip().upper()
            if vin_key not in vin_model_cache:
                vin_model_cache[vin_key] = _decode_vin_model_detail(vin_key)
            model_detail = vin_model_cache[vin_key]
            if model_detail:
                risk["model"] = model_detail
                print(f"[INFO] Filled Intact risk model from VIN {vin_key}: {model_detail}")

    return data


def apply(generator, data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
    """Run Intact post-processing in existing order."""
    company = getattr(generator, "company", "")
    _beacon_interest(
        "intact_auto_apply_enter",
        company=company,
        interest_before=_summarize_risk_interest(data),
        documents=_summarize_documents_for_interest(documents),
    )
    data, intact_date_fixes = generator._normalize_intact_dates(data)
    if intact_date_fixes > 0:
        print(f"[INFO] Normalized {intact_date_fixes} Intact date field(s) by configured format")
    data = generator._remove_non_intact_membership_fields(data)
    data = _apply_intact_defaults(generator, data, documents)
    data = _apply_dual_applicant_from_application(data, documents)
    data = _apply_mvr_names_from_documents(data, documents)
    data = _apply_mvr_request_datetime_from_documents(generator, data, documents)
    data = _apply_mvr_name_to_second_applicant(data, documents)
    data = _normalize_assignment_usage_from_quote(data, documents)
    data = _merge_root_address_into_applicant_information(data)
    data = _normalize_intact_applicant_information(data)
    data = _promote_additional_driver_identity_blocks(data)
    data = _normalize_intact_claim_total_amount_paid(data)
    data = _normalize_intact_coverages(data, documents)
    data = _normalize_winter_tires_from_quote_discount(data, documents)
    data = _apply_interest_from_application(data, documents)
    data = _remove_second_applicant_unless_dual_on_application(data, documents)
    _beacon_interest(
        "before_normalize_intact_structure",
        interest=_summarize_risk_interest(data),
    )
    data = generator._normalize_intact_structure(data)
    _beacon_interest(
        "intact_auto_apply_exit",
        interest_after=_summarize_risk_interest(data),
    )
    return data

import re
import json
from typing import Dict, Optional
from datetime import datetime, date
from urllib import parse, request


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


# Staging keys on driver[i] (i>=1); promoted to root driver_{i+1}_information / driver_{i+1}_address.
_DRIVER_IDENTITY_KEYS = (
    "last_name",
    "first_name",
    "gender",
    "date_of_birth",
    "marital_status",
)
_APPLICANT_ADDRESS_KEYS = ("postal_code", "full_address")
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


# MVR header sits at the very top-right of each MVR document and looks like:
#   *** MOTOR VEHICLE RECORD - YYYY/MM/DD ***
# This header date is the authoritative MVR "consent" date for that driver.
_MVR_HEADER_PATTERN = re.compile(
    r"MOTOR\s+VEHICLE\s+RECORD\s*-\s*(\d{4}[/-]\d{2}[/-]\d{2})",
    flags=re.IGNORECASE,
)
_MVR_NAME_PATTERN = re.compile(
    r"Name\s*:\s*([^\n\r]+)",
    flags=re.IGNORECASE,
)
_MVR_LICENCE_PATTERN = re.compile(
    r"Licence\s*:\s*(\S+)",
    flags=re.IGNORECASE,
)


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
    text = name_raw.strip()
    if not text:
        return None

    # Trailing comma with no first name (e.g. 'SMITH,') yields one non-empty part.
    parts = [part.strip() for part in text.split(",")]
    parts = [part for part in parts if part]
    if not parts:
        return None

    last_name = parts[0]
    if len(parts) >= 2:
        return last_name, parts[1]
    return last_name, last_name


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

        name_match = _MVR_NAME_PATTERN.search(content)
        if not name_match:
            continue
        parsed = _parse_mvr_name(name_match.group(1))
        if not parsed:
            continue

        licence_match = _MVR_LICENCE_PATTERN.search(content)
        licence = licence_match.group(1).strip() if licence_match else ""
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

    licence = driver.get("licence_number")
    licence_key = str(licence).strip() if not _is_missing(licence) else ""

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


def _build_mvr_header_date_index(documents: Optional[Dict[str, str]]):
    """
    Return a list of (doc_key, header_date, upper_content) for every MVR document.
    Only the FIRST `*** MOTOR VEHICLE RECORD - YYYY/MM/DD ***` match in each document
    is kept, since that is the top-of-page header in the upper-right corner.
    """
    index = []
    if not isinstance(documents, dict):
        return index

    for doc_key, content in documents.items():
        if not isinstance(doc_key, str) or not isinstance(content, str) or not content:
            continue
        if not doc_key.upper().startswith("MVR"):
            continue
        match = _MVR_HEADER_PATTERN.search(content)
        if not match:
            continue
        header_date = _parse_date_text(match.group(1))
        if header_date is None:
            continue
        index.append((doc_key, header_date, content.upper()))
    return index


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


def _normalize_intact_additional_coverages(data: Dict) -> Dict:
    """
    Consolidate legacy coverage arrays into coverages.additional_coverages.
    Keep every non-empty coverage/discount entry — including ': 0' values.
    """
    if not isinstance(data, dict):
        return data

    coverages = data.get("coverages")
    if not isinstance(coverages, dict):
        return data

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

    if merged:
        coverages["additional_coverages"] = merged
    elif "additional_coverages" in coverages and isinstance(coverages["additional_coverages"], list):
        coverages["additional_coverages"] = [
            str(x).strip()
            for x in coverages["additional_coverages"]
            if x is not None and str(x).strip()
        ]

    return data


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
    data, intact_date_fixes = generator._normalize_intact_dates(data)
    if intact_date_fixes > 0:
        print(f"[INFO] Normalized {intact_date_fixes} Intact date field(s) by configured format")
    data = generator._remove_non_intact_membership_fields(data)
    data = _apply_intact_defaults(generator, data, documents)
    data = _apply_mvr_names_from_documents(data, documents)
    data = _normalize_assignment_usage_from_quote(data, documents)
    data = _merge_root_address_into_applicant_information(data)
    data = _normalize_intact_applicant_information(data)
    data = _promote_additional_driver_identity_blocks(data)
    data = _normalize_intact_claim_total_amount_paid(data)
    data = _normalize_intact_additional_coverages(data)
    return generator._normalize_intact_structure(data)

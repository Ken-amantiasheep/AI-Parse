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
_DRIVER_ADDRESS_KEYS = ("postal_code", "full_address")
_ASSIGNMENT_COMMON_KEYS = (
    "type_of_use",
    "km_toward_work",
    "annual_km",
    "annual_business_km",
    "automobile_rented_or_leased_to_others",
    "automobile_used_to_carry_passengers_for_compensation_or_hire",
    "automobile_carry_explosives_or_radioactive_materials",
)


def _promote_additional_driver_identity_blocks(data: Dict) -> Dict:
    """
    For Intact Auto, second and subsequent drivers get root-level blocks matching
    applicant_information + address shape: driver_2_information, driver_2_address, etc.
    Values are taken from the corresponding driver[] element, then those keys are removed
    from the driver object. The first driver must not carry these staging keys.
    """
    if not isinstance(data, dict):
        return data

    drivers = data.get("driver")
    if not isinstance(drivers, list):
        return data

    root_address = data.get("address") if isinstance(data.get("address"), dict) else {}

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

        if not addr.get("postal_code") and not _is_missing(root_address.get("postal_code")):
            addr["postal_code"] = root_address["postal_code"]
        if not addr.get("full_address") and not _is_missing(root_address.get("full_address")):
            addr["full_address"] = root_address["full_address"]

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


def _extract_assignment_values_by_vehicle_from_documents(documents: Optional[Dict[str, str]]) -> Dict[int, Dict]:
    """
    Extract per-vehicle assignment values from quote text blocks like:
    Vehicle N of M ... then a line near "Primary Use / Annual km / Business km / Daily km".
    """
    if not isinstance(documents, dict) or not documents:
        return {}

    full_text = "\n".join(v for v in documents.values() if isinstance(v, str))
    if not full_text:
        return {}

    vehicle_values: Dict[int, Dict] = {}
    block_pattern = re.compile(
        r"Vehicle\s+(\d+)\s+of\s+\d+([\s\S]*?)(?=Vehicle\s+\d+\s+of\s+\d+|$)",
        flags=re.IGNORECASE,
    )

    for match in block_pattern.finditer(full_text):
        vehicle_idx = int(match.group(1))
        block = match.group(2)
        marker = re.search(r"Primary\s+Use[\s\S]{0,80}?Daily\s*km", block, flags=re.IGNORECASE)
        if not marker:
            continue

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
            continue

        number_matches = list(re.finditer(r"\d+", candidate_line))
        if not number_matches:
            continue

        first_num_start = number_matches[0].start()
        type_of_use = candidate_line[:first_num_start].strip()
        nums = [int(m.group()) for m in number_matches]
        if not type_of_use or not nums:
            continue

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

        vehicle_values[vehicle_idx] = {
            "type_of_use": type_of_use,
            "annual_km": annual_km,
            "annual_business_km": annual_business_km,
            "km_toward_work": daily_km,
        }

    return vehicle_values


def _normalize_multi_risk_assignment(data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
    """
    For Intact Auto multi-risk outputs, assignment should carry a full per-vehicle block.
    When risk count > 1 and assignment contains shared top-level usage fields, copy those
    fields into each vehicle_N block and remove duplicated top-level fields.
    """
    if not isinstance(data, dict):
        return data

    risks = data.get("risk")
    if not isinstance(risks, list) or len(risks) <= 1:
        return data

    assignment = data.get("assignment")
    if not isinstance(assignment, dict):
        return data

    parsed_vehicle_values = _extract_assignment_values_by_vehicle_from_documents(documents)

    # Build defaults from top-level shared fields first; fall back to vehicle_1 fields.
    # This ensures every additional vehicle gets a full set even when model only filled vehicle_1.
    default_values = {}
    for field_key in _ASSIGNMENT_COMMON_KEYS:
        if field_key in assignment:
            default_values[field_key] = assignment[field_key]

    vehicle_1 = assignment.get("vehicle_1")
    if isinstance(vehicle_1, dict):
        for field_key in _ASSIGNMENT_COMMON_KEYS:
            if field_key not in default_values and field_key in vehicle_1:
                default_values[field_key] = vehicle_1[field_key]

    if not default_values:
        return data

    for i in range(1, len(risks) + 1):
        vehicle_key = f"vehicle_{i}"
        vehicle_assignment = assignment.get(vehicle_key)
        if not isinstance(vehicle_assignment, dict):
            vehicle_assignment = {}
            assignment[vehicle_key] = vehicle_assignment

        # Prefer explicit per-vehicle values parsed from quote blocks.
        if i in parsed_vehicle_values:
            vehicle_assignment.update(parsed_vehicle_values[i])

        for field_key in _ASSIGNMENT_COMMON_KEYS:
            if field_key in default_values and field_key not in vehicle_assignment:
                vehicle_assignment[field_key] = default_values[field_key]

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


_COVERAGE_LEGACY_ARRAY_KEYS = (
    "section_optional_coverages",
    "accident_benefits_standard_benefits",
)


def _coverage_entry_has_zero_value(entry) -> bool:
    """True if 'Name: 0' style entry should be dropped."""
    if not isinstance(entry, str):
        return False
    text = entry.strip()
    if not text:
        return True
    if ":" not in text:
        return False
    _, _, value_part = text.partition(":")
    value_text = value_part.strip().replace(",", "").replace("$", "")
    if not value_text:
        return False
    try:
        return float(value_text) == 0.0
    except ValueError:
        return value_text in {"0", "0.0", "0.00"}


def _normalize_intact_additional_coverages(data: Dict) -> Dict:
    """
    Consolidate legacy coverage arrays into coverages.additional_coverages and
    drop entries whose numeric suffix is zero.
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
            if not text or _coverage_entry_has_zero_value(text):
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
            if x is not None
            and str(x).strip()
            and not _coverage_entry_has_zero_value(str(x).strip())
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
        if _is_missing(insureds.get("insured_with_broker_since")) and not _is_missing(effective_date_full):
            insureds["insured_with_broker_since"] = effective_date_full
            print("[INFO] Filled insured_with_broker_since from policy_effective_date")

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

            lapse_desc = driver.get("lapse_in_insurance_description")
            if (
                driver.get("lapse_in_insurance") == "Yes"
                and isinstance(lapse_desc, str)
                and lapse_desc.strip().lower() == "no automobile"
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
    data = _normalize_multi_risk_assignment(data, documents)
    data = _promote_additional_driver_identity_blocks(data)
    data = _normalize_intact_claim_total_amount_paid(data)
    data = _normalize_intact_additional_coverages(data)
    return generator._normalize_intact_structure(data)

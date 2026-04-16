import re
import json
from typing import Dict, Optional
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

    drivers = data.get("driver")
    if isinstance(drivers, list):
        for driver in drivers:
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
    data = _promote_additional_driver_identity_blocks(data)
    return generator._normalize_intact_structure(data)

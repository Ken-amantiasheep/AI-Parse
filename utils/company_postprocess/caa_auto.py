import re
from typing import Dict, Optional


def _fix_business_km_by_primary_use(data: Dict) -> int:
    """
    Enforce: business_km can only have a value when primary_use is 'Business'.
    If primary_use is not 'Business' and business_km has a value, move it to
    daily_km (if daily_km is empty) then clear business_km.
    """
    vehicles = data.get("vehicles_information")
    if not isinstance(vehicles, dict):
        return 0

    corrected = 0
    for vehicle_key, vehicle in vehicles.items():
        if not isinstance(vehicle, dict):
            continue

        primary_use = vehicle.get("primary_use")
        if isinstance(primary_use, str) and primary_use.strip().lower() == "business":
            continue

        business_km = vehicle.get("business_km")
        if business_km is None or (isinstance(business_km, str) and not business_km.strip()):
            continue

        daily_km = vehicle.get("daily_km")
        daily_km_empty = daily_km is None or (isinstance(daily_km, str) and not daily_km.strip())

        if daily_km_empty:
            vehicle["daily_km"] = business_km
            print(
                f"[WARNING] Vehicle '{vehicle_key}': primary_use='{primary_use}' is not Business "
                f"but business_km='{business_km}'. Moved to daily_km and cleared business_km."
            )
        else:
            print(
                f"[WARNING] Vehicle '{vehicle_key}': primary_use='{primary_use}' is not Business "
                f"but business_km='{business_km}'. Clearing business_km."
            )

        vehicle["business_km"] = None
        corrected += 1

    return corrected


def _has_labeled_name_evidence(all_text_upper: str, token_upper: str, labels) -> bool:
    """Check whether token appears as value for any of the provided name labels."""
    if not token_upper:
        return False
    escaped = re.escape(token_upper)
    for label in labels:
        pattern = rf"{label}\s*[:#-]?\s*{escaped}\b"
        if re.search(pattern, all_text_upper):
            return True
    return False


def _fix_coapplicant_name_order_by_document_labels(data: Dict, documents: Optional[Dict[str, str]]) -> int:
    """
    If document text explicitly labels co-applicant first/last name opposite to
    current JSON values, swap first_name and last_name.
    """
    if not isinstance(data, dict) or not isinstance(documents, dict) or not documents:
        return 0

    coapp = data.get("coapplicant_information")
    if not isinstance(coapp, dict):
        return 0

    first_name = coapp.get("first_name")
    last_name = coapp.get("last_name")
    if not isinstance(first_name, str) or not isinstance(last_name, str):
        return 0

    first_name = first_name.strip()
    last_name = last_name.strip()
    if not first_name or not last_name:
        return 0
    if first_name.upper() == last_name.upper():
        return 0

    all_text_upper = " ".join(str(v) for v in documents.values()).upper()
    if not all_text_upper.strip():
        return 0

    first_labels = [
        r"FIRST\s*NAME",
        r"GIVEN\s*NAME",
    ]
    last_labels = [
        r"LAST\s*NAME",
        r"SURNAME",
        r"FAMILY\s*NAME",
    ]

    # Positive evidence that current fields are reversed:
    # - current last_name appears under first-name labels
    # - current first_name appears under last-name labels
    reversed_first_evidence = _has_labeled_name_evidence(all_text_upper, last_name.upper(), first_labels)
    reversed_last_evidence = _has_labeled_name_evidence(all_text_upper, first_name.upper(), last_labels)

    # Negative evidence that current mapping is already correct.
    current_first_evidence = _has_labeled_name_evidence(all_text_upper, first_name.upper(), first_labels)
    current_last_evidence = _has_labeled_name_evidence(all_text_upper, last_name.upper(), last_labels)

    if reversed_first_evidence and reversed_last_evidence and not (current_first_evidence and current_last_evidence):
        coapp["first_name"] = last_name
        coapp["last_name"] = first_name
        print(
            "[INFO] Corrected coapplicant_information name order from labeled document evidence "
            f"(first_name='{first_name}', last_name='{last_name}' -> first_name='{last_name}', last_name='{first_name}')."
        )
        return 1

    return 0


def _fix_coapplicant_name_order_by_fullname_frequency(data: Dict, documents: Optional[Dict[str, str]]) -> int:
    """
    For ambiguous cases without explicit labels, decide order by document full-name frequency.
    If "LAST FIRST" appears more often than "FIRST LAST", swap co-applicant and keep related
    driver sections consistent.
    """
    if not isinstance(data, dict) or not isinstance(documents, dict) or not documents:
        return 0

    coapp = data.get("coapplicant_information")
    if not isinstance(coapp, dict):
        return 0

    first_name = coapp.get("first_name")
    last_name = coapp.get("last_name")
    if not isinstance(first_name, str) or not isinstance(last_name, str):
        return 0

    first_name = first_name.strip().upper()
    last_name = last_name.strip().upper()
    if not first_name or not last_name or first_name == last_name:
        return 0

    all_text_upper = " ".join(str(v) for v in documents.values()).upper()
    if not all_text_upper.strip():
        return 0

    current_order = rf"\b{re.escape(first_name)}\s+{re.escape(last_name)}\b"
    reversed_order = rf"\b{re.escape(last_name)}\s+{re.escape(first_name)}\b"
    current_count = len(re.findall(current_order, all_text_upper))
    reversed_count = len(re.findall(reversed_order, all_text_upper))

    if reversed_count <= current_count or reversed_count == 0:
        return 0

    coapp["first_name"] = last_name
    coapp["last_name"] = first_name
    fixes = 1

    old_full = f"{first_name} {last_name}"
    new_full = f"{last_name} {first_name}"

    # Keep driver_list consistent
    driver_list = data.get("driver_list")
    if isinstance(driver_list, list):
        for i, item in enumerate(driver_list):
            if isinstance(item, str) and item.strip().upper() == old_full:
                driver_list[i] = new_full
                fixes += 1

    # Keep drivers_information consistent (key + fields)
    drivers_info = data.get("drivers_information")
    if isinstance(drivers_info, dict):
        src_key = None
        for key in list(drivers_info.keys()):
            if isinstance(key, str) and key.strip().upper() == old_full:
                src_key = key
                break
        if src_key is not None:
            driver_obj = drivers_info.pop(src_key)
            if isinstance(driver_obj, dict):
                driver_obj["first_name"] = last_name
                driver_obj["last_name"] = first_name
            drivers_info[new_full] = driver_obj
            fixes += 1

    # Keep vehicle driver display strings consistent, e.g. "RAJVINDER KAUR (Occ)"
    vehicles = data.get("vehicles_information")
    if isinstance(vehicles, dict):
        for vehicle in vehicles.values():
            if not isinstance(vehicle, dict):
                continue
            drivers = vehicle.get("drivers")
            if not isinstance(drivers, list):
                continue
            updated = []
            changed = False
            for d in drivers:
                if not isinstance(d, str):
                    updated.append(d)
                    continue
                replaced = re.sub(rf"\b{re.escape(old_full)}\b", new_full, d)
                if replaced != d:
                    changed = True
                updated.append(replaced)
            if changed:
                vehicle["drivers"] = updated
                fixes += 1

    print(
        "[INFO] Corrected co-applicant name order by full-name frequency evidence "
        f"(doc count {new_full}={reversed_count} > {old_full}={current_count})."
    )
    return fixes


def apply(generator, data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
    """Run CAA post-processing in existing order."""
    data, cfg_date_changes = generator._normalize_dates_by_fields_config(data)
    if cfg_date_changes > 0:
        print(f"[INFO] Normalized {cfg_date_changes} date field(s) to configured formats (CAA Auto)")

    data, changed_count = generator._normalize_caa_birth_dates(data)
    if changed_count > 0:
        print(f"[INFO] Normalized {changed_count} date_of_birth field(s) to MM/DD/YYYY")

    data, corrected_vehicles = generator._apply_caa_vehicle_purchase_sanity(data)
    if corrected_vehicles > 0:
        print(f"[INFO] Corrected purchase table column misalignment in {corrected_vehicles} vehicle(s)")

    data, misalignment_fixes = generator._fix_vehicle_table_column_misalignment(data)
    if misalignment_fixes > 0:
        print(f"[INFO] Fixed {misalignment_fixes} vehicle information table column misalignment issue(s)")

    business_km_fixes = _fix_business_km_by_primary_use(data)
    if business_km_fixes > 0:
        print(f"[INFO] Fixed {business_km_fixes} vehicle(s) where business_km was set for non-Business primary_use")

    coapp_name_fixes = _fix_coapplicant_name_order_by_document_labels(data, documents)
    if coapp_name_fixes > 0:
        print(f"[INFO] Fixed {coapp_name_fixes} co-applicant name order issue(s)")
    else:
        coapp_name_fixes = _fix_coapplicant_name_order_by_fullname_frequency(data, documents)
        if coapp_name_fixes > 0:
            print(f"[INFO] Fixed {coapp_name_fixes} co-applicant name consistency issue(s) by full-name frequency")

    return generator._apply_caa_output_normalization(data, documents)

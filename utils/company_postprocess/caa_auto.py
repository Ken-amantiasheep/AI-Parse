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

    return generator._apply_caa_output_normalization(data, documents)

from typing import Dict, Optional


def apply(generator, data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
    """Run CAA post-processing in existing order."""
    data, changed_count = generator._normalize_caa_birth_dates(data)
    if changed_count > 0:
        print(f"[INFO] Normalized {changed_count} date_of_birth field(s) to MM/DD/YYYY")

    data, corrected_vehicles = generator._apply_caa_vehicle_purchase_sanity(data)
    if corrected_vehicles > 0:
        print(f"[INFO] Corrected purchase table column misalignment in {corrected_vehicles} vehicle(s)")

    data, misalignment_fixes = generator._fix_vehicle_table_column_misalignment(data)
    if misalignment_fixes > 0:
        print(f"[INFO] Fixed {misalignment_fixes} vehicle information table column misalignment issue(s)")

    return generator._apply_caa_output_normalization(data, documents)

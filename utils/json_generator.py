"""
JSON Generator - Generate JSON from documents using Claude API
"""
import json
import os
import sys
import re
from datetime import datetime
from typing import Dict, Optional, Tuple
from anthropic import Anthropic
import requests

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.document_reader import extract_text_from_documents
from utils import json_generator_pure
from utils import company_config
from utils.company_postprocess import pipeline as company_postprocess_pipeline
from utils.company_validators import get_required_top_level_fields
from utils.prompt_parts import common as prompt_common
from utils.prompt_parts import caa_memo as prompt_caa_memo

class IntactJSONGenerator:
    """Generate JSON required for Intact upload from documents"""
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        company: str = "Intact",
        mode: Optional[str] = None,
        api_key: Optional[str] = None,
        gateway_url: Optional[str] = None,
        gateway_token: Optional[str] = None,
        timeout_sec: Optional[int] = None
    ):
        """
        Initialize generator
        
        Args:
            config_path: Configuration file path, if None uses default path
            company: Company name (Intact, CAA, Aviva, etc.)
        """
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "config",
                "config.json"
            )
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.mode = (mode or self.config.get("mode", "direct")).lower()
        self.model = self.config.get("model", "claude-sonnet-4-20250514")
        self.max_tokens = self.config.get("max_tokens", 4096)
        self.temperature = self.config.get("temperature", 0.1)
        self.timeout_sec = int(timeout_sec or self.config.get("timeout_sec", 180))
        self.gateway_url = gateway_url or self.config.get("gateway_url", "http://127.0.0.1:8080")
        self.gateway_token = gateway_token or self.config.get("gateway_token", "")
        self.use_company_schema_validation = bool(self.config.get("use_company_schema_validation", False))
        self.company = company

        if self.mode == "gateway":
            self.client = None
        else:
            resolved_api_key = api_key or self.config.get("api_key")
            if not resolved_api_key:
                raise ValueError("api_key is required when mode is 'direct'")
            self.client = Anthropic(api_key=resolved_api_key)

        self._load_fields_config(company)

    def _load_fields_config(self, company: str):
        """Load company-specific fields configuration."""
        config_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config"
        )
        
        company_lower = company.lower()
        routing = company_config.load_company_routing(config_dir)
        config_name = company_config.resolve_fields_config_name(company, routing)
        
        fields_config_path = os.path.join(config_dir, config_name)

        if os.path.exists(fields_config_path):
            with open(fields_config_path, 'r', encoding='utf-8') as f:
                self.fields_config = json.load(f)
        else:
            # Fallback: try old naming convention for backward compatibility
            old_config_path = os.path.join(config_dir, f"{company_lower}_fields_config.json")
            if os.path.exists(old_config_path):
                with open(old_config_path, 'r', encoding='utf-8') as f:
                    self.fields_config = json.load(f)
            else:
                self.fields_config = {
                    "company": company,
                    "description": f"{company} insurance JSON output format configuration",
                    "fields": {}
                }

    def _set_company(self, company: Optional[str]):
        """Switch company config when requested."""
        if company and company != self.company:
            self.company = company
            self._load_fields_config(company)
    
    def _is_caa_company(self) -> bool:
        """Check if company is CAA-related (CAA, CAA_Auto, CAA_property, etc.)"""
        company_upper = self.company.upper()
        return company_upper == "CAA" or company_upper.startswith("CAA_")

    def _is_caa_auto_company(self) -> bool:
        """CAA automobile lines only (excludes CAA_property)."""
        u = self.company.upper()
        if u.endswith("_PROPERTY") or u == "CAA_PROPERTY":
            return False
        return u == "CAA" or u.startswith("CAA_")

    def _is_intact_company(self) -> bool:
        """Check if company is Intact-related (Intact, Intact_Auto, etc.)"""
        company_upper = self.company.upper()
        return company_upper == "INTACT" or company_upper.startswith("INTACT_")

    def _is_intact_auto_company(self) -> bool:
        """Intact Auto JSON extraction only (legacy `Intact` alias included; not CAA or other lines)."""
        u = self.company.upper()
        if u == "INTACT" or u == "INTACT_AUTO":
            return True
        return u.startswith("INTACT_") and u.endswith("_AUTO")

    def _build_fields_prompt_section(self, fields_config: Dict) -> str:
        """Build prompt section from fields configuration"""
        if not fields_config.get("fields"):
            # If no fields configured, return default structure
            return self._get_default_fields_structure()
        
        sections = []
        section_num = 1
        
        for section_name, section_data in fields_config["fields"].items():
            section_text = f"{section_num}. **{section_name}**"
            
            if section_data.get("required", False):
                section_text += " (required):"
            else:
                section_text += " (optional):"
            
            sections.append(section_text)
            
            if section_data.get("description"):
                sections.append(f"   {section_data['description']}")
            
            # Add fields
            if "fields" in section_data:
                for field_name, field_info in section_data["fields"].items():
                    field_type = field_info.get("type", "string")
                    field_mode = field_info.get("mode", "free_text")
                    field_required = field_info.get("required", False)
                    field_description = field_info.get("description", "")
                    field_extraction_logic = field_info.get("extraction_logic", "")
                    field_multiple = field_info.get("multiple", False)
                    
                    # Handle array/multiple fields
                    if field_type == "array" or field_multiple:
                        field_line = f"   - {field_name}: array of strings"
                    else:
                        field_line = f"   - {field_name}: {field_type}"
                    
                    if field_mode == "dropdown":
                        options = field_info.get("options", [])
                        if options:
                            # Convert all options to strings to handle both string and numeric values
                            options_str = ', '.join(str(opt) for opt in options)
                            if field_multiple or field_type == "array":
                                field_line += f" (can select multiple from: {options_str})"
                            else:
                                field_line += f" (options: {options_str})"
                    
                    if field_mode == "radio":
                        options = field_info.get("options", [])
                        if options:
                            # Convert all options to strings to handle both string and numeric values
                            options_str = ', '.join(str(opt) for opt in options)
                            field_line += f" (select one: {options_str})"
                    
                    if field_mode == "date":
                        date_format = self._get_configured_date_format(
                            {
                                "description": field_description,
                                "extraction_logic": field_extraction_logic,
                            },
                            field_name,
                        )
                        field_line += f" (format: {date_format})"
                    
                    if not field_required:
                        field_line += " (optional)"
                    
                    # Add extraction logic prominently
                    if field_extraction_logic:
                        # Special emphasis for CAA membership fields
                        if field_name in ("caa_membership", "caa_membership_number"):
                            field_line += f"\n     ⚠️ CRITICAL FIELD - READ CAREFULLY ⚠️"
                            field_line += f"\n     → EXTRACTION LOGIC: {field_extraction_logic}"
                            field_line += f"\n     → IMPORTANT: Search for 'Group discount apply: yes - CAA' pattern. If found, caa_membership MUST be 'Yes' and caa_membership_number MUST be extracted."
                        # Special emphasis for coverages_information to include OPCF options
                        elif field_name == "coverages_information":
                            field_line += f"\n     ⚠️ CRITICAL: This field includes BOTH standard coverages AND ALL OPCF options/protections ⚠️"
                            field_line += f"\n     → EXTRACTION LOGIC: {field_extraction_logic}"
                            field_line += f"\n     → MANDATORY CHECKLIST: Extract EVERY row from coverage/premium tables in Quote PDF, including:"
                            field_line += f"\n       1. Standard coverages: 'Bodily Injury', 'Property Damage', 'All Perils', 'Accident Benefits', 'Direct Compensation', 'Uninsured Automobile'"
                            field_line += f"\n       2. OPCF options: '#5 Rent or Lease', '#20 Loss of Use', '#27 Liab to Unowned Veh.', '#43a Limited Waiver', '#44 Family Protection'"
                            field_line += f"\n       3. Protection options: 'Minor Conviction Protection', 'Forgive & Forget', and ANY other protection types you see"
                            field_line += f"\n     → DO NOT SKIP ANY ROWS! Extract ALL coverages and protections found in the Quote PDF tables!"
                        else:
                            field_line += f"\n     → EXTRACTION LOGIC: {field_extraction_logic}"
                    
                    if field_description:
                        field_line += f"\n     → Description: {field_description}"
                    
                    sections.append(field_line)
            
            sections.append("")  # Empty line between sections
            section_num += 1
        
        return "\n".join(sections)

    @staticmethod
    def _build_intact_auto_json_format_requirements() -> str:
        """Intact Auto only: strict JSON and multi-vehicle `risk` array rules."""
        return """## Intact Auto — JSON output (mandatory)
- Output ONLY a single valid JSON object. Do not output markdown fences, comments, or explanatory text.
- JSON must be syntactically valid: include commas between array/object elements and use double quotes for keys/strings.
- For sections configured as arrays (for example `risk` in Intact Auto), ALWAYS output an array `[]`.
- If multiple vehicles/risks are found, include ALL of them in `risk` as separate array elements in the same order as the source document.

"""

    def _build_property_format_requirements(self) -> str:
        """Build critical format requirements section for property type"""
        requirements = """
## ⚠️ CRITICAL FORMAT REQUIREMENTS - MUST FOLLOW EXACTLY ⚠️

### 1. application_info.address.address Format (CRITICAL)

**❌ WRONG FORMAT**:
```json
"address": {
  "address": "6 BlueberryDr."  // ❌ Missing space, cannot identify street type
}
```

**✅ CORRECT FORMAT**:
```json
"address": {
  "address": "6 Blueberry Dr."  // ✅ Has space, can correctly separate street name and type
}
```

**Rules**:
- Street name and street type **MUST be separated by a space** in the address field
- Examples: "123 Main St", "456 Oak Ave", "789 Park Dr"
- Do NOT write: "123 MainSt", "456 OakAve" (missing space)

### 2. application_info.province Format (CRITICAL)

**❌ WRONG FORMAT**:
```json
"province": "Ontario"  // ❌ Full name
```

**✅ CORRECT FORMAT**:
```json
"province": "ON"  // ✅ Province abbreviation (2 uppercase letters)
```

**Province Abbreviation Reference**:
- Ontario → ON
- British Columbia → BC
- Alberta → AB
- Manitoba → MB
- Saskatchewan → SK
- Quebec → QC
- New Brunswick → NB
- Nova Scotia → NS
- Prince Edward Island → PE
- Newfoundland and Labrador → NL
- Yukon → YT
- Northwest Territories → NT
- Nunavut → NU

### 3. application_info.phone.number Format

**✅ RECOMMENDED FORMAT**:
```json
"phone": {
  "type": "Home",
  "number": "647-781-0777"  // ✅ Recommended: remove parentheses, use hyphens
}
```

**OR**:
```json
"phone": {
  "type": "Home",
  "number": "(647) 781-0777"  // ⚠️ Also acceptable, but removing parentheses is recommended
}
```

**Rules**:
- Recommended format: `###-###-####` (remove parentheses)
- Also acceptable: `(###) ###-####` (with parentheses)
- Do NOT use: `### ### ####` (space-separated)

### 4. application_info.prev_insurance.end_date Structure (CRITICAL)

**❌ WRONG FORMAT**:
```json
"prev_insurance": {
  "end_date": "2026-03-09"  // ❌ String format
}
```

**✅ CORRECT FORMAT**:
```json
"prev_insurance": {
  "end_date": {
    "month": "03",    // Must be two-digit string "01"-"12"
    "day": "09",      // Must be two-digit string "01"-"31"
    "year": "2026"    // Must be four-digit string "2024", "2025", etc.
  },
  "policy_number": "P97270368HAB"
}
```

**Conversion Rules**:
- If date is "2026-03-09" format, split into: month: "03", day: "09", year: "2026"
- If date is "03/09/2026" format, split into: month: "03", day: "09", year: "2026"
- If date doesn't exist, set end_date to null but keep prev_insurance object structure

### 5. coverages_information Structure (CRITICAL)

**❌ WRONG FORMAT**:
```json
"coverages_information": {
  "Residence": [...],
  "Contents": [...]
}
```

**✅ CORRECT FORMAT**:
```json
"coverages_information": [
  {
    "Residence": {
      "Coverage A - Dwelling": {
        "name": "Coverage A - Dwelling",
        "deductible": null,
        "amount": "$728,700",
        "premium": "$1,956"
      }
    }
  },
  {
    "Contents": {
      "Outbuildings": {
        "name": "Outbuildings",
        "deductible": null,
        "amount": "$145,740",
        "premium": "Inc."
      }
    }
  },
  {
    "Service Line Coverage": {
      "Service Line": {
        "name": "Service Line",
        "deductible": "$1,000",
        "amount": "$50,000",
        "premium": "$150"
      }
    }
  }
]
```

**Rules**:
- coverages_information MUST be an array [], NOT an object {}
- Each array element is an object containing one coverage class name as key
- Each coverage class value is an object containing multiple coverage items
- Each coverage item must have: name (string), deductible (string | null), amount (string), premium (string)

### 6. application_info Field Cleanup

**❌ WRONG FORMAT**:
```json
"application_info": {
  "membership": {
    "caa_membership": "Yes",
    "caa_membership_number": "6202822425653003"
  },
  "caa_membership": "No"  // ❌ Duplicate field
}
```

**✅ CORRECT FORMAT**:
```json
"application_info": {
  "membership": {
    "caa_membership": "Yes",
    "caa_membership_number": "6202822425653003"
  }
}
```

**Rules**: Do NOT have duplicate fields like caa_membership both in membership object and as top-level field.

### 7. effective_date Format

**✅ CORRECT FORMAT**:
```json
"effective_date": "2026-03-09"  // YYYY-MM-DD format string, NOT object
```

### 8. claims Array Default Value

**✅ CORRECT FORMAT**:
```json
"claims": []  // If no claims, use empty array [], NOT null
```

### 9. secondary_dwelling_information Format

**✅ CORRECT FORMAT**:
```json
"secondary_dwelling_information": null  // If not exists, use null
```

Or if exists:
```json
"secondary_dwelling_information": {
  "dwelling_type": "Homeowners",
  "location_and_coverage_information": {...},
  "dwelling_information": {...},
  // ... Same structure as primary_dwelling_information
}
```

### 10. primary_dwelling_information.dwelling_information.occupied_since Format (CRITICAL)

**❌ WRONG FORMAT**:
```json
{
  "primary_dwelling_information": {
    "dwelling_information": {
      // ❌ Missing occupied_since field
      "year_dwelling_built": "1995"
    }
  }
}
```

or

```json
{
  "primary_dwelling_information": {
    "dwelling_information": {
      "occupied_since": "2018-03-15"  // ❌ Wrong format (YYYY-MM-DD)
    }
  }
}
```

**✅ CORRECT FORMAT**:
```json
{
  "primary_dwelling_information": {
    "dwelling_information": {
      "occupied_since": "03/15/2018",  // ✅ MM/DD/YYYY format
      "year_dwelling_built": "1995",
      ...
    }
  }
}
```

**Field Details**:
- **Field Name**: `occupied_since`
- **Location**: `primary_dwelling_information.dwelling_information.occupied_since`
- **Type**: String (date)
- **Format**: `MM/DD/YYYY` (e.g., "03/15/2018")
- **Description**: The date when the insured first occupied/started living at the current property address
- **Required**: Yes (for all dwelling types: Homeowners, Tenants, Condominiums, Rented Dwelling)

**Where to Find This Information**:
Look for information in the quote or application PDFs such as:
- "Date moved in"
- "Occupied since"
- "Residence date"
- "Date of occupancy"
- "When did you move in"
- "How long have you lived here"

**⚠️ CRITICAL NOTES**:
1. **Date Format**: Must be `MM/DD/YYYY` format (NOT `YYYY-MM-DD`)
2. **Required for All Types**: This field is required for all dwelling types (Homeowners, Tenants, Condominiums, Rented Dwelling)
3. **Premium Calculation**: This field directly affects premium calculation. You MUST extract it accurately from the PDF. Do NOT use default values or guess.
4. **If Not Found**: If the information is truly not found in the documents, you must clearly indicate this in your output (use null, but document why)
5. **Secondary Dwelling**: If secondary dwelling exists, also add to `secondary_dwelling_information.dwelling_information.occupied_since`

### 11. insured_information.name Format (CRITICAL)

**❌ WRONG FORMAT**:
```json
"insured_information": {
  "name": "Lin"  // ❌ Only one word, cannot separate first name and last name
}
```

or

```json
"insured_information": {
  "name": "John A"  // ❌ Last Name "A" only has 1 character, must be at least 2 characters
}
```

**✅ CORRECT FORMAT**:
```json
"insured_information": {
  "name": "Zi Qing Lin"  // ✅ At least 2 words, last word "Lin" has 2+ characters
}
```

**Format Requirements**:
- MUST contain at least TWO words (separated by spaces)
- The LAST word is the Last Name and MUST be at least 2 characters
- All words before the last word form the First Name (must be at least 1 character)
- Can include middle names, which will be included in First Name
- Normalize multiple spaces to single space
- Remove special characters except hyphens

**Name Parsing Logic**:
- "Zi Qing Lin" → First Name: "Zi Qing", Last Name: "Lin" ✅
- "John Smith" → First Name: "John", Last Name: "Smith" ✅
- "Mary Jane Watson" → First Name: "Mary Jane", Last Name: "Watson" ✅

**Validation Rules**:
- [ ] name field contains at least two words (separated by spaces)
- [ ] Last word (Last Name) has at least 2 characters
- [ ] First word(s) (First Name) has at least 1 character
- [ ] No special characters that cause parsing failure
- [ ] Multiple spaces normalized to single space

**Common Errors to Avoid**:
- ❌ Single word name: "Lin" → Should be "Lin Lin" or infer from context
- ❌ Last Name too short: "John A" → Last Name "A" only 1 char, need at least 2
- ❌ Empty or whitespace-only: "" or "   " → Invalid

**Special Cases**:
- If PDF has only one word, add placeholder or infer from other fields
- If Last Name is only 1 character, need to handle or mark
- Names with prefixes (Mr., Mrs.) or suffixes (Jr., Sr.) should be handled appropriately

## Validation Checklist

Before outputting JSON, verify:

### Address Format
- [ ] `application_info.address.address` has space between street name and type
- [ ] Example: "6 Blueberry Dr." (NOT "6 BlueberryDr.")

### Province Format
- [ ] `application_info.province` uses 2-letter abbreviation (ON, BC, AB, etc.)
- [ ] NOT full name (Ontario, British Columbia, etc.)

### Date Format
- [ ] `insured_information.date_of_birth` is YYYY-MM-DD format
- [ ] `application_info.effective_date` is YYYY-MM-DD format
- [ ] `prev_insurance.end_date` is object format `{month, day, year}`
- [ ] `primary_dwelling_information.dwelling_information.occupied_since` is MM/DD/YYYY format (required)
- [ ] `secondary_dwelling_information.dwelling_information.occupied_since` is MM/DD/YYYY format (if secondary dwelling exists)

### Phone Format
- [ ] `application_info.phone.number` recommended format: `###-###-####` (remove parentheses)

### Name Format
- [ ] `insured_information.name` contains at least two words
- [ ] Last word (Last Name) has at least 2 characters

### Array Format
- [ ] `coverages_information` is array `[]`, NOT object `{}`
- [ ] `claims` uses `[]` instead of `null` if no data

### Other Checks
- [ ] application_info.prev_insurance.end_date is object {month, day, year} NOT string
- [ ] application_info has no duplicate fields
- [ ] secondary_dwelling_information is null if not exists
- [ ] coinsured_information.name (if exists) follows same format requirements
- [ ] primary_dwelling_information.dwelling_information.occupied_since exists and is MM/DD/YYYY format
- [ ] secondary_dwelling_information.dwelling_information.occupied_since exists (if secondary dwelling exists) and is MM/DD/YYYY format

## Common Errors to Avoid

1. ❌ Do NOT set address without space between street name and type (e.g., "BlueberryDr." → should be "Blueberry Dr.")
2. ❌ Do NOT set province as full name (e.g., "Ontario" → should be "ON")
3. ❌ Do NOT set end_date as string "2026-03-09" (should be object {month, day, year})
4. ❌ Do NOT set coverages_information as object {} (should be array [])
5. ❌ Do NOT set claims as null (use [])
6. ❌ Do NOT have duplicate fields in application_info
7. ❌ Do NOT set effective_date as object (should be string)
8. ❌ Do NOT set insured_information.name as single word (must have at least 2 words)
9. ❌ Do NOT set Last Name with only 1 character (must be at least 2 characters)
10. ❌ Do NOT use space-separated phone format (recommended: `###-###-####`)
11. ❌ Do NOT omit `occupied_since` field in `dwelling_information` (required for all dwelling types)
12. ❌ Do NOT use YYYY-MM-DD format for `occupied_since` (must be MM/DD/YYYY)

## FULL CAA_property OUTPUT EXAMPLE - FOLLOW THIS STRUCTURE

The overall JSON structure, section names, and nesting MUST follow this example for CAA_property outputs.

```json
{
  "address": {
    "address": "6 Blueberry Dr.",
    "city": "Scarborough",
    "province": "ON",
    "postal_code": "M1S3E9"
  },
  "phone": "647-781-0777",
  "policy_information": {
    "insured_since": "01/06/2014",
    "insured_with_brokerage_since": "03/09/2026",
    "auto_insured_since": null,
    "auto_current_insurer": "New Business",
    "property_insured_since": "04/01/2024",
    "property_current_insurer": "New Business",
    "multi_line_policy": "Yes",
    "combined_policy": "Yes",
    "multi_line_for_all_carriers": "Yes",
    "first_time_buyer": "No"
  },
  "insured_information": {
    "name": "Zi Qing Lin",
    "date_of_birth": "06/02/1976",
    "gender": "Male",
    "retired": null,
    "occupation": null,
    "employer": null,
    "date_hired": null,
    "full_time": "No"
  },
  "coinsured_information": {
    "name": "Yanxia Ke",
    "date_of_birth": "10/10/1980",
    "gender": "Female"
  },
  "primary_dwelling_information": {
    "dwelling_type": "Homeowners",
    "location_and_coverage_information": {
      "location": "6 BLUEBERRY DR, SCARBOROUGH - M1S3E9",
      "metres_to_hydrant": "Within 150 metres",
      "kilometres_to_firehall": "Within 5 kilometres",
      "coverage_type": "All Risk / All Risk",
      "single_limit": "Yes",
      "gbrc": "Yes",
      "dwelling_value": "$728,700",
      "dwelling_coverage": "$728,700",
      "outbuildings": "Limit",
      "contents": "Limit",
      "deductible": "$2,000",
      "liability": "$1,000,000",
      "rcc_included": "Yes",
      "last_home_evaluation": "02/24/2026",
      "home_evaluation_tool": "ezITV (iClarify Validated)",
      "hail_deductible": "Base",
      "hail_coverage": null,
      "wind_deductible": "Base",
      "wind_coverage": null,
      "water_deductible": "Base"
    },
    "dwelling_information": {
      "owner_occupied": "Yes",
      "year_dwelling_built": "1972",
      "occupied_since": "04/01/2024",
      "number_of_mortgages": "1",
      "number_of_families": "1",
      "structure": "Detached",
      "construction": "Frame (Wood)",
      "in_law_suite": "No",
      "basement_apartment": "No",
      "number_of_units": "1",
      "exterior_finish": "Brick Veneer",
      "garage": "Built-in",
      "number_of_cars": "2",
      "year_of_roof": "2021",
      "roof_renovated": "100%",
      "type_of_roof": "Asphalt Shingles",
      "slope": "Pitched",
      "impact_resistance": null,
      "year_of_plumbing": "2015",
      "plumbing_renovated": "100%",
      "type_of_plumbing": "Mixed – Copper/PVC",
      "year_of_electrical": "2015",
      "electrical_renovated": "100%",
      "electrical_service": "100 AMP",
      "type_of_electrical": "Copper",
      "electrical_panel": "Breakers",
      "number_of_storeys": "2",
      "total_living_area": "1691 sq. ft.",
      "basement_area": "530 sq. ft.",
      "finished_basement": "100%",
      "number_of_full_baths": "1",
      "number_of_half_baths": "1",
      "water_heater_year": "2020",
      "water_main_valve_shutoff": null,
      "number_of_sensors": null,
      "septic_system": "No"
    },
    "heating_information": {
      "approved": "Yes",
      "year": "2020",
      "renovated": "100%",
      "type": "Central Furnace - Gas",
      "chimney_type": null
    },
    "security_information": {
      "burglar_alarm": "None",
      "fire_alarm": "None",
      "number_of_smoke_detectors": "3",
      "number_of_fire_extinguishers": "0",
      "sprinkler_system": "None",
      "dead_bolt_locks": "Yes",
      "block_watch": "No",
      "walled_community": "No",
      "bars_on_windows": "No",
      "dog": "No"
    },
    "preventative_measures_information": {
      "alarmed_sump_pump": "No",
      "sump_pump_pit": "No",
      "backup_backflow_valve": null,
      "type": null,
      "auxiliary_power": null
    },
    "extended_coverages": {
      "Sewer Backup": {
        "amount": "Max",
        "deductible": "$2,000"
      },
      "Overland Water": {
        "amount": "Max",
        "deductible": "$2,000"
      }
    }
  },
  "secondary_dwelling_information": null,
  "coverages_information": [
    {
      "Residence": {
        "name": "Residence",
        "deductible": "$2,000",
        "amount": "$728,700",
        "premium": "$1,956"
      },
      "Outbuildings": {
        "name": "Outbuildings",
        "deductible": "$2,000",
        "amount": "$145,740",
        "premium": "Inc."
      },
      "Contents": {
        "name": "Contents",
        "deductible": "$2,000",
        "amount": "$582,960",
        "premium": "Inc."
      },
      "Additional Living Expenses": {
        "name": "Additional Living Expenses",
        "deductible": "$2,000",
        "amount": "$218,610",
        "premium": "Inc."
      },
      "Voluntary Medical": {
        "name": "Voluntary Medical",
        "deductible": "$2,000",
        "amount": "$5,000",
        "premium": "Inc."
      },
      "Voluntary Property": {
        "name": "Voluntary Property",
        "deductible": "$2,000",
        "amount": "$1,000",
        "premium": "Inc."
      },
      "Deductible": {
        "name": "Deductible",
        "deductible": "$2,000",
        "amount": "",
        "premium": "$-117"
      },
      "Replacement Cost Contents": {
        "name": "Replacement Cost Contents",
        "deductible": "$2,000",
        "amount": "",
        "premium": "Inc."
      },
      "Single Limit": {
        "name": "Single Limit",
        "deductible": "$2,000",
        "amount": "$1,676,010",
        "premium": "Inc."
      },
      "Guaranteed Building Replacement Cost": {
        "name": "Guaranteed Building Replacement Cost",
        "deductible": "$2,000",
        "amount": "",
        "premium": "Inc."
      },
      "Legal Liability": {
        "name": "Legal Liability",
        "deductible": "$2,000",
        "amount": "",
        "premium": ""
      },
      "Personal Insurance": {
        "name": "Personal Insurance",
        "deductible": "$2,000",
        "amount": "$1,000,000",
        "premium": "Inc."
      },
      "Discounts - Premiums may have been rounded.": {
        "name": "Discounts - Premiums may have been rounded.",
        "deductible": null,
        "amount": "",
        "premium": "$-666"
      },
      "CAA Member": {
        "name": "CAA Member",
        "deductible": null,
        "amount": "10%",
        "premium": "$-184"
      },
      "Multi-Line": {
        "name": "Multi-Line",
        "deductible": null,
        "amount": "12.5%",
        "premium": "$-186"
      },
      "Claims Free": {
        "name": "Claims Free",
        "deductible": null,
        "amount": "10%",
        "premium": "$-130"
      },
      "Seniors": {
        "name": "Seniors",
        "deductible": null,
        "amount": "10%",
        "premium": "$-165"
      },
      "Extended Coverages": {
        "name": "Extended Coverages",
        "deductible": "$2,000",
        "amount": "",
        "premium": "$429"
      },
      "Sewer Backup": {
        "name": "Sewer Backup",
        "deductible": "$2,000",
        "amount": "$50,000",
        "premium": "$429"
      },
      "Overland Water": {
        "name": "Overland Water",
        "deductible": "$2,000",
        "amount": "",
        "premium": "Inc."
      }
    }
  ],
  "application_info": {
    "address": {
      "address": "6 Blueberry Dr.",
      "city": "Scarborough",
      "province": "ON",
      "postal_code": "M1S3E9"
    },
    "phone": {
      "type": "Home",
      "number": "647-290-2372"
    },
    "effective_date": "2026-03-09",
    "membership": {
      "caa_membership": "Yes",
      "caa_membership_number": "6202822425653003"
    },
    "prev_insurance": {
      "company": "AVIVA COMPANY OF CANADA",
      "policy_number": "P97270368HAB",
      "end_date": {
        "year": "2026",
        "month": "03",
        "day": "09"
      }
    }
  }
}
```

"""
        return requirements
    
    def _get_default_fields_structure(self) -> str:
        """Get default fields structure (fallback)"""
        return """
1. **applicant_information** (required):
   - first_name: string
   - last_name: string
   - email: string (optional)
   - phone: string (optional)
   - date_of_birth: string (format: YYYY-MM-DD)
   - salutation: string (optional, e.g., "Mr", "Mrs", "Ms")
   - marital_status: string (optional)

2. **address** (required):
   - street: string
   - city: string
   - province: string (use standard abbreviations like ON, BC, AB, etc.)
   - postal_code: string

3. **application_info** (required):
   - effective_date: string (format: YYYY-MM-DD)
   - previous_insurance: object (optional)
     - carrier: string
     - policy_number: string
     - expiration_date: string (format: YYYY-MM-DD)
     - years_insured: integer

4. **drivers_information** (required):
   - Object with keys like "driver_1", "driver_2", etc.
   - Each driver object should contain:
     - first_name: string
     - last_name: string
     - date_of_birth: string (format: YYYY-MM-DD)
     - license_number: string
     - license_class: string (optional)
     - license_issue_date: string (format: YYYY-MM-DD, optional)
     - license_expiry_date: string (format: YYYY-MM-DD, optional)
     - claims: array of objects
       - date: string (format: YYYY-MM-DD)
       - description: string
       - amount: number (optional)
       - at_fault: boolean (optional)
     - convictions: array of objects
       - date: string (format: YYYY-MM-DD)
       - description: string
       - km/h: string (optional, for speeding violations)

5. **vehicles_information** (required):
   - Object with keys like "vehicle_1", "vehicle_2", etc.
   - Each vehicle object should contain:
     - year: integer
     - make: string
     - model: string
     - vin: string
     - model_name: string (e.g., "2020 Toyota Camry")
     - primary_use: string (optional)
     - annual_mileage: integer (optional)

6. **coverages_information** (optional):
   - Object with vehicle keys (e.g., "vehicle_1")
   - Each vehicle key contains coverage objects:
     - Coverage name as key (e.g., "Collision", "Comprehensive")
     - Each coverage object contains:
       - coverage_amount: number

7. **policy_information** (optional):
   - payment_plan: string
   - deductible: number"""
    
    def _build_prompt(self, documents: Dict[str, str]) -> str:
        """Build detailed prompt"""
        prompt = prompt_common.build_prompt_intro(self.company)
        # Add document content.
        # Per user requirement: always include full text for every input file.
        # Do not truncate any document content.
        for doc_name, content in documents.items():
            content_preview = content
            prompt += f"\n### {doc_name} Document:\n{content_preview}\n"
        
        prompt += "\n## Output Requirements:\n\n"
        prompt += "Generate a JSON object with the following structure:\n\n"

        if self._is_intact_auto_company():
            prompt += self._build_intact_auto_json_format_requirements()
        
        # Add critical format requirements for property type
        if self.company.endswith("_property"):
            prompt += self._build_property_format_requirements()
        
        # Build fields section from configuration
        fields_section = self._build_fields_prompt_section(self.fields_config)
        prompt += fields_section
        
        date_rule, caa_claim_policy_rule, caa_membership_rule = prompt_caa_memo.build_rules(self.company)
        prompt += prompt_caa_memo.build_critical_extraction_block(
            date_rule=date_rule,
            caa_claim_policy_rule=caa_claim_policy_rule,
            caa_membership_rule=caa_membership_rule,
        )
        
        return prompt
    
    def generate_json(
        self,
        autoplus_path: Optional[str] = None,
        autoplus_paths: Optional[list] = None,
        quote_path: Optional[str] = None,
        mvr_path: Optional[str] = None,
        mvr_paths: Optional[list] = None,
        application_form_path: Optional[str] = None,
        company: Optional[str] = None
    ) -> Dict:
        """
        Generate JSON from documents
        
        Args:
            autoplus_path: Autoplus document path (for backward compatibility)
            autoplus_paths: List of Autoplus document paths (takes precedence over autoplus_path)
            quote_path: Quote document path
            mvr_path: MVR document path (for backward compatibility)
            mvr_paths: List of MVR document paths (takes precedence over mvr_path)
            application_form_path: Application Form path
            company: Company name (overrides instance company if provided)
            
        Returns:
            Generated JSON dictionary
        """
        # Update company if provided
        self._set_company(company)
        # 1. Read all documents
        print("\n[Step 1] Reading documents...")
        documents = extract_text_from_documents(
            autoplus_path, autoplus_paths, quote_path, mvr_path, mvr_paths, application_form_path
        )
        print(f"[Step 1] Successfully read {len(documents)} document(s)")
        return self.generate_json_from_documents(documents, company=self.company)

    def generate_json_from_documents(
        self,
        documents: Dict[str, str],
        company: Optional[str] = None
    ) -> Dict:
        """Generate JSON from document texts."""
        self._set_company(company)

        print("\n[Step 2] Building prompt...")
        prompt = self._build_prompt(documents)

        try:
            print("\n[Step 3] Calling model...")
            print(f"Mode: {self.mode} | Company: {self.company} | Model: {self.model}")

            if self.mode == "gateway":
                result_json = self._call_gateway(documents)
            else:
                result_text = self._call_anthropic(prompt)
                result_json = self._parse_response_json(result_text)

            # Extract and display extraction reasoning if present
            reasoning = result_json.pop("_extraction_reasoning", None)
            if reasoning:
                print("\n[DEBUG] Extraction Reasoning:")
                print("=" * 60)
                if isinstance(reasoning, dict):
                    for field, explanation in reasoning.items():
                        if explanation:
                            print(f"\n{field}:")
                            print(f"  {explanation}")
                else:
                    print(reasoning)
                print("=" * 60)
                print()

            print("[Step 4] JSON generated successfully!")
            return self._validate_and_clean_json(result_json, documents)
        except Exception as e:
            print(f"[ERROR] Failed to generate JSON: {e}")
            raise

    def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic API with streaming and return full text response."""
        if not self.client:
            raise RuntimeError("Anthropic client is not initialized")
        print("[Step 3] Streaming model response...")
        chunks = []
        stop_reason = None
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            ) as stream:
                for text in stream.text_stream:
                    chunks.append(text)
                final_message = stream.get_final_message()
                stop_reason = getattr(final_message, "stop_reason", None)
        except Exception as e:
            message = str(e)
            if "longer than 10 minutes" in message.lower():
                raise RuntimeError(
                    "请求预计耗时超过 10 分钟，请使用 streaming（当前已启用）或降低 max_tokens / 精简输入文档。"
                ) from e
            raise RuntimeError(f"调用模型失败：{message}") from e

        result_text = "".join(chunks)
        print(
            f"[Step 3] Streaming completed. stop_reason={stop_reason}, "
            f"response_chars={len(result_text)}"
        )
        if stop_reason == "max_tokens":
            raise RuntimeError(
                "模型因达到 max_tokens 被截断，返回内容可能不是完整 JSON。"
                "请提高 config 中的 max_tokens，或精简提示/字段说明。"
            )
        if not result_text.strip():
            raise RuntimeError("模型返回为空，请检查输入文档内容或稍后重试。")
        return result_text

    def _call_gateway(self, documents: Dict[str, str]) -> Dict:
        """Call internal gateway service and return JSON object."""
        url = f"{self.gateway_url.rstrip('/')}/v1/generate-json"
        headers = {"Content-Type": "application/json"}
        if self.gateway_token:
            headers["X-Internal-Token"] = self.gateway_token

        payload = {
            "company": self.company,
            "documents": documents,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout_sec)
        if resp.status_code != 200:
            raise RuntimeError(f"Gateway request failed ({resp.status_code}): {resp.text}")

        body = resp.json()
        if not body.get("ok"):
            raise RuntimeError(body.get("error", "Gateway returned failure"))
        if "data" not in body:
            raise RuntimeError("Gateway response missing data field")
        return body["data"]

    @staticmethod
    def _parse_response_json(result_text: str) -> Dict:
        """Parse model text response into JSON object."""
        return json_generator_pure.parse_response_json(result_text)
    
    def _validate_and_clean_json(self, data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
        """Validate and clean generated JSON"""
        # Ensure required fields exist
        legacy_required_fields = [
            "applicant_information",
            "address",
            "application_info",
            "drivers_information",
            "vehicles_information"
        ]
        if getattr(self, "use_company_schema_validation", False):
            required_fields = get_required_top_level_fields(
                self.company,
                self.fields_config,
                legacy_required_fields,
            )
        else:
            required_fields = legacy_required_fields
        
        for field in required_fields:
            if field not in data:
                print(f"[WARNING] Missing required field: {field}, adding empty object")
                data[field] = {}
        
        # Ensure nested structure is correct
        if "drivers_information" in data and not isinstance(data["drivers_information"], dict):
            data["drivers_information"] = {}
        
        if "vehicles_information" in data and not isinstance(data["vehicles_information"], dict):
            data["vehicles_information"] = {}
        
        if "coverages_information" in data and not isinstance(data["coverages_information"], dict):
            data["coverages_information"] = {}

        data = company_postprocess_pipeline.run(self, data, documents)
        
        return data

    @staticmethod
    def _format_to_mmddyyyy(date_value):
        """Convert common date formats to MM/DD/YYYY; return original if conversion fails."""
        return json_generator_pure.format_to_mmddyyyy(date_value)

    def _should_apply_caa_dob_normalization(self, data: Dict) -> bool:
        """Apply CAA DOB normalization only for explicit CAA mode."""
        return self._is_caa_company()

    @staticmethod
    def _format_to_yyyymmdd(date_value):
        """Convert common date formats to YYYY-MM-DD; return original if conversion fails."""
        return json_generator_pure.format_to_yyyymmdd(date_value)

    @staticmethod
    def _format_to_ddmmyyyy(date_value):
        """Convert common date formats to DD-MM-YYYY; return original if conversion fails."""
        return json_generator_pure.format_to_ddmmyyyy(date_value)

    @staticmethod
    def _format_to_yyyymm(date_value):
        """Convert common date formats to YYYY-MM; return original if conversion fails."""
        return json_generator_pure.format_to_yyyymm(date_value)

    @staticmethod
    def _get_configured_date_format(field_info: Dict, field_name: Optional[str] = None) -> str:
        """Infer target date format from field config metadata (per-field; no silent wrong default for CAA effective_date)."""
        if not isinstance(field_info, dict):
            return "YYYY-MM-DD"
        desc = field_info.get("description", "") or ""
        logic = field_info.get("extraction_logic", "") or ""
        hints = f"{desc} {logic}".upper()

        if field_name == "effective_date":
            return "YYYY-MM-DD"
        if "ONLY DATE FIELD THAT USES YYYY-MM-DD" in logic.upper():
            return "YYYY-MM-DD"
        if "ONLY FIELD USING THIS FORMAT" in hints and "YYYY-MM-DD" in desc.upper():
            return "YYYY-MM-DD"

        if "YYYY-MM FORMAT" in hints or "FORMAT: YYYY-MM" in hints:
            return "YYYY-MM"
        if "DD-MM-YYYY" in hints:
            return "DD-MM-YYYY"
        if "MM/DD/YYYY" in hints:
            return "MM/DD/YYYY"
        return "YYYY-MM-DD"

    def _collect_date_field_formats(self) -> Dict[str, str]:
        """Collect target date format per field configured as mode=date."""
        field_formats = {}

        def walk(node):
            if not isinstance(node, dict):
                return
            fields = node.get("fields")
            if isinstance(fields, dict):
                for field_name, field_info in fields.items():
                    if isinstance(field_info, dict):
                        if field_info.get("mode") == "date":
                            field_formats[field_name] = self._get_configured_date_format(field_info, field_name)
                        walk(field_info)

        walk(self.fields_config)
        return field_formats

    def _normalize_date_scalar(self, value: str, fmt: str) -> str:
        if not isinstance(value, str):
            return value
        if fmt == "MM/DD/YYYY":
            return self._format_to_mmddyyyy(value)
        if fmt == "YYYY-MM":
            return self._format_to_yyyymm(value)
        if fmt == "DD-MM-YYYY":
            return self._format_to_ddmmyyyy(value)
        return self._format_to_yyyymmdd(value)

    def _normalize_dates_in_object_by_template(self, field_map: Dict, obj: Dict) -> int:
        """
        Normalize date strings in obj using the schema field_map (handles dynamic-key sections
        like coverages when the template uses a single ALL_CAPS placeholder key).
        """
        changed = 0
        if not isinstance(field_map, dict) or not isinstance(obj, dict):
            return 0

        direct_keys = [k for k in field_map if k in obj]
        if not direct_keys and len(field_map) == 1:
            sole_key, sole_info = next(iter(field_map.items()))
            if (
                isinstance(sole_key, str)
                and sole_key.isupper()
                and isinstance(sole_info, dict)
                and sole_info.get("fields")
            ):
                inner_template = sole_info["fields"]
                for sub_val in obj.values():
                    if isinstance(sub_val, dict):
                        changed += self._normalize_dates_in_object_by_template(inner_template, sub_val)
                return changed

        for fname, finfo in field_map.items():
            if fname not in obj:
                continue
            val = obj[fname]
            if not isinstance(finfo, dict):
                continue
            if finfo.get("mode") == "date" and isinstance(val, str):
                fmt = self._get_configured_date_format(finfo, fname)
                normalized = self._normalize_date_scalar(val, fmt)
                if normalized != val:
                    obj[fname] = normalized
                    changed += 1
            elif (
                (finfo.get("type") == "array" or finfo.get("always_array"))
                and isinstance(val, list)
                and finfo.get("item_fields")
            ):
                itf = finfo["item_fields"]
                for item in val:
                    if isinstance(item, dict):
                        changed += self._normalize_dates_in_object_by_template(itf, item)
            elif finfo.get("fields") and isinstance(val, dict):
                if finfo.get("type") == "object" and finfo.get("key_format"):
                    for ent in val.values():
                        if isinstance(ent, dict):
                            changed += self._normalize_dates_in_object_by_template(finfo["fields"], ent)
                else:
                    changed += self._normalize_dates_in_object_by_template(finfo["fields"], val)
        return changed

    def _normalize_dates_by_fields_config(self, data: Dict) -> Tuple[Dict, int]:
        """Force date strings to each field's configured format (CAA Auto / any loaded fields_config)."""
        if not self._is_caa_auto_company():
            return data, 0
        root = self.fields_config.get("fields")
        if not isinstance(root, dict) or not isinstance(data, dict):
            return data, 0
        changed = 0
        for _section_name, section_cfg in root.items():
            if not isinstance(section_cfg, dict):
                continue
            field_map = section_cfg.get("fields")
            if not isinstance(field_map, dict):
                continue
            payload = data.get(_section_name)
            if payload is None:
                continue
            if section_cfg.get("type") == "object" and section_cfg.get("key_format"):
                if isinstance(payload, dict):
                    for entity in payload.values():
                        if isinstance(entity, dict):
                            changed += self._normalize_dates_in_object_by_template(field_map, entity)
            elif isinstance(payload, dict):
                changed += self._normalize_dates_in_object_by_template(field_map, payload)
        return data, changed

    def _normalize_intact_dates(self, data: Dict):
        """Normalize Intact date fields based on configured per-field target formats."""
        if not isinstance(data, dict):
            return data, 0

        field_formats = self._collect_date_field_formats()
        if not field_formats:
            return data, 0

        changed_count = 0

        def walk(node):
            nonlocal changed_count
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in field_formats:
                        target = field_formats[key]
                        if isinstance(value, str):
                            if target == "DD-MM-YYYY":
                                normalized = self._format_to_ddmmyyyy(value)
                            elif target == "YYYY-MM":
                                normalized = self._format_to_yyyymm(value)
                            elif target == "MM/DD/YYYY":
                                normalized = self._format_to_mmddyyyy(value)
                            else:
                                normalized = self._format_to_yyyymmdd(value)
                            if normalized != value:
                                node[key] = normalized
                                changed_count += 1
                        elif isinstance(value, list):
                            updated = []
                            list_changed = False
                            for item in value:
                                if not isinstance(item, str):
                                    updated.append(item)
                                    continue
                                if target == "DD-MM-YYYY":
                                    normalized = self._format_to_ddmmyyyy(item)
                                elif target == "YYYY-MM":
                                    normalized = self._format_to_yyyymm(item)
                                elif target == "MM/DD/YYYY":
                                    normalized = self._format_to_mmddyyyy(item)
                                else:
                                    normalized = self._format_to_yyyymmdd(item)
                                updated.append(normalized)
                                if normalized != item:
                                    list_changed = True
                                    changed_count += 1
                            if list_changed:
                                node[key] = updated
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
        return data, changed_count

    @staticmethod
    def _remove_non_intact_membership_fields(data: Dict) -> Dict:
        """Remove CAA membership fields accidentally generated for Intact."""
        if not isinstance(data, dict):
            return data
        app_info = data.get("application_info")
        if isinstance(app_info, dict):
            app_info.pop("caa_membership", None)
            app_info.pop("caa_membership_number", None)
        elif app_info is None:
            data["application_info"] = {}
        return data

    @staticmethod
    def _normalize_intact_structure(data: Dict) -> Dict:
        """Apply Intact-specific structural cleanup rules."""
        if not isinstance(data, dict):
            return data

        if "application_info" not in data or not isinstance(data.get("application_info"), dict):
            data["application_info"] = {}

        interest = data.get("interest")
        if isinstance(interest, dict) and interest.get("has_loan") == "No":
            data["interest"] = {"has_loan": "No"}

        claim = data.get("claim")
        if isinstance(claim, dict) and claim.get("has_claim") == "No":
            data["claim"] = {"has_claim": "No"}

        drivers = data.get("driver")
        if isinstance(drivers, list):
            for driver in drivers:
                if not isinstance(driver, dict):
                    continue

                if driver.get("lapse_in_insurance") != "Yes":
                    driver.pop("lapse_in_insurance_description", None)
                    driver.pop("lapse_start", None)
                    driver.pop("lapse_end", None)

                licence_class = driver.get("licence_class")
                if licence_class == "G1":
                    driver.pop("g2_class_date_licensed", None)
                    driver.pop("g_class_date_licensed", None)
                elif licence_class == "G2":
                    driver.pop("g_class_date_licensed", None)
                elif licence_class == "G":
                    pass
                else:
                    driver.pop("g1_class_date_licensed", None)
                    driver.pop("g2_class_date_licensed", None)
                    driver.pop("g_class_date_licensed", None)

        return data

    def _normalize_caa_birth_dates(self, data: Dict):
        """Normalize CAA birth date fields to MM/DD/YYYY."""
        if not isinstance(data, dict):
            return data, 0

        changed_count = 0

        applicant = data.get("applicant_information")
        if isinstance(applicant, dict) and "date_of_birth" in applicant:
            original = applicant.get("date_of_birth")
            normalized = self._format_to_mmddyyyy(original)
            applicant["date_of_birth"] = normalized
            if normalized != original:
                changed_count += 1

        drivers = data.get("drivers_information")
        if isinstance(drivers, dict):
            for _, driver in drivers.items():
                if isinstance(driver, dict) and "date_of_birth" in driver:
                    original = driver.get("date_of_birth")
                    normalized = self._format_to_mmddyyyy(original)
                    driver["date_of_birth"] = normalized
                    if normalized != original:
                        changed_count += 1

        return data, changed_count

    @staticmethod
    def _is_missing(value) -> bool:
        return json_generator_pure.is_missing(value)

    @staticmethod
    def _extract_digits_as_int(value):
        return json_generator_pure.extract_digits_as_int(value)

    @staticmethod
    def _is_non_price_text(value) -> bool:
        """Check if value is clearly non-price text (like parking locations, Yes/No, etc.)"""
        return json_generator_pure.is_non_price_text(value)

    def _apply_caa_vehicle_purchase_sanity(self, data: Dict):
        """
        Validate and fix obvious errors in purchase-related fields:
        1. Clear non-price text from price fields (e.g., "Private Driveway" in purchase_price)
        2. Ensure empty fields are null
        3. If km_at_purchase and list_price_new normalize to the same positive number, treat as
           purchase-table column misalignment (blank km cell + list price duplicated into km) and
           clear km_at_purchase to null.
        """
        if not isinstance(data, dict):
            return data, 0

        vehicles = data.get("vehicles_information")
        if not isinstance(vehicles, dict):
            return data, 0

        corrected = 0
        for vehicle_key, vehicle in vehicles.items():
            if not isinstance(vehicle, dict):
                continue

            condition = vehicle.get("purchase_condition")
            km_value = vehicle.get("km_at_purchase")
            list_price = vehicle.get("list_price_new")
            purchase_price = vehicle.get("purchase_price")

            # Validate purchase_price: clear non-price text
            if purchase_price is not None:
                if self._is_non_price_text(purchase_price):
                    print(f"[WARNING] Invalid purchase_price value '{purchase_price}' for vehicle '{vehicle_key}'. Setting to null.")
                    vehicle["purchase_price"] = None
                    corrected += 1
                elif isinstance(purchase_price, str) and not purchase_price.strip():
                    vehicle["purchase_price"] = None
                    corrected += 1

            # Validate list_price_new: clear non-price text
            if list_price is not None:
                if self._is_non_price_text(list_price):
                    print(f"[WARNING] Invalid list_price_new value '{list_price}' for vehicle '{vehicle_key}'. Setting to null.")
                    vehicle["list_price_new"] = None
                    corrected += 1
                elif isinstance(list_price, str) and not list_price.strip():
                    vehicle["list_price_new"] = None
                    corrected += 1

            # Ensure empty km_at_purchase is null
            if km_value is not None and isinstance(km_value, str) and not km_value.strip():
                vehicle["km_at_purchase"] = None
                corrected += 1

            km_value = vehicle.get("km_at_purchase")
            list_price = vehicle.get("list_price_new")
            km_digits = (
                self._extract_digits_as_int(str(km_value).strip())
                if km_value is not None and not self._is_missing(km_value)
                else None
            )
            lp_digits = (
                self._extract_digits_as_int(str(list_price).strip())
                if list_price is not None and not self._is_missing(list_price)
                else None
            )
            if km_digits is not None and lp_digits is not None and km_digits == lp_digits:
                print(
                    f"[INFO] Vehicle '{vehicle_key}': km_at_purchase and list_price_new both "
                    f"'{km_digits}' — likely shifted columns; clearing km_at_purchase."
                )
                vehicle["km_at_purchase"] = None
                corrected += 1

            # Swap logic: if list_price_new is null, purchase_price is null (after validation), and km_at_purchase has a value, swap them
            km_value = vehicle.get("km_at_purchase")
            list_price = vehicle.get("list_price_new")
            purchase_price_after_validation = vehicle.get("purchase_price")
            
            if list_price is None or (isinstance(list_price, str) and not list_price.strip()):
                # list_price_new is null or empty
                if purchase_price_after_validation is None or (isinstance(purchase_price_after_validation, str) and not purchase_price_after_validation.strip()):
                    # purchase_price is also null or empty after validation
                    if km_value is not None and isinstance(km_value, str) and km_value.strip():
                        # km_at_purchase has a value, swap them
                        print(f"[INFO] Swapping fields for vehicle '{vehicle_key}': km_at_purchase='{km_value}' -> list_price_new, list_price_new=null -> km_at_purchase")
                        vehicle["list_price_new"] = km_value
                        vehicle["km_at_purchase"] = None
                        corrected += 1

        return data, corrected
    
    def _fix_vehicle_table_column_misalignment(self, data: Dict):
        """
        Fix column misalignment issues in vehicle information table.
        Common issue: when daily_km is blank, but a value from cylinders column is incorrectly extracted as daily_km.

        Detection logic (conservative):
        - If daily_km is a single digit and equals cylinders, clear daily_km (likely read from wrong column).
        - Do NOT clear single-digit daily_km otherwise: values like 8 km/day are valid and common when
          primary_use is Pleasure and business_km is empty.
        """
        if not isinstance(data, dict):
            return data, 0
        
        vehicles = data.get("vehicles_information")
        if not isinstance(vehicles, dict):
            return data, 0
        
        corrected = 0
        for vehicle_key, vehicle in vehicles.items():
            if not isinstance(vehicle, dict):
                continue
            
            daily_km = vehicle.get("daily_km")
            cylinders = vehicle.get("cylinders")
            business_km = vehicle.get("business_km")
            
            # Check if daily_km looks suspicious (single digit that matches cylinders)
            if daily_km is not None and isinstance(daily_km, str):
                daily_km_clean = daily_km.strip()
                
                # If daily_km is a single digit (1-9) and matches cylinders, it's likely misaligned
                if len(daily_km_clean) == 1 and daily_km_clean.isdigit():
                    if cylinders is not None and str(cylinders).strip() == daily_km_clean:
                        print(f"[WARNING] Vehicle '{vehicle_key}': daily_km='{daily_km}' matches cylinders='{cylinders}'. "
                              f"This suggests column misalignment. Clearing daily_km.")
                        vehicle["daily_km"] = None
                        corrected += 1
            
            # Similar check for business_km (though less common)
            if business_km is not None and isinstance(business_km, str):
                business_km_clean = business_km.strip()
                # If business_km is a single digit and matches cylinders, it's likely misaligned
                if len(business_km_clean) == 1 and business_km_clean.isdigit():
                    if cylinders is not None and str(cylinders).strip() == business_km_clean:
                        print(f"[WARNING] Vehicle '{vehicle_key}': business_km='{business_km}' matches cylinders='{cylinders}'. "
                              f"This suggests column misalignment. Clearing business_km.")
                        vehicle["business_km"] = None
                        corrected += 1
        
        return data, corrected

    def _apply_caa_output_normalization(self, data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
        """
        Apply CAA Auto Submission JSON post-processing rules on top of model output.

        Key goals:
        - vehicles_information: validate purchase_price (clear invalid values to null, allow null for empty fields); drivers strings use '(PRN)'.
        - drivers_information: claims/convictions/suspensions/lapses/vehicles are arrays;
          claims objects have required fields (policy, codes, tp_bi, tp_pd, ab, coll, other_pd).
        - discounts_information: driver_covered uses 'PRN' instead of 'Prn'.
        - application_info: avoid obvious nulls for CAA-specific fields (like caa_membership).
        """
        if not isinstance(data, dict):
            return data

        vehicle_keys = []
        vehicles = data.get("vehicles_information")
        if isinstance(vehicles, dict):
            vehicle_keys = list(vehicles.keys())
            for _, vehicle in vehicles.items():
                if not isinstance(vehicle, dict):
                    continue

                # annual_km / daily_km: avoid null, prefer empty string
                for km_field in ("annual_km", "daily_km"):
                    if km_field in vehicle and vehicle[km_field] is None:
                        vehicle[km_field] = ""
                
                # km_at_purchase is required for CAA auto output:
                # if missing/blank/null, force default to numeric 0 instead of null.
                km_at_purchase = vehicle.get("km_at_purchase")
                if self._is_missing(km_at_purchase):
                    vehicle["km_at_purchase"] = 0

                # purchase_price: validate existing value, but allow null for empty/invalid fields
                # If the field was cleared due to invalid value (e.g., "Private Driveway"), keep it as null
                purchase_price = vehicle.get("purchase_price")
                if purchase_price is not None and self._is_non_price_text(purchase_price):
                    # This should have been caught by _apply_caa_vehicle_purchase_sanity, but double-check
                    print(f"[WARNING] Invalid purchase_price value '{purchase_price}' detected in normalization. Setting to null.")
                    vehicle["purchase_price"] = None
                # Note: If purchase_price is null (empty field or invalid value cleared), keep it as null - do not auto-fill

                # drivers: normalize relationship code to '(PRN)' in uppercase
                drivers_list = vehicle.get("drivers")
                if isinstance(drivers_list, list):
                    normalized_drivers = []
                    for drv in drivers_list:
                        if isinstance(drv, str):
                            # Replace any '(Prn)' / '(prn)' / '(PRn)' etc. with '(PRN)'
                            normalized = re.sub(r"\(\s*prn\s*\)", "(PRN)", drv, flags=re.IGNORECASE)
                            normalized_drivers.append(normalized)
                        else:
                            normalized_drivers.append(drv)
                    vehicle["drivers"] = normalized_drivers

        # discounts_information: normalize driver_covered => 'PRN'
        discounts = data.get("discounts_information")
        if isinstance(discounts, dict):
            for _, veh_discounts in discounts.items():
                if not isinstance(veh_discounts, dict):
                    continue
                for _, discount in veh_discounts.items():
                    if not isinstance(discount, dict):
                        continue
                    dc = discount.get("driver_covered")
                    if isinstance(dc, str) and dc.lower() == "prn":
                        discount["driver_covered"] = "PRN"

        # drivers_information normalization (claims structure, arrays, etc.)
        # fallback claim policy candidates from other sections (best effort)
        fallback_claim_policy = self._extract_global_claim_policy_fallback(data)

        drivers_info = data.get("drivers_information")
        if isinstance(drivers_info, dict):
            missing_policy_claims = []
            for _, driver in drivers_info.items():
                if not isinstance(driver, dict):
                    continue

                # Ensure core array fields exist and are arrays
                for field in ("claims", "convictions", "suspensions", "lapses", "vehicles"):
                    value = driver.get(field)
                    if value is None:
                        driver[field] = []
                    elif not isinstance(value, list):
                        driver[field] = [value]

                # Normalize claims to object structure
                raw_claims = driver.get("claims") or []
                normalized_claims = []
                for claim in raw_claims:
                    if isinstance(claim, str):
                        normalized_claims.append(
                            self._parse_caa_claim_string(claim, vehicle_keys, fallback_claim_policy)
                        )
                    elif isinstance(claim, dict):
                        normalized_claims.append(
                            self._normalize_caa_claim_object(claim, vehicle_keys, fallback_claim_policy)
                        )
                driver["claims"] = normalized_claims

                # Strict validation: policy is required for each non-empty claim
                for idx, claim in enumerate(driver["claims"]):
                    if not isinstance(claim, dict):
                        continue
                    policy = claim.get("policy")
                    if self._is_missing(policy):
                        driver_name = f"{driver.get('first_name', '')} {driver.get('last_name', '')}".strip()
                        if not driver_name:
                            driver_name = "UNKNOWN_DRIVER"
                        missing_policy_claims.append(f"{driver_name} claim[{idx}]")

            if missing_policy_claims:
                joined = ", ".join(missing_policy_claims)
                raise ValueError(
                    f"CAA claims require non-empty policy (Claim# / Policy#). Missing in: {joined}"
                )

        # application_info specific tweaks
        app_info = data.get("application_info")
        if isinstance(app_info, dict):
            # caa_membership: default to "No" instead of null
            if app_info.get("caa_membership") is None:
                app_info["caa_membership"] = "No"
            
            # Normalize CAA membership number: remove spaces if present
            if app_info.get("caa_membership") == "Yes":
                membership_number = app_info.get("caa_membership_number")
                if membership_number and isinstance(membership_number, str) and membership_number.strip():
                    # Remove all spaces for consistency
                    normalized_number = re.sub(r'\s+', '', membership_number)
                    if normalized_number != membership_number:
                        app_info["caa_membership_number"] = normalized_number
                        print(f"[INFO] Normalized CAA membership number (removed spaces): {normalized_number}")
            
            # avoid obvious nulls for strings we know are simple scalars
            for key in ("address", "phone", "caa_membership_number", "lessor"):
                if key in app_info and app_info[key] is None:
                    app_info[key] = ""
        
        # Clean coverage_amount fields in coverages_information (Auto format: object with vehicle keys)
        coverages_info = data.get("coverages_information")
        if isinstance(coverages_info, dict):
            for vehicle_key, vehicle_coverages in coverages_info.items():
                if isinstance(vehicle_coverages, dict):
                    for coverage_type, coverage_data in vehicle_coverages.items():
                        if isinstance(coverage_data, dict):
                            # Clean coverage_amount field
                            if "coverage_amount" in coverage_data:
                                coverage_data["coverage_amount"] = self._clean_coverage_amount(coverage_data["coverage_amount"])

        return data
    
    def _check_caa_membership_pattern_in_documents(self, documents: Dict[str, str]) -> bool:
        """
        Check if "Group discount apply: yes - CAA" pattern exists in documents.
        Returns True if pattern is found, False otherwise.
        """
        # Combine all document texts
        all_text = " ".join(documents.values())
        
        # Check for the pattern (case-insensitive, flexible whitespace)
        pattern = r"Group\s+discount\s+apply:\s+yes\s+-\s+CAA"
        match = re.search(pattern, all_text, re.IGNORECASE)
        return match is not None
    
    def _extract_caa_membership_number_from_documents(self, documents: Dict[str, str]) -> Optional[str]:
        """
        Extract CAA membership number from documents using regex patterns.
        Looks for patterns like "Group discount apply: yes - CAA | Member #: [NUMBER]"
        """
        # Combine all document texts
        all_text = " ".join(documents.values())
        
        # Pattern 1: "Group discount apply: yes - CAA | Member #: [NUMBER]"
        pattern1 = r"Group\s+discount\s+apply:\s+yes\s+-\s+CAA\s*\|\s*Member\s*#:\s*([0-9\s]+)"
        match1 = re.search(pattern1, all_text, re.IGNORECASE)
        if match1:
            number = match1.group(1).strip()
            # Remove spaces for consistency
            number = re.sub(r'\s+', '', number)
            return number if number else None
        
        # Pattern 2: "Member #: [NUMBER]" near "CAA" or "Group discount"
        pattern2 = r"(?:Group\s+discount|CAA).*?Member\s*#:\s*([0-9\s]+)"
        match2 = re.search(pattern2, all_text, re.IGNORECASE)
        if match2:
            number = match2.group(1).strip()
            number = re.sub(r'\s+', '', number)
            return number if number else None
        
        # Pattern 3: "CAA Member #: [NUMBER]"
        pattern3 = r"CAA\s+Member\s*#:\s*([0-9\s]+)"
        match3 = re.search(pattern3, all_text, re.IGNORECASE)
        if match3:
            number = match3.group(1).strip()
            number = re.sub(r'\s+', '', number)
            return number if number else None
        
        return None

    def _parse_caa_claim_string(self, claim_str: str, vehicle_keys, fallback_claim_policy: str = "") -> Dict:
        """
        Convert a CAA claim string like:
        "Non-resp Direct Compensation 08/24/2001 No 2019 NISSAN KICKS S 4DR 2WD TP/BI$: 5000"
        into a normalized claim object with required fields.
        """
        if not isinstance(claim_str, str):
            claim_str = str(claim_str)

        text = claim_str.strip()

        # Defaults
        description = ""
        date = ""
        charge = ""
        vehicle_involved = ""

        # 1) Extract date (first MM/DD/YYYY)
        date_match = re.search(r"\b(\d{2}/\d{2}/\d{4})\b", text)
        if date_match:
            date = date_match.group(1)
            before_date = text[: date_match.start()].strip()
            after_date = text[date_match.end() :].strip()
        else:
            before_date = text
            after_date = ""

        # 2) Description: everything before date
        description = before_date

        # 3) Charge: first Yes/No after date
        charge_match = re.search(r"\b(Yes|No)\b", after_date, flags=re.IGNORECASE)
        if charge_match:
            charge = charge_match.group(1).capitalize()
            after_charge = after_date[charge_match.end() :].strip()
        else:
            after_charge = after_date

        # 4) Vehicle involved: best-effort match against known vehicle keys
        for vk in vehicle_keys or []:
            if vk and vk in text:
                vehicle_involved = vk
                break

        # 5) Amount parsing helpers
        def parse_amount(pattern: str) -> Optional[int]:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if not m:
                return None
            raw = m.group(1)
            digits = re.sub(r"[^\d]", "", raw)
            if not digits:
                return None
            try:
                return int(digits)
            except ValueError:
                return None

        tp_bi = parse_amount(r"TP/BI\\$[: ]*([0-9,\\.]+)")
        tp_pd = parse_amount(r"TP/PD\\$[: ]*([0-9,\\.]+)")
        ab = parse_amount(r"AB\\$[: ]*([0-9,\\.]+)")
        coll = parse_amount(r"COLL\\$[: ]*([0-9,\\.]+)")
        other_pd = parse_amount(r"OTHER[_ ]?PD\\$[: ]*([0-9,\\.]+)")

        # 6) Codes: glass vs collision
        desc_lower = text.lower()
        if "glass" in desc_lower:
            codes = ["26 - GLASS"]
        else:
            codes = ["20 - COLL"]

        policy = self._extract_claim_policy_from_text(text) or fallback_claim_policy

        claim_obj = {
            "description": description,
            "date": date,
            "charge": charge,
            "vehicle_involved": vehicle_involved,
            "policy": policy or "",
            "codes": codes,
            "tp_bi": tp_bi if tp_bi is not None else 0,
            "tp_pd": tp_pd if tp_pd is not None else 0,
            "ab": ab if ab is not None else 0,
            "coll": coll if coll is not None else 0,
            "other_pd": other_pd if other_pd is not None else 0,
        }
        return claim_obj

    def _normalize_caa_claim_object(self, claim: Dict, vehicle_keys, fallback_claim_policy: str = "") -> Dict:
        """
        Normalize a claim object that may use CAA field_config keys like
        'tp/bi', 'tp/pd$', 'ab$', 'coll$', 'other_pd$' into the required
        flattened structure.
        """
        if not isinstance(claim, dict):
            claim = {}

        def get_amount(*keys) -> Optional[int]:
            for key in keys:
                if key in claim:
                    raw = claim.get(key)
                    if raw is None:
                        continue
                    # Already numeric
                    if isinstance(raw, (int, float)):
                        return int(raw)
                    # String: strip non-digits
                    s = str(raw)
                    digits = re.sub(r"[^\d]", "", s)
                    if digits:
                        try:
                            return int(digits)
                        except ValueError:
                            continue
            return None

        desc = claim.get("description") or ""
        date = claim.get("date") or ""
        # Ensure MM/DD/YYYY if it's a recognizable date
        date = self._format_to_mmddyyyy(date)
        charge = claim.get("charge") or ""

        vehicle_involved = claim.get("vehicle_involved") or ""
        if not vehicle_involved:
            # attempt to infer from any vehicle key present in nested text fields
            combined = " ".join(str(v) for v in claim.values())
            for vk in vehicle_keys or []:
                if vk and vk in combined:
                    vehicle_involved = vk
                    break

        # Amounts
        tp_bi = get_amount("tp_bi", "tp/bi")
        tp_pd = get_amount("tp_pd", "tp/pd", "tp/pd$")
        ab = get_amount("ab", "ab$")
        coll = get_amount("coll", "coll$")
        other_pd = get_amount("other_pd", "other_pd$")

        # Codes
        codes = claim.get("codes")
        if not isinstance(codes, list) or not codes:
            if "glass" in str(desc).lower():
                codes = ["26 - GLASS"]
            else:
                codes = ["20 - COLL"]

        policy = self._extract_claim_policy_from_claim_obj(claim) or fallback_claim_policy or ""

        normalized = {
            "description": desc,
            "date": date,
            "charge": charge,
            "vehicle_involved": vehicle_involved,
            "policy": policy,
            "codes": codes,
            "tp_bi": tp_bi if tp_bi is not None else 0,
            "tp_pd": tp_pd if tp_pd is not None else 0,
            "ab": ab if ab is not None else 0,
            "coll": coll if coll is not None else 0,
            "other_pd": other_pd if other_pd is not None else 0,
        }
        return normalized

    @staticmethod
    def _extract_claim_policy_from_text(text: str) -> str:
        """Extract Claim# / Policy# candidate from free text."""
        if not isinstance(text, str):
            return ""

        patterns = [
            r"(?:claim#|claim no\.?|claim number)\s*[:#]?\s*([A-Za-z0-9\-_/]+)",
            r"(?:policy#|policy no\.?|policy number)\s*[:#]?\s*([A-Za-z0-9\-_/]+)",
            # AutoPlus commonly uses "Policy: 01884845" (without #).
            r"(?:policy)\s*[:#]\s*([A-Za-z0-9\-_/]+)",
            # Common OCR / extraction typos for "policy".
            r"(?:polciy|poilcy)\s*[:#]\s*([A-Za-z0-9\-_/]+)",
            r"(?:claim#/policy#)\s*[:#]?\s*([A-Za-z0-9\-_/]+)",
        ]
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                value = (m.group(1) or "").strip()
                if value:
                    return value
        return ""

    def _extract_claim_policy_from_claim_obj(self, claim: Dict) -> str:
        """Extract policy from structured claim object with multiple possible key names."""
        if not isinstance(claim, dict):
            return ""

        candidate_keys = [
            "policy",
            "policy_number",
            "policy_no",
            "claim_number",
            "claim_no",
            "claim#/policy#",
            "claim_policy",
        ]
        for key in candidate_keys:
            value = claim.get(key)
            if value is None:
                continue
            value_str = str(value).strip()
            if value_str:
                return value_str

        # Tolerant key matching for variants like:
        # "Policy", "Policy:", "Policy #", "polciy", "claim no", etc.
        normalized_lookup = {}
        for key, value in claim.items():
            if value is None:
                continue
            key_norm = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if key_norm:
                normalized_lookup[key_norm] = value

        normalized_candidate_keys = [
            "policy",
            "policynumber",
            "policyno",
            "policyid",
            "polciy",      # common typo
            "poilcy",      # common typo
            "claimnumber",
            "claimno",
            "claimpolicy",
        ]
        for key_norm in normalized_candidate_keys:
            if key_norm not in normalized_lookup:
                continue
            value_str = str(normalized_lookup[key_norm]).strip()
            if value_str:
                return value_str

        combined_text = " ".join(str(v) for v in claim.values() if v is not None)
        return self._extract_claim_policy_from_text(combined_text)

    def _extract_global_claim_policy_fallback(self, data: Dict) -> str:
        """Best-effort global fallback when a claim-level policy is missing."""
        if not isinstance(data, dict):
            return ""

        policy_info = data.get("policy_information")
        if isinstance(policy_info, dict):
            candidate = policy_info.get("property_policy_number")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()

        app_info = data.get("application_info")
        if isinstance(app_info, dict):
            previous = app_info.get("previous_insurance")
            if isinstance(previous, dict):
                candidate = previous.get("policy_number")
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()

        return ""
    
    def _normalize_property_names(self, data: Dict) -> Dict:
        """
        Normalize name fields in property JSON to ensure they have at least 2 words
        and last word (Last Name) has at least 2 characters.
        """
        if not isinstance(data, dict):
            return data
        
        # Normalize insured_information.name
        insured_info = data.get("insured_information")
        if isinstance(insured_info, dict):
            name = insured_info.get("name")
            if isinstance(name, str):
                original_name = name
                normalized_name = self._normalize_name_field(name)
                # Always update the name field to ensure it's cleaned (even if it looks correct)
                insured_info["name"] = normalized_name
                if normalized_name != original_name:
                    print(f"[INFO] Normalized insured_information.name: '{original_name}' -> '{normalized_name}'")
                
                # Always validate and print debug info
                self._validate_and_debug_name(normalized_name, "insured_information.name")
        
        # Normalize coinsured_information.name
        coinsured_info = data.get("coinsured_information")
        if isinstance(coinsured_info, dict):
            name = coinsured_info.get("name")
            if isinstance(name, str) and name.strip():
                original_name = name
                normalized_name = self._normalize_name_field(name)
                # Always update the name field to ensure it's cleaned (even if it looks correct)
                coinsured_info["name"] = normalized_name
                if normalized_name != original_name:
                    print(f"[INFO] Normalized coinsured_information.name: '{original_name}' -> '{normalized_name}'")
                
                # Always validate and print debug info
                self._validate_and_debug_name(normalized_name, "coinsured_information.name")
        
        return data
    
    @staticmethod
    def _normalize_name_field(name: str) -> str:
        return json_generator_pure.normalize_name_field(name)
    
    @staticmethod
    def _validate_and_debug_name(name: str, field_name: str):
        return json_generator_pure.validate_and_debug_name(name, field_name)
    
    @staticmethod
    def _clean_coverage_amount(value: str) -> str:
        return json_generator_pure.clean_coverage_amount(value)
    
    def _normalize_property_structure(self, data: Dict) -> Dict:
        """
        Normalize property JSON structure to ensure:
        - coverages_information is an array [] not an object {}
        - application_info has no duplicate fields (e.g., caa_membership)
        - coverage_amount fields are cleaned (no $, no text descriptions)
        """
        if not isinstance(data, dict):
            return data
        
        # Fix coverages_information: must be array, not object
        if "coverages_information" in data:
            coverages = data["coverages_information"]
            if isinstance(coverages, dict):
                # If it's an empty object, convert to empty array
                if len(coverages) == 0:
                    data["coverages_information"] = []
                    print("[INFO] Converted coverages_information from empty object {} to empty array []")
                else:
                    # If it has content, wrap it in an array
                    # This shouldn't happen if AI follows instructions, but handle it gracefully
                    print(f"[WARNING] coverages_information is an object with {len(coverages)} keys, converting to array format")
                    # Try to convert object to array format
                    # This is a fallback - ideally AI should generate array format directly
                    coverage_array = []
                    for key, value in coverages.items():
                        coverage_array.append({key: value})
                    data["coverages_information"] = coverage_array
                    print(f"[INFO] Converted coverages_information object to array with {len(coverage_array)} elements")
            elif not isinstance(coverages, list):
                # If it's neither dict nor list, set to empty array
                print(f"[WARNING] coverages_information is {type(coverages)}, converting to empty array []")
                data["coverages_information"] = []
            
            # Clean coverage_amount fields in coverages_information (Property format: array)
            if isinstance(data["coverages_information"], list):
                for coverage_item in data["coverages_information"]:
                    if isinstance(coverage_item, dict):
                        for coverage_class, coverages_dict in coverage_item.items():
                            if isinstance(coverages_dict, dict):
                                for coverage_name, coverage_data in coverages_dict.items():
                                    if isinstance(coverage_data, dict):
                                        # Clean amount field
                                        if "amount" in coverage_data:
                                            coverage_data["amount"] = self._clean_coverage_amount(coverage_data["amount"])
        
        # Remove duplicate caa_membership field in application_info
        application_info = data.get("application_info")
        if isinstance(application_info, dict):
            # Check if both membership.caa_membership and caa_membership exist
            membership = application_info.get("membership")
            has_membership_caa = isinstance(membership, dict) and "caa_membership" in membership
            has_direct_caa = "caa_membership" in application_info
            
            if has_membership_caa and has_direct_caa:
                # Remove the duplicate direct caa_membership field
                print(f"[INFO] Removing duplicate caa_membership field from application_info (keeping membership.caa_membership)")
                del application_info["caa_membership"]
        
        return data
    
    def save_json(self, data: Dict, output_path: str):
        """Save JSON to file"""
        final_output_path = self._get_unique_output_path(output_path)
        os.makedirs(os.path.dirname(final_output_path), exist_ok=True)
        with open(final_output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n[SUCCESS] JSON saved to: {final_output_path}")
        return final_output_path

    @staticmethod
    def _get_unique_output_path(output_path: str) -> str:
        """
        Return a non-conflicting path.
        If output_path exists, append '(1)', '(2)', ... before extension.
        """
        if not output_path or not os.path.exists(output_path):
            return output_path

        directory, filename = os.path.split(output_path)
        base_name, ext = os.path.splitext(filename)
        counter = 1
        while True:
            candidate = os.path.join(directory, f"{base_name}({counter}){ext}")
            if not os.path.exists(candidate):
                return candidate
            counter += 1

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Sanitize filename for Windows/macOS/Linux compatibility."""
        if not name:
            return "output"
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()
        # Avoid trailing spaces/dots on Windows
        safe_name = safe_name.rstrip(" .")
        return safe_name or "output"

    def get_applicant_filename(self, data: Dict, fallback: str = "output") -> str:
        """
        Build output filename from applicant name in generated JSON.

        Priority:
        1) applicant_information.full_name
        2) applicant_information.first_name + applicant_information.last_name
        3) fallback
        """
        applicant = data.get("applicant_information", {}) if isinstance(data, dict) else {}

        full_name = applicant.get("full_name")
        if isinstance(full_name, str) and full_name.strip():
            return self._sanitize_filename(full_name.strip())

        first_name = applicant.get("first_name")
        last_name = applicant.get("last_name")
        if isinstance(first_name, str) and isinstance(last_name, str):
            combined = f"{first_name.strip()} {last_name.strip()}".strip()
            if combined:
                return self._sanitize_filename(combined)

        return self._sanitize_filename(fallback)

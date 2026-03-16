"""
JSON Generator - Generate JSON from documents using Claude API
"""
import json
import os
import sys
import re
from datetime import datetime
from typing import Dict, Optional
from anthropic import Anthropic
import requests

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.document_reader import extract_text_from_documents

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
        
        # Map company names to config file names
        # Support both old names (CAA, Intact) and new names (CAA_Auto, Intact_Auto, CAA_property)
        company_lower = company.lower()
        
        # Try new naming convention first (e.g., caa_auto_fields_config.json, intact_auto_fields_config.json)
        # or property variants (e.g., caa_property_fields_config.json)
        if company_lower.endswith("_auto"):
            # CAA_Auto -> caa_auto_fields_config.json
            config_name = f"{company_lower}_fields_config.json"
        elif company_lower.endswith("_property"):
            # CAA_property -> caa_property_fields_config.json
            config_name = f"{company_lower}_fields_config.json"
        else:
            # For backward compatibility: CAA -> caa_auto_fields_config.json, Intact -> intact_auto_fields_config.json
            if company_lower == "caa":
                config_name = "caa_auto_fields_config.json"
            elif company_lower == "intact":
                config_name = "intact_auto_fields_config.json"
            else:
                # Other companies: use original naming
                config_name = f"{company_lower}_fields_config.json"
        
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
                        # Check if date format is specified in description or extraction_logic
                        date_format = "YYYY-MM-DD"  # default
                        if "DD-MM-YYYY" in field_description or "DD-MM-YYYY" in field_extraction_logic:
                            date_format = "DD-MM-YYYY"
                        elif "YYYY-MM" in field_description or "YYYY-MM" in field_extraction_logic:
                            date_format = "YYYY-MM"
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
        prompt = f"""You are a professional insurance data extraction expert. Your task is to extract information from the provided documents and generate JSON data that meets the requirements for uploading to the {self.company} insurance system.

## ⚠️ IMMEDIATE ACTION REQUIRED - READ THIS FIRST ⚠️

Before reading the documents below, you MUST know this:

**FOR CAA INSURANCE APPLICATIONS:**
- There is a section called "CSIO APPLICATION FOR AUTOMOBILE INSURANCE - OAF1 - MEMO TEXT DETAILS" 
- This section appears at the END of Application PDF documents
- In this section, look for a line that says: "Group discount apply: yes - CAA | Member #: [NUMBER]"
- If you find this line, you MUST:
  1. Set `caa_membership` to "Yes"
  2. Extract the number after "| Member #:" as `caa_membership_number`
  3. Remove all spaces from the membership number

**DO NOT SKIP THIS CHECK!** This information is critical and often appears in the last pages/sections of the Application PDF.

## Input Documents:
"""
        # Add document content (limit length to avoid too many tokens)
        for doc_name, content in documents.items():
            # For CAA, prioritize showing the end of Application PDF where MEMO TEXT DETAILS usually appears
            if self._is_caa_company() and "application" in doc_name.lower():
                # Show both beginning and end (where MEMO TEXT DETAILS is)
                content_length = len(content)
                if content_length > 16000:
                    # Show first 4000 and last 12000 characters
                    content_preview = content[:4000] + "\n\n[... middle section omitted ...]\n\n" + content[-12000:]
                    prompt += f"\n### {doc_name} Document (showing beginning and END sections where MEMO TEXT DETAILS appears):\n{content_preview}\n"
                elif content_length > 8000:
                    # Show first 2000 and last 6000 characters
                    content_preview = content[:2000] + "\n\n[... middle section omitted ...]\n\n" + content[-6000:]
                    prompt += f"\n### {doc_name} Document (showing beginning and END sections where MEMO TEXT DETAILS appears):\n{content_preview}\n"
                else:
                    content_preview = content
                    prompt += f"\n### {doc_name} Document:\n{content_preview}\n"
            else:
                # If content is too long, only take first 8000 characters
                content_preview = content[:8000] if len(content) > 8000 else content
                prompt += f"\n### {doc_name} Document:\n{content_preview}\n"
                if len(content) > 8000:
                    prompt += f"[... document truncated, total length: {len(content)} characters ...]\n"
        
        prompt += "\n## Output Requirements:\n\n"
        prompt += "Generate a JSON object with the following structure:\n\n"
        
        # Add critical format requirements for property type
        if self.company.endswith("_property"):
            prompt += self._build_property_format_requirements()
        
        # Build fields section from configuration
        fields_section = self._build_fields_prompt_section(self.fields_config)
        prompt += fields_section
        
        if self._is_caa_company():
            date_rule = "- For CAA, only date_of_birth fields must be MM/DD/YYYY. Do not force-convert other date fields."
        else:
            date_rule = "- All dates must be in YYYY-MM-DD format"

        if self._is_caa_company():
            caa_claim_policy_rule = """- For CAA claims, each claims item must include non-empty policy (Claim# / Policy#).
- Claim policy must be extracted from Autoplus claims section (the claim block that contains Loss Date / Company / Source / Policy).
- For every individual claim item, copy the Policy value from the same claim block into claim.policy (or claim_number if only Claim# is present).
- Do NOT leave claim.policy empty when Policy/Claim number exists in Autoplus text.
- If Policy is not printed in that claim block, try Claim# in the same block; if both are missing, then fallback to a global policy number."""
            caa_membership_rule = """- ⚠️ CRITICAL: CAA Membership Extraction Rule ⚠️
- THIS IS ONE OF THE MOST IMPORTANT FIELDS - DO NOT SKIP THIS CHECK!
- SEARCH FOR THIS EXACT PATTERN: "Group discount apply: yes - CAA" - if you find this pattern ANYWHERE in the Application PDF or Quote PDF, you MUST set caa_membership to "Yes".
- This pattern often appears in sections like "MEMO TEXT DETAILS", "CSIO APPLICATION FOR AUTOMOBILE INSURANCE - OAF1 - MEMO TEXT DETAILS", or similar memo/remarks/details sections.
- The pattern may appear as: "Group discount apply: yes - CAA" or "Group discount apply: yes - CAA | Member #: [NUMBER]"
- EXAMPLE: If you see "Group discount apply: yes - CAA | Member #: 620 2822 4256 53003", then:
  * caa_membership MUST be "Yes" (NOT "No", NOT null)
  * caa_membership_number MUST be extracted as "6202822425653003" (remove all spaces)
- When caa_membership is "Yes", caa_membership_number CANNOT be null or empty - the number is ALWAYS on the SAME LINE as "Group discount apply: yes - CAA" after the "| Member #:" separator.
- Search in both Application PDF and Quote PDF thoroughly, especially in memo/remarks/details sections. Use Ctrl+F or search function if needed.
- The membership number format is typically digits with optional spaces (e.g., "620 2822 4256 53003" or "6202822425653003").
- If you find "Group discount apply: yes - CAA" but the membership number seems missing, look more carefully on the same line - it's ALWAYS right there after "| Member #:" on the same line.
- COMMON MISTAKE: Setting caa_membership to "No" when the pattern exists - DO NOT DO THIS! Always search first before setting to "No"."""
        else:
            caa_claim_policy_rule = ""
            caa_membership_rule = ""

        prompt += f"""

## ⚠️ CRITICAL EXTRACTION CHECKLIST - READ THIS FIRST ⚠️

Before extracting any fields, you MUST perform these checks:

0. **COVERAGES EXTRACTION CHECK (MANDATORY - DO THIS FOR EVERY VEHICLE)**:
   
   **When extracting `coverages_information`, you MUST extract ALL rows from coverage/premium tables:**
   
   **Standard Coverages (always extract these):**
   - Bodily Injury
   - Property Damage
   - Direct Compensation
   - Accident Benefits
   - All Perils
   - Uninsured Automobile
   
   **OPCF Options (extract ALL you find, including but not limited to):**
   - #5 Rent or Lease
   - #20 Loss of Use
   - #27 Liab to Unowned Veh.
   - #43a Limited Waiver
   - #44 Family Protection
   - Any other options starting with #
   
   **Protection Options (extract ALL you find, including but not limited to):**
   - Minor Conviction Protection
   - Forgive & Forget
   - Any other protection types in the table
   
   **CRITICAL RULE:**
   - Look at EVERY row in coverage/premium tables in the Quote PDF
   - Extract EVERY coverage and protection option you see
   - Do NOT skip any rows - if it's in the table, it MUST be in your output
   - Each option should have: principal, totals, and/or coverage_amount fields

1. **CAA MEMBERSHIP CHECK (MANDATORY FIRST STEP - DO THIS BEFORE ANYTHING ELSE)**:
   
   **STEP 1: Search for the pattern**
   - Use Ctrl+F or search function to find: "Group discount apply: yes - CAA"
   - ⚠️ CRITICAL: Search in ALL documents, including:
     * Application PDF (especially the LATER/END sections - this info often appears near the end of the document)
     * Quote PDF (the pattern may ONLY appear in Quote PDF, not in Application PDF)
     * ALL other provided documents
   - ⚠️ IMPORTANT: Do NOT skip the later pages/sections of documents - this information is often found:
     * Near the END of Application PDF documents
     * In the middle or end sections of Quote PDF documents
     * In sections that come AFTER the main form fields
   - ⚠️ SPECIFIC LOCATION TO CHECK (THIS IS WHERE IT ALMOST ALWAYS APPEARS):
     * Look for section header: "CSIO APPLICATION FOR AUTOMOBILE INSURANCE - OAF1 - MEMO TEXT DETAILS"
     * This section appears at the END of Application PDF documents (after page 4 or 5, near the very end)
     * In this section, you will see multiple lines of text like:
       ```
       Combined Policy / Multi-line discount: yes - Cross Ref: BINDER58154
       Group discount apply: yes - CAA | Member #: 620 2822 4256 53003
       Number of Telematics: 0
       ```
     * Search for the EXACT line: "Group discount apply: yes - CAA | Member #: [NUMBER]"
     * The pattern is ALWAYS on a single line in this MEMO TEXT DETAILS section
     * The membership number (e.g., "620 2822 4256 53003") is RIGHT THERE on the same line after "| Member #:"
     * ⚠️ DO NOT MISS THIS! It's literally right there in the text!
   - This pattern appears frequently in sections like:
     * "MEMO TEXT DETAILS" (often near the end of Application PDF)
     * "CSIO APPLICATION FOR AUTOMOBILE INSURANCE - OAF1 - MEMO TEXT DETAILS" (THIS IS THE MOST COMMON LOCATION!)
     * Similar memo/remarks/details sections (typically in later pages)
   
   **STEP 2: If pattern is found**
   - You MUST set `caa_membership` to "Yes" (NOT "No", NOT null)
   - You MUST extract the membership number from the SAME LINE
   - The pattern looks like: "Group discount apply: yes - CAA | Member #: 620 2822 4256 53003"
   - ⚠️ CRITICAL: The membership number is ALWAYS on the SAME LINE, right after "| Member #:"
   - Extract everything after "| Member #:" as the membership number (including spaces, you'll remove them later)
   - Remove all spaces from the membership number before outputting
   - Example extraction:
     * Input line: "Group discount apply: yes - CAA | Member #: 620 2822 4256 53003"
     * Extract: "620 2822 4256 53003"
     * Remove spaces: "6202822425653003"
     * Output: `caa_membership`: "Yes", `caa_membership_number`: "6202822425653003"
   - ⚠️ REMEMBER: If you see "Group discount apply: yes - CAA" anywhere, the membership number MUST be on that same line!
   
   **STEP 3: If pattern is NOT found**
   - Only after thoroughly searching ALL documents and confirming the pattern is absent
   - Then set `caa_membership` to "No"
   
   **COMMON MISTAKES TO AVOID:**
   - ❌ Setting `caa_membership` to "No" without searching ALL documents thoroughly
   - ❌ Only searching the beginning of documents - the pattern is often in LATER sections
   - ❌ Only searching Application PDF - the pattern may ONLY be in Quote PDF
   - ❌ Missing the pattern because it's in a memo/details section near the end
   - ❌ Setting to "Yes" but not extracting the membership number
   - ❌ Extracting membership number with spaces (should remove spaces)
   
   **VERIFICATION & SELF-CHECK (CRITICAL - DO THIS BEFORE OUTPUTTING JSON):**
   - Before finalizing your JSON, perform this self-check:
     1. Did I search for "Group discount apply: yes - CAA" in ALL documents (including later sections)?
     2. What did I set for `caa_membership`?
     3. What did I set for `caa_membership_number`?
   
   - ⚠️ CRITICAL VALIDATION RULE ⚠️:
     * If `caa_membership` is "Yes" BUT `caa_membership_number` is null, empty string, or missing:
       → THIS IS INVALID! You MUST re-search the documents for the membership number
       → The membership number MUST exist if membership is "Yes"
       → Go back and search more carefully, especially in:
         - Later sections of Application PDF
         - All sections of Quote PDF
         - Look for the pattern: "Group discount apply: yes - CAA | Member #: [NUMBER]"
       → Extract the number from the SAME LINE as the pattern
       → Only output JSON when `caa_membership_number` has a valid value (not empty)
   
   - If `caa_membership` is "Yes" → `caa_membership_number` MUST have a value (cannot be null or empty)
   - If `caa_membership` is "No" → `caa_membership_number` can be null or empty
   
   - Final check before output: If caa_membership="Yes" and caa_membership_number is empty/null, STOP and re-search!

## Important Rules:
{date_rule}
{caa_claim_policy_rule}
{caa_membership_rule}
- Use null (NOT empty string, NOT other values) for missing or blank information
- Driver and vehicle keys must use numeric suffixes (driver_1, vehicle_1, etc.)
- Extract convictions from MVR documents with date and description
- If a conviction is for speeding, include the km/h field
- Province codes must be standard Canadian abbreviations (ON, BC, AB, QC, etc.)

## CRITICAL: Table Reading Method
For ALL table-based fields, you MUST:
1. FIRST identify the COLUMN HEADERS in the table
2. THEN match each field to its corresponding column by HEADER NAME (not position)
3. Extract ONLY the value directly under that header's column
4. If a cell is blank, return null - DO NOT take values from adjacent columns

This is especially important for the purchase information table - see detailed instructions below.

## ⚠️ CRITICAL: Purchase Table Column Alignment - ABSOLUTE REQUIREMENT ⚠️

**STOP AND READ THIS CAREFULLY BEFORE EXTRACTING PURCHASE FIELDS!**

The purchase information is in a TABLE. Each column has a HEADER LABEL. You MUST match fields to columns by HEADER NAME, NOT by reading left-to-right!

**VISUAL REPRESENTATION OF THE TABLE STRUCTURE:**

```
Column 1: [Purchase Condition]  →  purchase_condition
Column 2: [Purchase Date]        →  purchase_date
Column 3: [km at Purchase]       →  km_at_purchase
Column 4: [List Price New]       →  list_price_new
Column 5: [Purchase Price]       →  purchase_price
Column 6: [Winter Tires]         →  winter_tires
Column 7: [Parking at Night]      →  parking_at_night
```

**THE EXACT PROCESS YOU MUST FOLLOW:**

For EACH field (km_at_purchase, list_price_new, purchase_price, etc.):

1. **FIND THE COLUMN HEADER**: Search for the exact header text (e.g., "km at Purchase", "List Price New")
2. **LOOK DIRECTLY BELOW THAT HEADER**: Read ONLY the cell that is directly under that specific header
3. **CHECK IF CELL IS BLANK**: 
   - If the cell directly under the header is EMPTY/BLANK → return null
   - If the cell directly under the header has a value → use that value
4. **DO NOT LOOK AT OTHER COLUMNS**: Even if you see a value nearby, if it's not directly under the correct header, ignore it!

**THE MOST COMMON MISTAKE TO AVOID:**

❌ **WRONG**: Reading left-to-right: "I see Used, then 03/05/2013, then 29705, so km_at_purchase = 29705"
✅ **CORRECT**: Finding header "km at Purchase", looking directly below it, seeing it's blank, so km_at_purchase = null

**CONCRETE EXAMPLE - THIS IS WHAT YOU WILL SEE:**

The table row looks like this (values on top, headers below):
```
Row 1 (values):    Used    03/05/2013    29705    Yes    Private Driveway
Row 2 (headers):   Purchase Purchase     km at   List    Purchase Winter Parking
                   Condition Date         Purchase Price  Price    Tires  at Night
```

**CORRECT EXTRACTION PROCESS:**

1. For `km_at_purchase`:
   - Find header: "km at Purchase"
   - Look directly below "km at Purchase" header
   - See: BLANK/EMPTY cell
   - Result: `km_at_purchase = null` ✅

2. For `list_price_new`:
   - Find header: "List Price New"
   - Look directly below "List Price New" header
   - See: "29705"
   - Result: `list_price_new = "29705"` ✅

3. For `purchase_price`:
   - Find header: "Purchase Price"
   - Look directly below "Purchase Price" header
   - See: BLANK/EMPTY cell
   - Result: `purchase_price = null` ✅

**CRITICAL REMINDER:**
- If you see "29705" but it's NOT directly under "km at Purchase" header → DO NOT use it for km_at_purchase!
- If "km at Purchase" column is blank → km_at_purchase MUST be null, even if you see "29705" in the next column!
- Each field reads from its OWN column only - never borrow from neighbors!

## ⚠️ CRITICAL: Vehicle Information Table Column Alignment ⚠️

**STOP AND READ THIS CAREFULLY BEFORE EXTRACTING VEHICLE BASIC INFORMATION FIELDS!**

The vehicle information table contains fields like: Annual km, Business km, Daily km, Garaging Location, Single Vehicle MVD, Leased, Cylinders, etc.

**THE EXACT PROCESS YOU MUST FOLLOW:**

For EACH field (annual_km, business_km, daily_km, garaging_location, cylinders, etc.):

1. **FIND THE COLUMN HEADER**: Search for the exact header text (e.g., "Daily km", "Cylinders")
2. **LOOK DIRECTLY BELOW THAT HEADER**: Read ONLY the cell that is directly under that specific header
3. **CHECK IF CELL IS BLANK**: 
   - If the cell directly under the header is EMPTY/BLANK → return null (or empty string for km fields)
   - If the cell directly under the header has a value → use that value
4. **DO NOT SHIFT VALUES**: Even if a field is blank, DO NOT take values from adjacent columns!

**COMMON MISTAKE TO AVOID:**

❌ **WRONG**: "I see '4' after 'Daily km' header, so daily_km = '4'"
   - But actually "4" is under "Cylinders" header, not "Daily km"!
   - If "Daily km" column is blank → daily_km MUST be null/empty!

✅ **CORRECT**: 
   - Find header "Daily km" → Look directly below it → See BLANK → daily_km = null
   - Find header "Cylinders" → Look directly below it → See "4" → cylinders = "4"

**CONCRETE EXAMPLE:**

Table structure:
```
Row 1 (values):    10000    (blank)    (blank)    ETOBICOKE M9W5X7    No    No    4
Row 2 (headers):   Annual   Business   Daily      Garaging           Single Leased Cylinders
                   km       km         km          Location            Vehicle MVD
```

**CORRECT EXTRACTION:**
- annual_km: Find "Annual km" header → Below it: "10000" → annual_km = "10000" ✅
- business_km: Find "Business km" header → Below it: BLANK → business_km = null ✅
- daily_km: Find "Daily km" header → Below it: BLANK → daily_km = null ✅
- garaging_location: Find "Garaging Location" header → Below it: "ETOBICOKE M9W5X7" → garaging_location = "ETOBICOKE M9W5X7" ✅
- cylinders: Find "Cylinders" header → Below it: "4" → cylinders = "4" ✅

**CRITICAL REMINDER:**
- If "Daily km" column is blank → daily_km MUST be null/empty, even if you see "4" in the next column!
- "4" belongs to "Cylinders" column, NOT "Daily km" column!
- Each field reads from its OWN column only - never shift values from adjacent columns!

Please carefully analyze all documents and extract accurate information to generate a complete JSON object. 

## DEBUG MODE: Extraction Reasoning
To help debug extraction issues, please include an "_extraction_reasoning" field at the root level of your JSON with DETAILED explanations for purchase-related fields.

**REQUIRED EXPLANATION FOR EACH FIELD:**

For `km_at_purchase`:
- Step 1: Describe how you found the "km at Purchase" column header in the table
- Step 2: Describe what you saw directly below that header (was it blank? was there a value?)
- Step 3: Explain your final decision (null or value) and WHY
- Step 4: If you saw "29705" anywhere, explain WHERE you saw it and why you did or didn't use it for km_at_purchase

For `list_price_new`:
- Step 1: Describe how you found the "List Price New" column header in the table
- Step 2: Describe what you saw directly below that header (was it blank? was there a value like "29705"?)
- Step 3: Explain your final decision (null or value) and WHY
- Step 4: If you saw "29705", explain WHERE you saw it and confirm it was under "List Price New" header

Example format:
```json
{{
  "_extraction_reasoning": {{
    "km_at_purchase": "I searched for the column header 'km at Purchase' in the table. I found it in column 3. When I looked directly below this header, the cell was completely blank/empty. Therefore, I set km_at_purchase to null. I did see '29705' in the document, but it was in column 4 under 'List Price New' header, so I correctly did NOT use it for km_at_purchase.",
    "list_price_new": "I searched for the column header 'List Price New' in the table. I found it in column 4. When I looked directly below this header, I saw the value '29705'. Therefore, I set list_price_new to '29705'. This value was directly under the 'List Price New' header, so it belongs to this field."
  }},
  ... rest of JSON ...
}}
```

## FINAL REMINDER BEFORE YOU START EXTRACTING:

**FOR PURCHASE TABLE FIELDS (km_at_purchase, list_price_new, purchase_price):**
- Each field reads from its OWN column header ONLY
- If a column is blank, that field = null (DO NOT borrow from next column!)
- "29705" under "List Price New" header → list_price_new = "29705"
- "29705" NOT under "km at Purchase" header → km_at_purchase = null (even if you see "29705" nearby!)

**DO NOT READ LEFT-TO-RIGHT! MATCH BY HEADER NAME!**

## ⚠️ FINAL OUTPUT VALIDATION - CHECK THIS BEFORE RETURNING JSON ⚠️

**MANDATORY CHECK FOR CAA MEMBERSHIP FIELDS:**

Before outputting your final JSON, you MUST verify:

1. Check `application_info.caa_membership` value:
   - If it is "Yes":
     * Check `application_info.caa_membership_number` value
     * If `caa_membership_number` is null, empty string "", or missing:
       → ⚠️ INVALID STATE! DO NOT OUTPUT THIS JSON!
       → You MUST re-search the documents for the membership number
       → Search for: "Group discount apply: yes - CAA | Member #: [NUMBER]"
       → Look in later sections of Application PDF and all sections of Quote PDF
       → Extract the number from the SAME LINE as the pattern
       → Only output JSON when you have found and extracted the membership number
   
2. Final validation rule:
   - ✅ VALID: `caa_membership: "Yes"` AND `caa_membership_number: "6202822425653003"` (has value)
   - ✅ VALID: `caa_membership: "No"` AND `caa_membership_number: ""` or null (can be empty)
   - ❌ INVALID: `caa_membership: "Yes"` AND `caa_membership_number: ""` or null (MUST re-search!)

**If you find yourself about to output `caa_membership: "Yes"` with an empty `caa_membership_number`, STOP and re-search the documents!**

IMPORTANT: You must return ONLY valid JSON. Do not include any explanatory text, markdown formatting, or code blocks outside the JSON. Start your response directly with {{ and end with }}."""
        
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
        """Call Anthropic API directly and return text response."""
        if not self.client:
            raise RuntimeError("Anthropic client is not initialized")

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        print("[Step 3] API call successful!")
        return response.content[0].text

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
        try:
            return json.loads(result_text)
        except json.JSONDecodeError:
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise ValueError("No valid JSON found in response")
    
    def _validate_and_clean_json(self, data: Dict, documents: Optional[Dict[str, str]] = None) -> Dict:
        """Validate and clean generated JSON"""
        # Ensure required fields exist
        required_fields = [
            "applicant_information",
            "address",
            "application_info",
            "drivers_information",
            "vehicles_information"
        ]
        
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

        # CAA-specific post-processing and normalization
        if self._should_apply_caa_dob_normalization(data):
            # 1) Normalize DOB fields
            data, changed_count = self._normalize_caa_birth_dates(data)
            if changed_count > 0:
                print(f"[INFO] Normalized {changed_count} date_of_birth field(s) to MM/DD/YYYY")
            # 2) Fix common vehicle purchase table issues
            data, corrected_vehicles = self._apply_caa_vehicle_purchase_sanity(data)
            if corrected_vehicles > 0:
                print(f"[INFO] Corrected purchase table column misalignment in {corrected_vehicles} vehicle(s)")
            # 3) Fix vehicle information table column misalignment (daily_km, business_km, cylinders, etc.)
            data, misalignment_fixes = self._fix_vehicle_table_column_misalignment(data)
            if misalignment_fixes > 0:
                print(f"[INFO] Fixed {misalignment_fixes} vehicle information table column misalignment issue(s)")
            # 4) Enforce CAA Auto Submission JSON structure/rules
            data = self._apply_caa_output_normalization(data, documents)
        
        # Property-specific post-processing
        if self.company.endswith("_property"):
            data = self._normalize_property_names(data)
            data = self._normalize_property_structure(data)
        
        return data

    @staticmethod
    def _format_to_mmddyyyy(date_value):
        """Convert common date formats to MM/DD/YYYY; return original if conversion fails."""
        if date_value is None:
            return date_value
        if not isinstance(date_value, str):
            return date_value

        value = date_value.strip()
        if not value:
            return date_value

        # Already correct format
        if re.match(r"^\d{2}/\d{2}/\d{4}$", value):
            return value

        # Fast path for ISO date
        iso_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
        if iso_match:
            year, month, day = iso_match.groups()
            return f"{month}/{day}/{year}"

        for fmt in ("%Y/%m/%d", "%m-%d-%Y", "%m/%d/%Y", "%Y.%m.%d"):
            try:
                dt = datetime.strptime(value, fmt)
                return dt.strftime("%m/%d/%Y")
            except ValueError:
                continue

        return date_value

    def _should_apply_caa_dob_normalization(self, data: Dict) -> bool:
        """Apply CAA DOB normalization for explicit CAA mode or CAA-like output."""
        if self._is_caa_company():
            return True

        if not isinstance(data, dict):
            return False

        application_info = data.get("application_info")
        if isinstance(application_info, dict) and "caa_membership" in application_info:
            return True

        carrier_info = data.get("carrier_information")
        if isinstance(carrier_info, dict):
            carrier_name = carrier_info.get("carrier_name")
            if isinstance(carrier_name, str) and "CAA" in carrier_name.upper():
                return True

        return False

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
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        return False

    @staticmethod
    def _extract_digits_as_int(value):
        if not isinstance(value, str):
            return None
        digits = re.sub(r"\D", "", value)
        if not digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None

    @staticmethod
    def _is_non_price_text(value) -> bool:
        """Check if value is clearly non-price text (like parking locations, Yes/No, etc.)"""
        if not isinstance(value, str):
            return False
        value_lower = value.strip().lower()
        # Common non-price patterns
        non_price_patterns = [
            "private driveway", "private garage", "private street", "private lot", "private parking",
            "street", "garage", "driveway", "parking",
            "yes", "no", "new", "used", "demo"
        ]
        return value_lower in non_price_patterns

    def _apply_caa_vehicle_purchase_sanity(self, data: Dict):
        """
        Validate and fix obvious errors in purchase-related fields:
        1. Clear non-price text from price fields (e.g., "Private Driveway" in purchase_price)
        2. Ensure empty fields are null
        3. Handle special case: if purchase_condition is New, km_at_purchase is implausibly high (>=5000),
           and list_price_new is missing, move km_at_purchase -> list_price_new.
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

            # Note: We do NOT auto-fix column misalignment here - the model should extract correctly from the start
            # Only validate and clear obviously invalid values (non-price text in price fields)

        return data, corrected
    
    def _fix_vehicle_table_column_misalignment(self, data: Dict):
        """
        Fix column misalignment issues in vehicle information table.
        Common issue: when daily_km is blank, but a value from cylinders column is incorrectly extracted as daily_km.
        
        Detection logic:
        - If daily_km is a single digit (like "4") and cylinders is also the same value, 
          it's likely daily_km was incorrectly extracted from cylinders column
        - If daily_km is a single digit but cylinders is different or missing, 
          it might still be misaligned (daily_km should rarely be a single digit)
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
            annual_km = vehicle.get("annual_km")
            
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
                    elif business_km is None or (isinstance(business_km, str) and not business_km.strip()):
                        # If business_km is also empty, daily_km being a single digit is suspicious
                        # (daily_km should typically be larger numbers or empty)
                        print(f"[WARNING] Vehicle '{vehicle_key}': daily_km='{daily_km}' is a single digit "
                              f"and business_km is empty. This suggests possible misalignment. Clearing daily_km.")
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
        """
        Normalize name field to ensure:
        - At least 2 words separated by spaces
        - Last word (Last Name) has at least 2 characters
        - Multiple spaces normalized to single space
        - Remove special characters and invisible characters
        - Preserve Unicode characters (including Chinese characters)
        """
        if not isinstance(name, str):
            return name
        
        # Remove leading/trailing whitespace
        name = name.strip()
        
        if not name:
            return name
        
        # Remove invisible characters (zero-width spaces, etc.)
        # Keep Unicode word characters, spaces, hyphens, and dots
        name = re.sub(r'[\u200B-\u200D\uFEFF]', '', name)  # Remove zero-width characters
        
        # More permissive regex: keep Unicode letters, digits, spaces, hyphens, dots, apostrophes
        # Use \w which matches Unicode word characters (including Chinese) in Python 3
        # Remove only clearly problematic characters (control chars, symbols except hyphens/apostrophes)
        try:
            # Python 3: \w matches Unicode word characters by default
            # Remove characters that are NOT: word chars, spaces, hyphens, apostrophes, dots
            name = re.sub(r'[^\w\s\-\'\.]', '', name, flags=re.UNICODE)
        except:
            # Fallback: if Unicode flag fails, use ASCII-safe pattern
            # But this should rarely happen in Python 3
            name = re.sub(r'[^\w\s\-\'\.]', '', name)
        
        # Normalize multiple spaces to single space
        name = re.sub(r'\s+', ' ', name)
        
        # Remove leading/trailing spaces again after normalization
        name = name.strip()
        
        if not name:
            return name
        
        # Split into words (preserve all non-empty words)
        words = [w.strip() for w in name.split() if w.strip()]
        
        if len(words) == 0:
            return name
        
        # Clean each word: remove only clearly problematic characters, preserve Unicode
        cleaned_words = []
        for word in words:
            # Remove only non-word, non-hyphen, non-apostrophe characters
            # Preserve Unicode letters (including Chinese) - \w matches Unicode word chars in Python 3
            try:
                cleaned_word = re.sub(r'[^\w\-\']', '', word, flags=re.UNICODE)
            except:
                cleaned_word = re.sub(r'[^\w\-\']', '', word)
            if cleaned_word:  # Only add non-empty words
                cleaned_words.append(cleaned_word)
        
        if len(cleaned_words) == 0:
            return "Unknown Unknown"
        
        # CRITICAL: Validate that we have at least 2 words before proceeding
        if len(cleaned_words) < 2:
            # If only one word, duplicate it to create a valid name
            single_word = cleaned_words[0]
            if len(single_word) >= 2:
                return f"{single_word} {single_word}"
            else:
                # If less than 2 characters, pad it
                padded = single_word.ljust(2, 'X')
                return f"{single_word} {padded}"
        
        # Check if last word (Last Name) has at least 2 characters
        last_word = cleaned_words[-1]
        if len(last_word) < 2:
            # If last word is too short, try to combine with previous word
            if len(cleaned_words) >= 2:
                # Use the second-to-last word as last name if it's longer
                second_last = cleaned_words[-2]
                if len(second_last) >= 2:
                    # Use second-to-last as last name, combine rest (including the short last word) as first name
                    first_name_parts = cleaned_words[:-2] + [last_word]
                    first_name = ' '.join(first_name_parts) if first_name_parts else second_last
                    # CRITICAL: Ensure first_name is not empty
                    if not first_name or not first_name.strip():
                        first_name = second_last if len(second_last) >= 1 else "Unknown"
                    return f"{first_name} {second_last}"
                else:
                    # Both are short, combine them as last name
                    combined_last_name = second_last + last_word
                    if len(combined_last_name) >= 2:
                        first_name = ' '.join(cleaned_words[:-2]) if len(cleaned_words) > 2 else "Unknown"
                        # CRITICAL: Ensure first_name is not empty
                        if not first_name or not first_name.strip():
                            first_name = "Unknown"
                        return f"{first_name} {combined_last_name}"
                    else:
                        # Pad the combined name
                        padded_last = combined_last_name.ljust(2, 'X')
                        first_name = ' '.join(cleaned_words[:-2]) if len(cleaned_words) > 2 else "Unknown"
                        # CRITICAL: Ensure first_name is not empty
                        if not first_name or not first_name.strip():
                            first_name = "Unknown"
                        return f"{first_name} {padded_last}"
            else:
                # Only one word, should not reach here (handled above), but handle it
                padded_last = last_word.ljust(2, 'X')
                return f"{last_word} {padded_last}"
        
        # Final validation: ensure we have at least 2 words and First Name is not empty
        if len(cleaned_words) < 2:
            if len(cleaned_words) == 1:
                single_word = cleaned_words[0]
                if len(single_word) >= 2:
                    return f"{single_word} {single_word}"
                else:
                    padded = single_word.ljust(2, 'X')
                    return f"{single_word} {padded}"
            else:
                return "Unknown Unknown"
        
        # CRITICAL: Final check - ensure First Name (all words except last) is not empty
        first_name_parts = cleaned_words[:-1]
        first_name = ' '.join(first_name_parts)
        
        # If First Name is empty after joining, something went wrong
        if not first_name or not first_name.strip():
            # This should not happen, but handle it gracefully
            if len(cleaned_words) >= 2:
                # Use first word as First Name
                first_name = cleaned_words[0]
            else:
                first_name = "Unknown"
        
        # Ensure Last Name has at least 2 characters
        last_name = cleaned_words[-1]
        if len(last_name) < 2:
            last_name = last_name.ljust(2, 'X')
        
        result = f"{first_name} {last_name}"
        
        # Final validation: split result and verify
        result_words = result.split()
        if len(result_words) < 2:
            # This should not happen, but handle it
            if len(result_words) == 1:
                single = result_words[0]
                return f"{single} {single}"
            else:
                return "Unknown Unknown"
        
        # Verify First Name is not empty
        result_first_name = ' '.join(result_words[:-1])
        if not result_first_name or not result_first_name.strip():
            # This is the critical error case - fix it
            result_first_name = result_words[0] if len(result_words) > 0 else "Unknown"
            result = f"{result_first_name} {result_words[-1]}"
        
        return result
    
    @staticmethod
    def _validate_and_debug_name(name: str, field_name: str):
        """
        Validate name field and print debug information.
        CRITICAL: This method detects and reports when First Name is empty.
        """
        if not isinstance(name, str):
            print(f"[WARNING] {field_name} is not a string: {type(name)}")
            return
        
        name = name.strip()
        if not name:
            print(f"[ERROR] {field_name} is empty or contains only whitespace")
            return
        
        # Split into words (preserve all words)
        words = [w.strip() for w in name.split() if w.strip()]
        word_count = len(words)
        
        if word_count < 2:
            print(f"[ERROR] {field_name} has only {word_count} word(s), need at least 2")
            print(f"  Original name: '{name}'")
            print(f"  Words: {words}")
            return
        
        # Extract first name and last name
        first_name_parts = words[:-1]
        first_name = ' '.join(first_name_parts)
        last_name = words[-1]
        
        # CRITICAL: Check if First Name is empty
        if not first_name or not first_name.strip():
            print(f"[ERROR] {field_name} - First Name is EMPTY after parsing!")
            print(f"  Original name: '{name}'")
            print(f"  Word count: {word_count}")
            print(f"  Words: {words}")
            print(f"  First Name parts: {first_name_parts}")
            print(f"  First Name (joined): '{first_name}'")
            print(f"  Last Name: '{last_name}'")
            print(f"  [CRITICAL] This indicates a parsing error - First Name should not be empty!")
            return
        
        # Check lengths
        first_name_len = len(first_name)
        last_name_len = len(last_name)
        
        # Print debug info
        print(f"[DEBUG] {field_name} validation:")
        print(f"  Original name: '{name}'")
        print(f"  Word count: {word_count}")
        print(f"  Words: {words}")
        print(f"  First Name: '{first_name}' (length: {first_name_len})")
        print(f"  Last Name: '{last_name}' (length: {last_name_len})")
        
        # Validate
        if first_name_len < 1:
            print(f"  [ERROR] First Name is too short (length: {first_name_len}, need >= 1)")
            print(f"  [CRITICAL] First Name must have at least 1 character!")
        
        if last_name_len < 2:
            print(f"  [ERROR] Last Name is too short (length: {last_name_len}, need >= 2)")
            print(f"  [CRITICAL] Last Name must have at least 2 characters!")
        
        # Check for special characters (but allow Unicode)
        try:
            if re.search(r'[^\w\s\-\'\.]', name, flags=re.UNICODE):
                print(f"  [WARNING] Name contains special characters (excluding Unicode letters)")
        except:
            if re.search(r'[^\w\s\-\'\.]', name):
                print(f"  [WARNING] Name contains special characters")
        
        # Check for multiple spaces
        if '  ' in name:
            print(f"  [WARNING] Name contains multiple consecutive spaces")
        
        # Final validation result
        if first_name_len >= 1 and last_name_len >= 2:
            print(f"  [OK] Name format is valid: First Name='{first_name}', Last Name='{last_name}'")
        else:
            print(f"  [ERROR] Name format is INVALID!")
            if first_name_len < 1:
                print(f"    - First Name is empty or too short")
            if last_name_len < 2:
                print(f"    - Last Name is too short")
    
    @staticmethod
    def _clean_coverage_amount(value: str) -> str:
        """
        清理coverage_amount字段，确保符合格式要求：
        1. 不包含$符号
        2. 不包含文字描述（如"Ded."）
        3. 免赔额为0时使用"0"
        4. 使用标准数字格式或K/M后缀
        5. 特殊值精确匹配（"Standard"、"Inc."、"60 Months"等）
        """
        if value is None:
            return value
        
        if not isinstance(value, str):
            value = str(value)
        
        original_value = value
        value = value.strip()
        
        # 保留特殊值（不处理）
        special_values = ["Standard", "Inc.", "Included", "N/A"]
        # 检查是否包含时间单位（如"60 Months"）
        if re.search(r'\d+\s*(Months?|Days?|Years?)', value, re.IGNORECASE):
            return value
        
        # 检查是否是特殊值（不区分大小写）
        if any(value.upper() == sv.upper() for sv in special_values):
            return value
        
        # 处理0值的情况
        zero_patterns = [
            r'^no\s+deductible$',
            r'^\$0\s*ded\.?$',
            r'^0\s*ded\.?$',
            r'^\$0$',
            r'^0$'
        ]
        for pattern in zero_patterns:
            if re.match(pattern, value, re.IGNORECASE):
                return "0"
        
        # 去除$符号
        value = value.replace('$', '')
        
        # 去除常见的文字描述（如"Ded.", "Deductible"等）
        # 但保留数字部分
        value = re.sub(r'\s*ded\.?\s*$', '', value, flags=re.IGNORECASE)
        value = re.sub(r'\s*deductible\s*$', '', value, flags=re.IGNORECASE)
        
        # 清理多余的空格
        value = value.strip()
        
        # 如果清理后为空，返回"0"
        if not value:
            return "0"
        
        # 如果值发生了变化，打印日志
        if value != original_value:
            print(f"[INFO] Cleaned coverage_amount: '{original_value}' -> '{value}'")
        
        return value
    
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

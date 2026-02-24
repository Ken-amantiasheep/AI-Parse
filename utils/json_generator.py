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

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.document_reader import extract_text_from_documents

class IntactJSONGenerator:
    """Generate JSON required for Intact upload from documents"""
    
    def __init__(self, config_path: Optional[str] = None, company: str = "Intact"):
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
        
        self.client = Anthropic(api_key=self.config["api_key"])
        self.model = self.config.get("model", "claude-sonnet-4-20250514")
        self.max_tokens = self.config.get("max_tokens", 4096)
        self.temperature = self.config.get("temperature", 0.1)
        self.company = company
        
        # Load company-specific fields configuration
        fields_config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config",
            f"{company.lower()}_fields_config.json"
        )
        
        if os.path.exists(fields_config_path):
            with open(fields_config_path, 'r', encoding='utf-8') as f:
                self.fields_config = json.load(f)
        else:
            # Use default/empty config if file doesn't exist
            self.fields_config = {
                "company": company,
                "description": f"{company} insurance JSON output format configuration",
                "fields": {}
            }
    
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
                        field_line += f"\n     → EXTRACTION LOGIC: {field_extraction_logic}"
                    
                    if field_description:
                        field_line += f"\n     → Description: {field_description}"
                    
                    sections.append(field_line)
            
            sections.append("")  # Empty line between sections
            section_num += 1
        
        return "\n".join(sections)
    
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

## Input Documents:
"""
        # Add document content (limit length to avoid too many tokens)
        for doc_name, content in documents.items():
            # If content is too long, only take first 8000 characters
            content_preview = content[:8000] if len(content) > 8000 else content
            prompt += f"\n### {doc_name} Document:\n{content_preview}\n"
            if len(content) > 8000:
                prompt += f"[... document truncated, total length: {len(content)} characters ...]\n"
        
        prompt += "\n## Output Requirements:\n\n"
        prompt += "Generate a JSON object with the following structure:\n\n"
        
        # Build fields section from configuration
        fields_section = self._build_fields_prompt_section(self.fields_config)
        prompt += fields_section
        
        if self.company.upper() == "CAA":
            date_rule = "- For CAA, only date_of_birth fields must be MM/DD/YYYY. Do not force-convert other date fields."
        else:
            date_rule = "- All dates must be in YYYY-MM-DD format"

        if self.company.upper() == "CAA":
            caa_claim_policy_rule = "- For CAA claims, each claims item must include non-empty policy (Claim# / Policy#)."
        else:
            caa_claim_policy_rule = ""

        prompt += f"""

## Important Rules:
{date_rule}
{caa_claim_policy_rule}
- Use null or empty string for missing information
- For table-based fields, map values by strict column-header alignment. Never shift a value horizontally into a neighboring column when a cell is blank.
- Driver and vehicle keys must use numeric suffixes (driver_1, vehicle_1, etc.)
- Extract convictions from MVR documents with date and description
- If a conviction is for speeding, include the km/h field
- Province codes must be standard Canadian abbreviations (ON, BC, AB, QC, etc.)

Please carefully analyze all documents and extract accurate information to generate a complete JSON object. 

IMPORTANT: You must return ONLY valid JSON. Do not include any explanatory text, markdown formatting, or code blocks. Start your response directly with {{ and end with }}."""
        
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
        if company and company != self.company:
            self.company = company
            # Reload fields config for the new company
            fields_config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "config",
                f"{company.lower()}_fields_config.json"
            )
            if os.path.exists(fields_config_path):
                with open(fields_config_path, 'r', encoding='utf-8') as f:
                    self.fields_config = json.load(f)
        # 1. Read all documents
        print("\n[Step 1] Reading documents...")
        documents = extract_text_from_documents(
            autoplus_path, autoplus_paths, quote_path, mvr_path, mvr_paths, application_form_path
        )
        print(f"[Step 1] Successfully read {len(documents)} document(s)")
        
        # 2. Build prompt
        print("\n[Step 2] Building prompt...")
        prompt = self._build_prompt(documents)
        
        # 3. Call API
        print("\n[Step 3] Calling Claude API...")
        print(f"Using model: {self.model}")
        try:
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
            
            # 4. Parse response
            print("[Step 3] API call successful!")
            result_text = response.content[0].text
            
            # Try to extract JSON (if response contains other text)
            try:
                # Try direct parsing
                result_json = json.loads(result_text)
            except json.JSONDecodeError:
                # If failed, try to extract JSON part
                import re
                json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
                if json_match:
                    result_json = json.loads(json_match.group())
                else:
                    raise ValueError("No valid JSON found in response")
            
            print("[Step 4] JSON generated successfully!")
            return self._validate_and_clean_json(result_json)
            
        except Exception as e:
            print(f"[ERROR] Failed to generate JSON: {e}")
            raise
    
    def _validate_and_clean_json(self, data: Dict) -> Dict:
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
            # 3) Enforce CAA Auto Submission JSON structure/rules
            data = self._apply_caa_output_normalization(data)
        
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
        if self.company.upper() == "CAA":
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

    def _apply_caa_vehicle_purchase_sanity(self, data: Dict):
        """
        Correct common CAA table-column misalignment:
        if purchase_condition is New, km_at_purchase is implausibly high (>=5000),
        and list_price_new is missing, move km_at_purchase -> list_price_new.
        """
        if not isinstance(data, dict):
            return data, 0

        vehicles = data.get("vehicles_information")
        if not isinstance(vehicles, dict):
            return data, 0

        corrected = 0
        for _, vehicle in vehicles.items():
            if not isinstance(vehicle, dict):
                continue

            condition = vehicle.get("purchase_condition")
            km_value = vehicle.get("km_at_purchase")
            list_price = vehicle.get("list_price_new")

            km_int = self._extract_digits_as_int(km_value) if isinstance(km_value, str) else None
            if condition == "New" and km_int is not None and km_int >= 5000 and self._is_missing(list_price):
                vehicle["list_price_new"] = km_value
                vehicle["km_at_purchase"] = None
                corrected += 1

        return data, corrected

    def _apply_caa_output_normalization(self, data: Dict) -> Dict:
        """
        Apply CAA Auto Submission JSON post-processing rules on top of model output.

        Key goals:
        - vehicles_information: no null purchase_price; drivers strings use '(PRN)'.
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

                # purchase_price: cannot be null, default to list_price_new or "0"
                purchase_price = vehicle.get("purchase_price")
                if purchase_price is None:
                    list_price = vehicle.get("list_price_new")
                    if self._is_missing(list_price):
                        vehicle["purchase_price"] = "0"
                    else:
                        vehicle["purchase_price"] = str(list_price)

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
            # avoid obvious nulls for strings we know are simple scalars
            for key in ("address", "phone", "caa_membership_number", "lessor"):
                if key in app_info and app_info[key] is None:
                    app_info[key] = ""

        return data

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

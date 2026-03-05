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
        fields_config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config",
            f"{company.lower()}_fields_config.json"
        )

        if os.path.exists(fields_config_path):
            with open(fields_config_path, 'r', encoding='utf-8') as f:
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
            caa_claim_policy_rule = """- For CAA claims, each claims item must include non-empty policy (Claim# / Policy#).
- Claim policy must be extracted from Autoplus claims section (the claim block that contains Loss Date / Company / Source / Policy).
- For every individual claim item, copy the Policy value from the same claim block into claim.policy (or claim_number if only Claim# is present).
- Do NOT leave claim.policy empty when Policy/Claim number exists in Autoplus text.
- If Policy is not printed in that claim block, try Claim# in the same block; if both are missing, then fallback to a global policy number."""
        else:
            caa_claim_policy_rule = ""

        prompt += f"""

## Important Rules:
{date_rule}
{caa_claim_policy_rule}
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
            return self._validate_and_clean_json(result_json)
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

    def _apply_caa_output_normalization(self, data: Dict) -> Dict:
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

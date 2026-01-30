"""
JSON Generator - Generate JSON from documents using Claude API
"""
import json
import os
import sys
from typing import Dict, Optional
from anthropic import Anthropic

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.document_reader import extract_text_from_documents

class IntactJSONGenerator:
    """Generate JSON required for Intact upload from documents"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize generator
        
        Args:
            config_path: Configuration file path, if None uses default path
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
    
    def _build_prompt(self, documents: Dict[str, str]) -> str:
        """Build detailed prompt"""
        prompt = """You are a professional insurance data extraction expert. Your task is to extract information from the provided documents and generate JSON data that meets the requirements for uploading to the Intact insurance system.

## Input Documents:
"""
        # Add document content (limit length to avoid too many tokens)
        for doc_name, content in documents.items():
            # If content is too long, only take first 8000 characters
            content_preview = content[:8000] if len(content) > 8000 else content
            prompt += f"\n### {doc_name} Document:\n{content_preview}\n"
            if len(content) > 8000:
                prompt += f"[... document truncated, total length: {len(content)} characters ...]\n"
        
        prompt += """
## Output Requirements:

Generate a JSON object with the following structure:

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
   - deductible: number

## Important Rules:
- All dates must be in YYYY-MM-DD format
- Use null or empty string for missing information
- Driver and vehicle keys must use numeric suffixes (driver_1, vehicle_1, etc.)
- Extract convictions from MVR documents with date and description
- If a conviction is for speeding, include the km/h field
- Province codes must be standard Canadian abbreviations (ON, BC, AB, QC, etc.)

Please carefully analyze all documents and extract accurate information to generate a complete JSON object. 

IMPORTANT: You must return ONLY valid JSON. Do not include any explanatory text, markdown formatting, or code blocks. Start your response directly with { and end with }."""
        
        return prompt
    
    def generate_json(
        self,
        autoplus_path: Optional[str] = None,
        quote_path: Optional[str] = None,
        mvr_path: Optional[str] = None,
        application_form_path: Optional[str] = None
    ) -> Dict:
        """
        Generate JSON from documents
        
        Args:
            autoplus_path: Autoplus document path
            quote_path: Quote document path
            mvr_path: MVR document path
            application_form_path: Application Form path
            
        Returns:
            Generated JSON dictionary
        """
        # 1. Read all documents
        print("\n[Step 1] Reading documents...")
        documents = extract_text_from_documents(
            autoplus_path, quote_path, mvr_path, application_form_path
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
        
        return data
    
    def save_json(self, data: Dict, output_path: str):
        """Save JSON to file"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n[SUCCESS] JSON saved to: {output_path}")

"""
JSON Format Validator and Fixer for Property Quote JSON
Validates and fixes common format issues in property quote JSON files
"""
import json
import re
from typing import Dict, List, Tuple, Optional


class PropertyJSONFormatValidator:
    """Validator and fixer for property quote JSON format requirements"""
    
    # Province name to abbreviation mapping
    PROVINCE_MAPPING = {
        "ontario": "ON",
        "british columbia": "BC",
        "alberta": "AB",
        "manitoba": "MB",
        "saskatchewan": "SK",
        "quebec": "QC",
        "new brunswick": "NB",
        "nova scotia": "NS",
        "prince edward island": "PE",
        "newfoundland and labrador": "NL",
        "yukon": "YT",
        "northwest territories": "NT",
        "nunavut": "NU"
    }
    
    # Common street type abbreviations
    STREET_TYPES = [
        "St", "Street", "Ave", "Avenue", "Rd", "Road", "Dr", "Drive",
        "Blvd", "Boulevard", "Ln", "Lane", "Ct", "Court", "Pl", "Place",
        "Way", "Cres", "Crescent", "Cir", "Circle", "Pkwy", "Parkway",
        "Terrace", "Tr", "Hwy", "Highway", "Rte", "Route"
    ]
    
    def __init__(self):
        self.issues_found = []
        self.fixes_applied = []
    
    def validate_and_fix(self, data: Dict) -> Tuple[Dict, List[str], List[str]]:
        """
        Validate and fix JSON format issues
        
        Returns:
            Tuple of (fixed_data, issues_found, fixes_applied)
        """
        self.issues_found = []
        self.fixes_applied = []
        
        if not isinstance(data, dict):
            return data, self.issues_found, self.fixes_applied
        
        # Fix address format
        data = self._fix_address_format(data)
        
        # Fix province format
        data = self._fix_province_format(data)
        
        # Fix phone format
        data = self._fix_phone_format(data)
        
        # Fix prev_insurance.end_date format
        data = self._fix_prev_insurance_end_date(data)
        
        # Fix coverages_information format
        data = self._fix_coverages_information_format(data)
        
        # Fix claims array format
        data = self._fix_claims_format(data)
        
        # Fix name format
        data = self._fix_name_format(data)
        
        return data, self.issues_found, self.fixes_applied
    
    def _fix_address_format(self, data: Dict) -> Dict:
        """Fix address format: ensure space between street name and type"""
        app_info = data.get("application_info")
        if not isinstance(app_info, dict):
            return data
        
        address_info = app_info.get("address")
        if not isinstance(address_info, dict):
            return data
        
        address_str = address_info.get("address")
        if not isinstance(address_str, str):
            return data
        
        original_address = address_str
        
        # Check if street type is attached without space
        for street_type in self.STREET_TYPES:
            # Pattern: word followed by street type without space
            pattern = rf'(\w+)({re.escape(street_type)})(\.?)(\s|$)'
            match = re.search(pattern, address_str, re.IGNORECASE)
            if match:
                # Found street type attached without space
                before = address_str[:match.start()]
                street_name = match.group(1)
                street_type_found = match.group(2)
                period = match.group(3)
                after = address_str[match.end():]
                
                # Fix: add space before street type
                fixed_address = f"{before}{street_name} {street_type_found}{period}{after}"
                address_info["address"] = fixed_address
                
                self.issues_found.append(
                    f"application_info.address.address: Missing space before street type "
                    f"('{original_address}' -> '{fixed_address}')"
                )
                self.fixes_applied.append(
                    f"Fixed address format: added space before '{street_type_found}'"
                )
                break
        
        return data
    
    def _fix_province_format(self, data: Dict) -> Dict:
        """Fix province format: convert full name to 2-letter abbreviation"""
        app_info = data.get("application_info")
        if not isinstance(app_info, dict):
            return data
        
        address_info = app_info.get("address")
        if not isinstance(address_info, dict):
            return data
        
        province = address_info.get("province")
        if not isinstance(province, str):
            return data
        
        province_lower = province.strip().lower()
        
        # Check if it's already an abbreviation (2 uppercase letters)
        if re.match(r'^[A-Z]{2}$', province.strip()):
            return data
        
        # Check if it's a full province name
        if province_lower in self.PROVINCE_MAPPING:
            fixed_province = self.PROVINCE_MAPPING[province_lower]
            address_info["province"] = fixed_province
            
            self.issues_found.append(
                f"application_info.address.province: Full name used "
                f"('{province}' -> '{fixed_province}')"
            )
            self.fixes_applied.append(
                f"Fixed province format: converted '{province}' to '{fixed_province}'"
            )
        
        return data
    
    def _fix_phone_format(self, data: Dict) -> Dict:
        """Fix phone format: recommend removing parentheses"""
        app_info = data.get("application_info")
        if not isinstance(app_info, dict):
            return data
        
        phone_info = app_info.get("phone")
        if not isinstance(phone_info, dict):
            return data
        
        phone_number = phone_info.get("number")
        if not isinstance(phone_number, str):
            return data
        
        original_number = phone_number
        
        # Remove parentheses and normalize format
        # Pattern: (###) ###-#### or (###)###-####
        pattern = r'\((\d{3})\)\s*(\d{3})-(\d{4})'
        match = re.search(pattern, phone_number)
        if match:
            # Convert to ###-###-#### format
            fixed_number = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
            phone_info["number"] = fixed_number
            
            self.issues_found.append(
                f"application_info.phone.number: Contains parentheses "
                f"('{original_number}' -> '{fixed_number}')"
            )
            self.fixes_applied.append(
                f"Fixed phone format: removed parentheses"
            )
        
        return data
    
    def _fix_prev_insurance_end_date(self, data: Dict) -> Dict:
        """Fix prev_insurance.end_date: convert string to object format"""
        app_info = data.get("application_info")
        if not isinstance(app_info, dict):
            return data
        
        prev_insurance = app_info.get("prev_insurance")
        if not isinstance(prev_insurance, dict):
            return data
        
        end_date = prev_insurance.get("end_date")
        
        # If it's already an object with month/day/year, check format
        if isinstance(end_date, dict):
            # Validate object format
            month = end_date.get("month")
            day = end_date.get("day")
            year = end_date.get("year")
            
            if month and day and year:
                # Ensure all are strings and properly formatted
                if not isinstance(month, str) or not isinstance(day, str) or not isinstance(year, str):
                    # Convert to strings
                    end_date["month"] = str(month).zfill(2) if month else "01"
                    end_date["day"] = str(day).zfill(2) if day else "01"
                    end_date["year"] = str(year) if year else "2024"
                    self.fixes_applied.append("Fixed prev_insurance.end_date: converted values to strings")
                return data
        
        # If it's a string, convert to object
        if isinstance(end_date, str):
            # Try to parse YYYY-MM-DD format
            ymd_match = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', end_date)
            if ymd_match:
                year, month, day = ymd_match.groups()
                prev_insurance["end_date"] = {
                    "month": month,
                    "day": day,
                    "year": year
                }
                self.issues_found.append(
                    f"application_info.prev_insurance.end_date: String format "
                    f"('{end_date}' -> object format)"
                )
                self.fixes_applied.append(
                    f"Fixed prev_insurance.end_date: converted string to object format"
                )
                return data
            
            # Try to parse MM/DD/YYYY format
            mdy_match = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', end_date)
            if mdy_match:
                month, day, year = mdy_match.groups()
                prev_insurance["end_date"] = {
                    "month": month,
                    "day": day,
                    "year": year
                }
                self.issues_found.append(
                    f"application_info.prev_insurance.end_date: String format "
                    f"('{end_date}' -> object format)"
                )
                self.fixes_applied.append(
                    f"Fixed prev_insurance.end_date: converted string to object format"
                )
                return data
        
        return data
    
    def _fix_coverages_information_format(self, data: Dict) -> Dict:
        """Fix coverages_information: ensure it's an array, not an object"""
        coverages = data.get("coverages_information")
        
        if coverages is None:
            return data
        
        # If it's already an array, return
        if isinstance(coverages, list):
            return data
        
        # If it's an object, convert to array format
        if isinstance(coverages, dict):
            if len(coverages) == 0:
                data["coverages_information"] = []
                self.issues_found.append(
                    "coverages_information: Empty object {} -> empty array []"
                )
                self.fixes_applied.append(
                    "Fixed coverages_information: converted empty object to array"
                )
            else:
                # Convert object to array format
                coverage_array = []
                for key, value in coverages.items():
                    coverage_array.append({key: value})
                data["coverages_information"] = coverage_array
                
                self.issues_found.append(
                    f"coverages_information: Object format -> array format "
                    f"({len(coverage_array)} elements)"
                )
                self.fixes_applied.append(
                    f"Fixed coverages_information: converted object to array format"
                )
        
        return data
    
    def _fix_claims_format(self, data: Dict) -> Dict:
        """Fix claims: ensure it's an array, not null"""
        insured_info = data.get("insured_information")
        if isinstance(insured_info, dict) and "claims" in insured_info:
            claims = insured_info.get("claims")
            if claims is None:
                insured_info["claims"] = []
                self.issues_found.append(
                    "insured_information.claims: null -> empty array []"
                )
                self.fixes_applied.append(
                    "Fixed claims: converted null to empty array"
                )
        
        return data
    
    def _fix_name_format(self, data: Dict) -> Dict:
        """Fix name format: ensure at least 2 words, last word has at least 2 chars"""
        insured_info = data.get("insured_information")
        if isinstance(insured_info, dict):
            name = insured_info.get("name")
            if isinstance(name, str):
                fixed_name = self._normalize_name(name)
                if fixed_name != name:
                    insured_info["name"] = fixed_name
                    self.issues_found.append(
                        f"insured_information.name: Invalid format "
                        f"('{name}' -> '{fixed_name}')"
                    )
                    self.fixes_applied.append(
                        f"Fixed name format: normalized to '{fixed_name}'"
                    )
        
        # Also check coinsured_information
        coinsured_info = data.get("coinsured_information")
        if isinstance(coinsured_info, dict):
            name = coinsured_info.get("name")
            if isinstance(name, str) and name.strip():
                fixed_name = self._normalize_name(name)
                if fixed_name != name:
                    coinsured_info["name"] = fixed_name
                    self.issues_found.append(
                        f"coinsured_information.name: Invalid format "
                        f"('{name}' -> '{fixed_name}')"
                    )
                    self.fixes_applied.append(
                        f"Fixed name format: normalized to '{fixed_name}'"
                    )
        
        return data
    
    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize name to ensure at least 2 words, last word has at least 2 chars"""
        if not isinstance(name, str):
            return name
        
        name = name.strip()
        if not name:
            return "Unknown Unknown"
        
        # Normalize multiple spaces
        name = re.sub(r'\s+', ' ', name)
        
        # Split into words
        words = [w.strip() for w in name.split() if w.strip()]
        
        if len(words) == 0:
            return "Unknown Unknown"
        
        # If only one word, duplicate it
        if len(words) == 1:
            single_word = words[0]
            if len(single_word) >= 2:
                return f"{single_word} {single_word}"
            else:
                padded = single_word.ljust(2, 'X')
                return f"{single_word} {padded}"
        
        # Check if last word has at least 2 characters
        last_word = words[-1]
        if len(last_word) < 2:
            # Try to combine with previous word
            if len(words) >= 2:
                second_last = words[-2]
                if len(second_last) >= 2:
                    # Use second-to-last as last name
                    first_name_parts = words[:-2] + [last_word]
                    first_name = ' '.join(first_name_parts) if first_name_parts else second_last
                    if not first_name or not first_name.strip():
                        first_name = second_last if len(second_last) >= 1 else "Unknown"
                    return f"{first_name} {second_last}"
                else:
                    # Combine both as last name
                    combined_last = second_last + last_word
                    if len(combined_last) >= 2:
                        first_name = ' '.join(words[:-2]) if len(words) > 2 else "Unknown"
                        if not first_name or not first_name.strip():
                            first_name = "Unknown"
                        return f"{first_name} {combined_last}"
                    else:
                        padded_last = combined_last.ljust(2, 'X')
                        first_name = ' '.join(words[:-2]) if len(words) > 2 else "Unknown"
                        if not first_name or not first_name.strip():
                            first_name = "Unknown"
                        return f"{first_name} {padded_last}"
            else:
                padded_last = last_word.ljust(2, 'X')
                return f"{last_word} {padded_last}"
        
        # Name is valid
        return ' '.join(words)


def validate_and_fix_json_file(input_path: str, output_path: Optional[str] = None) -> Tuple[Dict, List[str], List[str]]:
    """
    Validate and fix JSON file format issues
    
    Args:
        input_path: Path to input JSON file
        output_path: Optional path to save fixed JSON (if None, overwrites input)
    
    Returns:
        Tuple of (fixed_data, issues_found, fixes_applied)
    """
    # Read JSON file
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Validate and fix
    validator = PropertyJSONFormatValidator()
    fixed_data, issues, fixes = validator.validate_and_fix(data)
    
    # Save fixed JSON
    save_path = output_path or input_path
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(fixed_data, f, ensure_ascii=False, indent=2)
    
    return fixed_data, issues, fixes


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python json_format_validator.py <input_json_file> [output_json_file]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"Validating and fixing: {input_file}")
    fixed_data, issues, fixes = validate_and_fix_json_file(input_file, output_file)
    
    print(f"\n{'='*60}")
    print(f"Issues Found: {len(issues)}")
    print(f"{'='*60}")
    for issue in issues:
        print(f"  - {issue}")
    
    print(f"\n{'='*60}")
    print(f"Fixes Applied: {len(fixes)}")
    print(f"{'='*60}")
    for fix in fixes:
        print(f"  ✓ {fix}")
    
    output_path = output_file or input_file
    print(f"\nFixed JSON saved to: {output_path}")

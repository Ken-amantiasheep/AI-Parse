def build_rules(is_caa_company: bool):
    if is_caa_company:
        date_rule = "- For CAA, only date_of_birth fields must be MM/DD/YYYY. Do not force-convert other date fields."
        caa_claim_policy_rule = """- For CAA claims, each claims item must include non-empty policy (Claim# / Policy#).
- Claim policy must be extracted from Autoplus claims section (the claim block that contains Loss Date / Company / Source / Policy).
- For every individual claim item, copy the Policy value from the same claim block into claim.policy (or claim_number if only Claim# is present).
- Do NOT leave claim.policy empty when Policy/Claim number exists in Autoplus text.
- If Policy is not printed in that claim block, try Claim# in the same block; if both are missing, then fallback to a global policy number.
- If Autoplus/dash documents are missing (not provided), treat this as no insurance history record for that driver and do NOT fabricate policy/claim history from missing sources."""
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
        date_rule = "- All dates must be in YYYY-MM-DD format"
        caa_claim_policy_rule = ""
        caa_membership_rule = ""

    return date_rule, caa_claim_policy_rule, caa_membership_rule


def build_critical_extraction_block(date_rule: str, caa_claim_policy_rule: str, caa_membership_rule: str) -> str:
    return f"""

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
✅ **CORRECT**: Finding header "km at Purchase", looking directly below it, seeing it's blank, so km_at_purchase = 0

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
   - Result: `km_at_purchase = 0` ✅ (required field: if blank, must use 0, never null)

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

## ⚠️ CRITICAL: business_km and primary_use Logic Rule ⚠️

**business_km can ONLY have a value when primary_use is 'Business'.**

- If primary_use is "Pleasure" → business_km MUST be empty string "" (NEVER assign a number!)
- If primary_use is "Commute" → business_km MUST be empty string ""
- If primary_use is "Farm Use" → business_km MUST be empty string ""
- If primary_use is "Business" → business_km MAY have a value (extract from the Business km column)

**COMMON MISTAKE TO AVOID (business_km vs daily_km):**

The table typically shows: Annual km | Business km | Daily km
When primary_use is "Pleasure", the "Business km" cell is usually BLANK, and a number you see nearby likely belongs to "Daily km"!

❌ **WRONG**: primary_use = "Pleasure", annual_km = "10352", business_km = "10", daily_km = ""
   - "10" is under "Daily km" header, NOT "Business km"! And even if it were, business_km must be empty when primary_use is Pleasure!

✅ **CORRECT**: primary_use = "Pleasure", annual_km = "10352", business_km = "", daily_km = "10"
   - "10" is correctly read from the "Daily km" column
   - business_km is empty because primary_use is "Pleasure"

**OTHER COMMON MISTAKE TO AVOID:**

❌ **WRONG**: "I see '4' after 'Daily km' header, so daily_km = '4'"
   - But actually "4" is under "Cylinders" header, not "Daily km"!
   - If "Daily km" column is blank → daily_km MUST be null/empty!

✅ **CORRECT**: 
   - Find header "Daily km" → Look directly below it → See BLANK → daily_km = null
   - Find header "Cylinders" → Look directly below it → See "4" → cylinders = "4"

**CONCRETE EXAMPLE 1 (Pleasure use):**

Table structure:
```
Row 1 (values):    10352    (blank)    10         ETOBICOKE M9W5X7    No    No    4
Row 2 (headers):   Annual   Business   Daily      Garaging           Single Leased Cylinders
                   km       km         km          Location            Vehicle MVD
```
primary_use = "Pleasure"

**CORRECT EXTRACTION:**
- annual_km = "10352" (under "Annual km" header) ✅
- business_km = "" (MUST be empty because primary_use is "Pleasure") ✅
- daily_km = "10" (under "Daily km" header) ✅

**CONCRETE EXAMPLE 2 (all blank km):**

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
- **business_km MUST be empty when primary_use is NOT "Business"** - this is a hard rule, not a suggestion!
- **Single-digit or two-digit values under "Daily km" are valid** (e.g. 8 or 10 km/day). Do not treat them as errors or leave daily_km empty when the quote shows a number under the Daily km header.

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
- `km_at_purchase` is required: if its column is blank, output `0` (never null)
- For other purchase fields, if a column is blank, that field = null (DO NOT borrow from next column!)
- "29705" under "List Price New" header → list_price_new = "29705"
- "29705" NOT under "km at Purchase" header → km_at_purchase = 0 (even if you see "29705" nearby!)

**DO NOT READ LEFT-TO-RIGHT! MATCH BY HEADER NAME!**

## ⚠️ FINAL OUTPUT VALIDATION - CHECK THIS BEFORE RETURNING JSON ⚠️

**MANDATORY CHECK FOR business_km vs primary_use:**

For EACH vehicle, verify:
- If primary_use is "Pleasure", "Commute", or "Farm Use" → business_km MUST be "" (empty) or null
- If business_km has a non-empty value but primary_use is NOT "Business" → ⚠️ INVALID! Fix it by clearing business_km
- Double-check that daily_km was not accidentally assigned to business_km

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

def build_prompt_intro(company: str) -> str:
    return f"""You are a professional insurance data extraction expert. Your task is to extract information from the provided documents and generate JSON data that meets the requirements for uploading to the {company} insurance system.

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

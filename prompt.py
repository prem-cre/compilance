# --- PROMPT TEMPLATES ---

Extract_rules_prompt = """
You are a Senior Legal Compliance Architect.

You are given an uploaded Policy Document via the file search store.
Your job is to extract ONLY the rules that are explicitly written in that document.

CRITICAL PRINCIPLES:
- Treat the Policy Document as the ONLY source of rules.
- Do NOT assume or import generic GDPR, privacy, or compliance rules unless the document itself cites them and converts them into concrete instructions.
- If the document is about Court Filings, remember that names are often REQUIRED; do not hallucinate masking/anonymisation rules unless they are explicitly written.
- If the document does NOT mention a specific restriction or requirement, you MUST write exactly: "None explicitly stated." for that item.

Extract STRICT rules under these headings:

1. Data Privacy / PII
   - Does the document EXPLICITLY require masking, redacting, pseudonymising, or omitting: names, dates, addresses, phone numbers, email addresses, identification numbers, or other PII?
   - Does the document EXPLICITLY require FULL disclosure of real names or other identifiers?
   - For each explicit rule, quote or closely paraphrase the relevant sentence.
   - If NO explicit rule is given for any of these, output a single line: "None explicitly stated."

2. Citation Style
   - Note any explicit rule about citation or reference style (e.g., Bluebook, OSCOLA, in-house style, footnotes vs endnotes, etc.).
   - If there is NO explicit guidance, write: "None explicitly stated."

3. Document Structure & Formatting
   - List any REQUIRED headings or sections (e.g., "IN THE HIGH COURT", "Abstract", "References", case title formats, etc.).
   - List any explicit formatting requirements: fonts, sizes, margins, spacing, alignment, paragraph numbering style, page limits, etc.
   - If an aspect is not mentioned at all, write: "None explicitly stated."

4. Restricted/Required Phrasing (Governance)
   - List any specific disclaimers, formulas, or standard phrases that MUST appear.
   - List any words or expressions that are explicitly FORBIDDEN.
   - If nothing is specified, write: "None explicitly stated."

OUTPUT FORMAT:
- Provide a clean, human-readable structured list with the four headings above.
- Under each heading, use bullet points.
- Under any heading with no explicit rules, include exactly one bullet: "None explicitly stated."
- Base everything ONLY on the text of the Policy Document - extract any kind of rules, policies, regulations.
"""

verify_compliance_system_instruction = """
You are a Mechanical Compliance Engine. You verify text against a JSON rule set.
Your job is to compare 'USER CONTENT' vs 'JSON RULES' and report discrepancies.
"""


def get_verify_compliance_prompt(rules: str, user_input: str) -> str:
    """
    Returns the verification prompt with rules and user input filled in.
    
    Args:
        rules: The extracted JSON rules from the policy document
        user_input: The user's content to check for compliance
        
    Returns:
        Formatted prompt string
    """
    return f"""
--- STEP 1: READ THE RULES ---
{rules}

The RULES above are a JSON object with four arrays: data_privacy_pii, citation_style, structure_formatting, phrasing_governance.
Treat this JSON as the COMPLETE and ONLY rule source.

--- STEP 2: READ THE USER CONTENT ---
{user_input}

CRITICAL OVERRIDES:
1. IGNORE TRUTH
   - Do not flag impossible dates or factual errors unless a specific rule in the JSON clearly regulates factual correctness.

2. IGNORE LOGIC
   - Do not flag contradictions or inconsistencies unless a specific rule demands internal consistency.

3. CONTEXTUAL PII
   - Look in data_privacy_pii rules for explicit masking / redaction / disclosure requirements.
   - If such a rule exists (e.g., mask names), then any unmasked PII in USER CONTENT that conflicts with that rule is a violation.
   - If data_privacy_pii contains only "None explicitly stated." or has no masking instruction, then all PII in USER CONTENT is compliant by default.

CHECKLIST USAGE (ONLY IF MATCHED BY RULES):
Use this list ONLY to search for relevant rules in the JSON; do NOT treat it as rules itself:
1. Structure: headings and sections.
2. Formatting: fonts, spacing, margins, numbering.
3. Privacy: PII redaction or disclosure.
4. Citations: style and completeness.
5. Consistency: acronyms, units, numbering.
6. Content Integrity: figures/tables, plagiarism aspects.
7. Accessibility: alt text, headings.
8. Legal/Ethical: copyright, disclaimers, conflicts.
9. Technical Quality: equations, graphics, file format.
10. Submission Requirements: page limits, abstracts, forms.

--- STEP 3: GENERATE REPORT ---
Compare USER CONTENT against the JSON RULES. A violation exists only when:
- A specific rule_text in the JSON applies; AND
- Some span of USER CONTENT conflicts with that rule.

OUTPUT STRICT JSON SCHEMA:
{{
  "is_compliant": boolean,
  "overallScore": float(1-100),
  "detectionConfidence": "LOW", "MEDIUM", or "HIGH",
  "totalViolations": int,
  "violations": [
    {{
      "rule_category": string,          
      "rule_reference": string,         
      "violation_text": string,         
      "correction_suggestion": string,  
      "severity": string                
    }}
  ]
}}

If there are no violations, return:
{{
  "is_compliant": true,
  "overallScore": 100,
  "detectionConfidence": "HIGH",
  "totalViolations": 0,
  "violations": []
}}
"""

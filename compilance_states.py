# --- IMPORTS ---
import os
from typing import TypedDict, Optional, List
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Initialize client for retry function
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# --- 1. DEFINE STATE & SCHEMA ---

class ComplianceViolation(BaseModel):
    rule_category: str
    violation_text: str
    correction_suggestion: str
    severity: str

class ComplianceReport(BaseModel):
    is_compliant: bool
    overallScore: float
    detectionConfidence: str
    totalViolations: int
    violations: List[ComplianceViolation]

class ComplianceState(TypedDict):
    user_id: str
    user_content: str
    file_path: Optional[str]  # Local file path for user's rules PDF
    store_name: Optional[str]
    metadata_filter: Optional[str]
    file_to_cleanup: Optional[str]
    mode: Optional[str]
    extracted_rules: Optional[str]
    compliance_report: str
    errors: List[str]


# --- 2. RETRY LOGIC ---
@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=2, min=2, max=20),
    retry=retry_if_exception_type(Exception)
)
def call_gemini_with_retry(model, contents, config):
    return client.models.generate_content(
        model=model,
        contents=contents,
        config=config
    )

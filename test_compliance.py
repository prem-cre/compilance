"""
Test file for Compliance Engine
Tests the user-upload flow with local file paths
"""
import warnings
warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality")

import json
import time
from pathlib import Path

# Import from local modules
from compliance import (
    upload_user_rules,
    check_compliance,
    check_compliance_with_uploaded_rules,
    delete_user_rules
)

# ============================================================================
# TEST CONFIGURATION
# ============================================================================

# Path to the rules PDF (local file)
RULES_PDF_PATH = str(Path(__file__).parent / "standard_compliance_rules.pdf")

# Test identifiers
TEST_USER_ID = "test_user_123"
TEST_FILE_ID = f"test_file_{int(time.time())}"

# Test document with potential violations
TEST_DRAFT_WITH_VIOLATIONS = """
PETITION FOR BAIL
Case Title: State vs. Arjun Mehra

I am writing this petition for Arjun Mehra, son of Sunil Mehra, resident of Flat 202, Sunshine Apartments, Bandra, Mumbai 400050. 

Regarding the incident: The police allege that the robbery took place on 31 June 2024. However, the accused was already in custody since his arrest on 30 Feb 2024. These dates prove the police records are forged.

Evidence Review: I have personally reviewed the CCTV footage from the bank. In the video, a person who looks nothing like the accused enters the vault and takes the cash. This verbal description of the video should be sufficient for the court to grant bail immediately without seeing the original files.

THE PROSECUTION IS COMPOSED OF IDIOTS AND LIARS. THEY ARE TRYING TO FRAME AN INNOCENT MAN. THIS COURT MUST STOP THIS FILTHY BEHAVIOR AND RELEASE THE ACCUSED IMMEDIATELY BEFORE JUSTICE IS COMPLETELY DESTROYED.

Medical Background: Dr. Rajesh Khanna from Global Hospital has diagnosed Arjun with Bipolar Disorder. He takes heavy medication and cannot be held responsible for his actions.

Contact Info: You can email the family at arjun.mehra@gmail.com or call 9820098200. His Aadhaar ID is 5566-7788-9900 for your records.

The incident occurred at exactly 02:45 PM.

Submitted by:
Advocate Karan Malhotra
Phone: 9123456789
"""


# ============================================================================
# TEST FUNCTIONS
# ============================================================================

def test_simple_compliance_check():
    """
    Simple test: Upload rules and check compliance in one call
    """
    print("\n" + "="*70)
    print("[TEST] SIMPLE COMPLIANCE CHECK (Upload + Check in one call)")
    print("="*70)
    
    print(f"\n[INFO] Using rules PDF: {RULES_PDF_PATH}")
    print(f"[INFO] User ID: {TEST_USER_ID}")
    
    # Single call that uploads and checks
    print("\n[STEP 1] Running compliance check...")
    result = check_compliance(
        user_id=TEST_USER_ID,
        file_path=RULES_PDF_PATH,
        draft_text=TEST_DRAFT_WITH_VIOLATIONS,
        cleanup_after=True  # Auto-cleanup after check
    )
    
    print(f"\n[RESULT]:")
    print(json.dumps(result, indent=2))
    
    if result.get("status") == "success":
        report = result.get("report", {})
        print(f"\n[SUMMARY]")
        print(f"  Is Compliant: {report.get('is_compliant')}")
        print(f"  Overall Score: {report.get('overallScore')}")
        print(f"  Total Violations: {report.get('totalViolations')}")
        print(f"  Confidence: {report.get('detectionConfidence')}")
        
        if report.get('violations'):
            print(f"\n[VIOLATIONS FOUND]:")
            for i, v in enumerate(report['violations'], 1):
                print(f"\n  {i}. {v.get('rule_category', 'Unknown')}")
                print(f"     Violation: {v.get('violation_text', 'N/A')[:100]}...")
                print(f"     Suggestion: {v.get('correction_suggestion', 'N/A')[:100]}...")
                print(f"     Severity: {v.get('severity', 'N/A')}")
    
    print("\n[DONE] Simple compliance check completed!")
    return result


def test_upload_then_check():
    """
    Two-step test: Upload rules first, then check compliance separately
    """
    print("\n" + "="*70)
    print("[TEST] TWO-STEP FLOW (Upload first, then Check)")
    print("="*70)
    
    file_id = f"two_step_{int(time.time())}"
    
    # Step 1: Upload rules
    print(f"\n[STEP 1] Uploading rules PDF...")
    upload_result = upload_user_rules(
        file_path=RULES_PDF_PATH,
        user_id=TEST_USER_ID,
        file_id=file_id
    )
    print(f"Upload Result: {json.dumps(upload_result, indent=2)}")
    
    if upload_result.get("status") != "success":
        print("[ERROR] Upload failed!")
        return
    
    # Step 2: Check compliance with previously uploaded rules
    print("\n[STEP 2] Checking compliance with uploaded rules...")
    check_result = check_compliance_with_uploaded_rules(
        user_id=TEST_USER_ID,
        file_id=file_id,
        draft_text=TEST_DRAFT_WITH_VIOLATIONS,
        cleanup_after=False  # Don't cleanup yet
    )
    print(f"Check Result: {json.dumps(check_result, indent=2)}")
    
    # Step 3: Manual cleanup
    print("\n[STEP 3] Cleaning up uploaded rules...")
    delete_result = delete_user_rules(TEST_USER_ID, file_id)
    print(f"Delete Result: {json.dumps(delete_result, indent=2)}")
    
    print("\n[DONE] Two-step flow completed!")
    return check_result


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("COMPLIANCE ENGINE TEST SUITE")
    print("="*70)
    print(f"Rules PDF: {RULES_PDF_PATH}")
    print(f"PDF exists: {Path(RULES_PDF_PATH).exists()}")
    
    # Run simple test
    test_simple_compliance_check()
    
    # Uncomment to also run the two-step test:
    # test_upload_then_check()

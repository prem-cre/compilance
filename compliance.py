import warnings
warnings.filterwarnings("ignore", message="Core Pydantic V1 functionality")

import os
import time
import json

from typing import Optional, Dict, Any
from google import genai
from google.genai import types
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

load_dotenv()


# --- IMPORTS ---
from compliance_file_store import ComplianceFileStoreManager
from compilance_states import ComplianceViolation, ComplianceReport, ComplianceState, call_gemini_with_retry
from prompt import Extract_rules_prompt, verify_compliance_system_instruction, get_verify_compliance_prompt

# --- INITIALIZE ---
file_store_manager = ComplianceFileStoreManager()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL_ID = os.getenv("MODEL_ID")


# --- LANGGRAPH NODES ---

def node_setup_context(state: ComplianceState):
    """
    DECISION NODE: Sets up context for user's uploaded rules.
    User must upload their rules PDF - no admin fallback.
    """
    user_id = state.get('user_id')
    file_path = state.get('file_path')  # Local file path
    
    if not user_id:
        return {"errors": state.get('errors', []) + ["Missing user_id"]}
    
    if not file_path:
        return {"errors": state.get('errors', []) + ["Missing file_path - user must upload a rules PDF"]}
    
    # Check if context already set up
    if state.get("store_name") and state.get("mode") == "custom":
        print(f"[CONTEXT] Using existing context - Store: {state['store_name']}")
        return {
            "store_name": state["store_name"],
            "metadata_filter": state.get("metadata_filter"),
            "file_to_cleanup": state.get("file_to_cleanup"),
            "mode": state["mode"]
        }

    try:
        # Generate file_id from timestamp
        file_id = f"user_{user_id}_{int(time.time())}"
        
        # Upload user's rules document
        upload_result = file_store_manager.upload_user_document(
            file_path=file_path,
            user_id=user_id,
            file_id=file_id
        )
        
        if upload_result.get("status") != "success":
            return {"errors": state.get('errors', []) + [upload_result.get("message", "Upload failed")]}
        
        print(f"[CONTEXT] Mode: custom, Store: {upload_result['store_name']}")
        
        return {
            "store_name": upload_result["store_name"],
            "metadata_filter": f'user_id = "{user_id}" AND file_id = "{file_id}"',
            "file_to_cleanup": upload_result.get("google_file_name"),
            "mode": "custom"
        }
        
    except Exception as e:
        print(f"[CONTEXT] Setup failed: {e}")
        return {"errors": state.get('errors', []) + [f"Context setup failed: {str(e)}"]}


def node_extract_rules(state: ComplianceState):
    """
    Extracts compliance rules from the user's uploaded document.
    """
    if not state.get("store_name"):
        return {"extracted_rules": "ERROR: No store configured."}

    print(f"[EXTRACT] Extracting rules from user document...")

    try:
        # Build file search tool with metadata filter
        file_search_tool = types.Tool(
            file_search=types.FileSearch(
                file_search_store_names=[state['store_name']],
                metadata_filter=state.get('metadata_filter')
            )
        )

        response = call_gemini_with_retry(
            model=MODEL_ID,
            contents=Extract_rules_prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                tools=[file_search_tool]
            )
        )

        print(f"[EXTRACT] Successfully extracted rules")
        return {"extracted_rules": response.text}

    except Exception as e:
        print(f"[EXTRACT] Failed: {e}")
        return {"extracted_rules": f"Error: {str(e)}", "errors": state.get('errors', []) + [str(e)]}


def node_verify_compliance(state: ComplianceState):
    """
    Verifies user content against extracted rules.
    """
    rules = state.get('extracted_rules', "")
    if "ERROR" in rules or not rules:
        return {"compliance_report": '{"error": "SKIPPED: Rules could not be extracted."}'}

    user_input = state['user_content']

    try:
        # Get the formatted prompt with rules and user input
        verify_prompt = get_verify_compliance_prompt(rules, user_input)
        
        response = call_gemini_with_retry(
            model=MODEL_ID,
            contents=verify_prompt,
            config=types.GenerateContentConfig(
                system_instruction=verify_compliance_system_instruction,
                temperature=0.3,
                response_mime_type="application/json",
                response_schema=ComplianceReport
            )
        )
        
        print(f"[VERIFY] Compliance check completed")
        return {"compliance_report": response.text}

    except Exception as e:
        print(f"[VERIFY] Failed: {e}")
        return {"errors": state.get('errors', []) + [f"Verification failed: {str(e)}"]}


def node_cleanup(state: ComplianceState):
    """
    Cleans up user-uploaded files after compliance check.
    """
    file_to_cleanup = state.get('file_to_cleanup')
    
    if file_to_cleanup:
        try:
            client.files.delete(name=file_to_cleanup)
            print(f"[CLEANUP] Deleted temporary file: {file_to_cleanup}")
        except Exception as e:
            print(f"[CLEANUP] Failed to delete file: {e}")
    else:
        print(f"[CLEANUP] No file to cleanup")
    
    return {}


# --- BUILD GRAPH ---
workflow = StateGraph(ComplianceState)
workflow.add_node("setup", node_setup_context)
workflow.add_node("extract", node_extract_rules)
workflow.add_node("verify", node_verify_compliance)
workflow.add_node("cleanup", node_cleanup)

workflow.set_entry_point("setup")
workflow.add_edge("setup", "extract")
workflow.add_edge("extract", "verify")
workflow.add_edge("verify", "cleanup")
workflow.add_edge("cleanup", END)

compliance_app = workflow.compile()


# =============================================================================
# PUBLIC API FUNCTIONS
# =============================================================================

def upload_user_rules(file_path: str, user_id: str, file_id: str) -> Dict[str, Any]:
    """
    PUBLIC API: Called when user uploads their custom rules PDF.
    Pre-indexes the document for faster compliance checking later.
    
    Args:
        file_path: Local path to the PDF file
        user_id: User identifier
        file_id: Unique file identifier
        
    Returns:
        Upload result with status
    """
    print(f"[API] Upload user rules - user: {user_id}, file: {file_id}")
    return file_store_manager.upload_user_document(file_path, user_id, file_id)


def check_compliance(
    user_id: str, 
    file_path: str, 
    draft_text: str,
    cleanup_after: bool = True
) -> Dict[str, Any]:
    """
    PUBLIC API: Check compliance of draft text against user's rules PDF.
    
    Args:
        user_id: User identifier
        file_path: Local path to the rules PDF
        draft_text: Text to check for compliance
        cleanup_after: Whether to delete the uploaded rules after check (default: True)
        
    Returns:
        Compliance report
    """
    print(f"[API] Check compliance - user: {user_id}, file: {file_path}")
    
    # Run compliance check
    final_state = compliance_app.invoke({
        "user_id": user_id,
        "user_content": draft_text,
        "file_path": file_path,
        "errors": []
    })
    
    return _parse_result(final_state)


def check_compliance_with_uploaded_rules(
    user_id: str, 
    file_id: str, 
    draft_text: str,
    cleanup_after: bool = False
) -> Dict[str, Any]:
    """
    PUBLIC API: Check compliance against user's previously uploaded rules.
    
    Args:
        user_id: User identifier
        file_id: File identifier of uploaded rules
        draft_text: Text to check for compliance
        cleanup_after: Whether to delete the uploaded rules after check
        
    Returns:
        Compliance report
    """
    print(f"[API] Check with pre-uploaded rules - user: {user_id}, file: {file_id}")
    
    # Get context for the pre-uploaded file
    context = file_store_manager.get_user_context(user_id, file_id)
    
    # Run compliance check
    final_state = compliance_app.invoke({
        "user_id": user_id,
        "user_content": draft_text,
        "file_path": None,  # Already uploaded
        "store_name": context["store_name"],
        "metadata_filter": context["metadata_filter"],
        "file_to_cleanup": None,  # Don't auto-cleanup
        "mode": "custom",
        "errors": []
    })
    
    # Optional cleanup
    if cleanup_after:
        file_store_manager.cleanup_user_file(user_id, file_id)
    
    return _parse_result(final_state)


def delete_user_rules(user_id: str, file_id: str) -> Dict[str, Any]:
    """
    PUBLIC API: Delete previously uploaded user rules.
    
    Args:
        user_id: User identifier
        file_id: File identifier
        
    Returns:
        Deletion result
    """
    print(f"[API] Delete user rules - user: {user_id}, file: {file_id}")
    return file_store_manager.cleanup_user_file(user_id, file_id)


# --- HELPER ---
def _parse_result(final_state: dict) -> Dict[str, Any]:
    """Parses the final state into a clean result."""
    if final_state.get("errors"):
        return {
            "status": "failed",
            "errors": final_state["errors"]
        }
    
    if "compliance_report" in final_state:
        try:
            report = json.loads(final_state["compliance_report"])
            return {
                "status": "success",
                "report": report
            }
        except json.JSONDecodeError:
            return {
                "status": "error",
                "message": "Model returned invalid JSON",
                "raw_output": final_state["compliance_report"]
            }
    
    return {"status": "unknown_error"}

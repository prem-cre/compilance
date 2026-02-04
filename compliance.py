import os
import time
import json

from typing import TypedDict, Optional, List, Dict, Any
from google import genai
from google.genai import types
from langgraph.graph import StateGraph, END
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pydantic import BaseModel
from dotenv import load_dotenv
load_dotenv()

#intializing this i need to check after integ(toodo)
file_store_manager = ComplianceFileStoreManager()



client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
MODEL_ID = os.getenv("MODEL_ID")

# --- 1. DEFINE STATE & SCHEMA And Retry LOGIC ---
from compilance_states import ComplianceViolation, ComplianceReport, ComplianceState, call_gemini_with_retry

# prompt setup
from prompt import Extract_rules_prompt,verify_compilance_system_instruction,verify_compilance_user_prompt

# --- 2. LANGGRAPH NODES ---

def node_setup_context(state: ComplianceState):
    """
    DECISION NODE: Determines whether to use User rules or Admin rules.
    """
    user_id = state.get('user_id')
    s3_key = state.get('s3_key')  # Can be None
    file_id = state.get('file_id')
    
    if not user_id:
        return {"errors": state.get('errors', []) + ["Missing user_id"]}
    
    if state.get("store_name") and state.get("mode") == "custom":
        logger.info(f"[CONTEXT] Using existing context - Mode: {state['mode']}, Store: {state['store_name']}")
        return {
            "store_name": state["store_name"],
            "metadata_filter": state.get("metadata_filter"),
            "file_to_cleanup": state.get("file_to_cleanup"),
            "mode": state["mode"]
        }

    try:
        # THE MAGIC: prepare_compliance_context handles the if/else logic
        context = file_store_manager.prepare_compliance_context(
            user_id=user_id,
            s3_key=s3_key,
            file_id=file_id
        )
        
        logger.info(f"[CONTEXT] Mode: {context['mode']}, Store: {context['store_name']}")
        
        return {
            "store_name": context["store_name"],
            "metadata_filter": context["metadata_filter"],
            "file_to_cleanup": context.get("file_to_cleanup"),
            "mode": context["mode"]
        }
        
    except Exception as e:
        logger.error(f"[CONTEXT] Setup failed: {e}")
        return {"errors": state.get('errors', []) + [f"Context setup failed: {str(e)}"]}


def node_extract_rules(state: ComplianceState):
    """
    Extracts compliance rules from the document
    """
    if not state.get("store_name"):
        return {"extracted_rules": "ERROR: No store configured."}

    mode = state.get('mode', 'unknown')
    print(f"[EXTRACT] Extracting rules from {mode} document...")


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

        print(f"[EXTRACT] Successfully extracted rules ({mode} mode)")
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
    mode = state.get('mode', 'unknown')

    try:
        response = call_gemini_with_retry(
            model=MODEL_ID,
            contents=verify_compilance_user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=verify_compilance_system_instruction,
                temperature=0.3,
                response_mime_type="application/json",
                response_schema=ComplianceReport
            )
        )
        
        print(f"[VERIFY] Compliance check completed ({mode} mode)")
        return {"compliance_report": response.text}

    except Exception as e:
        print(f"[VERIFY] Failed: {e}")
        return {"errors": state.get('errors', []) + [f"Verification failed: {str(e)}"]}


def node_cleanup(state: ComplianceState):
    """
    Cleans up user-uploaded files. Does NOT delete admin files.
    """
    file_to_cleanup = state.get('file_to_cleanup')
    mode = state.get('mode')
    
    if file_to_cleanup and mode == "custom":
        
        client.files.delete(name=file_to_cleanup)
            
        
    else:
        print(f"[CLEANUP] Skipped - mode: {mode}, no cleanup needed")
    
    return {}


# --- 4. BUILD GRAPH ---
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

def upload_user_rules(s3_key: str, user_id: str, file_id: str) -> Dict[str, Any]:
    """
    PUBLIC API: Called when user uploads their custom rules PDF.
    Pre-indexes the document for faster compliance checking later.
    
    Args:
        s3_key: S3 object key of uploaded PDF
        user_id: User identifier
        file_id: Unique file identifier
        
    Returns:
        Upload result with status
    """
    logger.info(f"[API] Upload user rules - user: {user_id}, file: {file_id}")
    return file_store_manager.upload_user_document(s3_key, user_id, file_id)


def check_compliance_with_user_rules(
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
    logger.info(f"[API] Check with USER rules - user: {user_id}, file: {file_id}")
    
    # Get context for the pre-uploaded file
    context = file_store_manager.get_user_context(user_id, file_id)
    
    # Run compliance check
    final_state = compliance_app.invoke({
        "user_id": user_id,
        "user_content": draft_text,
        "s3_key": None,  # Already uploaded
        "file_id": file_id,
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


def check_compliance_with_admin_rules(user_id: str, draft_text: str) -> Dict[str, Any]:
    """
    PUBLIC API: Check compliance against default ADMIN standard rules.
    Used when user doesn't upload custom rules.
    
    Args:
        user_id: User identifier (for logging)
        draft_text: Text to check for compliance
        
    Returns:
        Compliance report
    """
    logger.info(f"[API] Check with ADMIN rules - user: {user_id}")
    
    # Run with no s3_key = fallback to admin rules
    final_state = compliance_app.invoke({
        "user_id": user_id,
        "user_content": draft_text,
        "s3_key": None,
        "file_id": None,
        "errors": []
    })
    
    return _parse_result(final_state)


def check_compliance_auto(
    user_id: str, 
    draft_text: str, 
    s3_key: Optional[str] = None,
    file_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    PUBLIC API: Smart compliance check that auto-detects which rules to use.
    
    - If s3_key provided -> Upload and use user's custom rules
    - If s3_key is None -> Use admin standard rules
    
    Args:
        user_id: User identifier
        draft_text: Text to check
        s3_key: Optional S3 key of custom rules PDF
        file_id: Optional file identifier
        
    Returns:
        Compliance report with mode indicator
    """
    logger.info(f"[API] Auto compliance check - user: {user_id}, has_custom: {bool(s3_key)}")
    
    final_state = compliance_app.invoke({
        "user_id": user_id,
        "user_content": draft_text,
        "s3_key": s3_key,
        "file_id": file_id or f"auto_{int(time.time())}",
        "errors": []
    })
    
    result = _parse_result(final_state)
    result["mode"] = final_state.get("mode", "unknown")
    return result


def delete_user_rules(user_id: str, file_id: str) -> Dict[str, Any]:
    """
    PUBLIC API: Delete previously uploaded user rules.
    
    Args:
        user_id: User identifier
        file_id: File identifier
        
    Returns:
        Deletion result
    """
    logger.info(f"[API] Delete user rules - user: {user_id}, file: {file_id}")
    return file_store_manager.cleanup_user_file(user_id, file_id)




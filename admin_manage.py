import os
import sys
import json
from pathlib import Path
from google import genai
from dotenv import load_dotenv

# --- SETUP ---
load_dotenv(Path(__file__).resolve().parent.parent.parent.parent / '.env')
sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))

from app.config.settings import settings

# Initialize Gemini Client
client = genai.Client(api_key=settings.GOOGLE_API_KEY)
ADMIN_STORE_NAME = "Lawvriksh_Admin_Standards_v1"

def find_admin_store():
    """Finds the store resource name based on the display name."""
    print(f"🔍 Searching for store: '{ADMIN_STORE_NAME}'...")
    for store in client.file_search_stores.list():
        if store.display_name == ADMIN_STORE_NAME:
            return store.name
    return None

def list_admin_files():
    """Lists all document entries currently indexed in the Store."""
    store_id = find_admin_store()
    if not store_id:
        print(f"❌ Store '{ADMIN_STORE_NAME}' does not exist.")
        return

    print(f"✅ Found Store: {store_id}")
    print("-" * 60)
    
    # List documents using the documents.list method
    docs = list(client.file_search_stores.documents.list(parent=store_id))
    
    if not docs:
        print("📭 The store is empty (No documents indexed).")
    else:
        print(f"📄 Found {len(docs)} document entry(s):")
        for i, doc in enumerate(docs, 1):
            print(f"\n[{i}] Document ID: {doc.name}")
            if hasattr(doc, 'custom_metadata') and doc.custom_metadata:
                print("    Metadata:")
                for m in doc.custom_metadata:
                    val = m.string_value if hasattr(m, 'string_value') else m.numeric_value
                    print(f"      - {m.key}: {val}")

def clear_all_documents():
    """
    Cleans the store properly.
    1. Deletes the Document entry from the File Search Store.
    2. Deletes the underlying File Resource from Gemini.
    """
    store_id = find_admin_store()
    if not store_id:
        print("❌ Store not found. Nothing to clear.")
        return

    docs = list(client.file_search_stores.documents.list(parent=store_id))
    if not docs:
        print("ℹ️ Store is already empty.")
        return

    print(f"⚠️  WARNING: You are about to delete {len(docs)} documents from the store.")
    confirm = input("Type 'yes' to confirm: ")
    
    if confirm.lower() == 'yes':
        for doc in docs:
            try:
                # 1. Try to delete the underlying File Resource first (if metadata exists)
                file_to_del = None
                if hasattr(doc, 'custom_metadata'):
                    for m in doc.custom_metadata:
                        if m.key == 'google_file_name':
                            file_to_del = m.string_value
                
                if file_to_del:
                    try:
                        client.files.delete(name=file_to_del)
                        print(f"🗑️  Deleted File binary: {file_to_del}")
                    except Exception:
                        print(f"ℹ️  Binary {file_to_del} already gone or inaccessible.")

                # 2. MANDATORY: Delete the Document Reference from the Store
                # This is what removes it from the 'list' results.
                client.file_search_stores.documents.delete(name=doc.name)
                print(f"🧹 Removed Document Entry: {doc.name}")
            
            except Exception as e:
                print(f"❌ Failed to remove {doc.name}: {e}")
        print("\n✅ Finished clearing store.")
    else:
        print("❌ Operation cancelled.")

def delete_entire_store():
    """Permanent deletion of the entire Store container and all its embeddings."""
    store_id = find_admin_store()
    if not store_id:
        print("❌ Store not found.")
        return

    print(f"🚨 DANGER: You are about to delete the ENTIRE Store: {store_id}")
    print("This will destroy all embeddings indefinitely.")
    confirm = input("Type 'DELETE STORE' to confirm: ")

    if confirm == "DELETE STORE":
        try:
            client.file_search_stores.delete(name=store_id, config={'force': True})
            print(f"💥 Store '{ADMIN_STORE_NAME}' has been wiped from existence.")
        except Exception as e:
            print(f"❌ Error deleting store: {e}")
    else:
        print("❌ Operation cancelled.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("""
Admin Store Manager CLI
-----------------------
Usage:
    python app/services/compilance_check/admin_manage.py list     # List all indexed docs
    python app/services/compilance_check/admin_manage.py clear    # Wipe docs but keep store
    python app/services/compilance_check/admin_manage.py delete   # Nuke the entire store
        """)
    else:
        command = sys.argv[1].lower()
        if command == "list":
            list_admin_files()
        elif command == "clear":
            clear_all_documents()
        elif command == "delete":
            delete_entire_store()
        else:
            print("❌ Invalid command.")
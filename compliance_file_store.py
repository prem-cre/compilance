"""
Compliance File Store Manager

Manages Google File Search Stores for Compliance service.
Handles user uploads only - users must upload their own rules PDF.
"""
from __future__ import annotations

import os
import time
import tempfile
from typing import Optional, Dict, Any

from google import genai
from dotenv import load_dotenv

load_dotenv()


class ComplianceFileStoreManager:
    """
    Manages Google File Search Stores for compliance checking.
    Users must upload their own rules PDF via local file path.
    """

    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

        # --- STORE CONFIGURATION ---
        self.USER_STORE_NAME = "Compliance_User_Uploads_v1"
        
        # Cache store ID
        self._user_store_id = None

        print("[FileStoreManager] Initialized ComplianceFileStoreManager")

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def upload_user_document(
        self,
        file_path: str,
        user_id: str,
        file_id: str
    ) -> Dict[str, Any]:
        """
        Uploads a user's custom rules document to the User Store.
        Called when user uploads a PDF (before clicking compliance check).

        Args:
            file_path: Local path to the PDF file
            user_id: User identifier
            file_id: Unique file identifier

        Returns:
            Upload result with status and metadata
        """
        try:
            # Validate file exists
            if not os.path.exists(file_path):
                return {
                    "status": "error",
                    "message": f"File not found: {file_path}"
                }

            store_id = self._get_or_create_store(self.USER_STORE_NAME)

            google_file_name = self._upload_from_local_path(
                store_name=store_id,
                file_path=file_path,
                metadata=[
                    {'key': 'user_id', 'string_value': str(user_id)},
                    {'key': 'file_id', 'string_value': str(file_id)},
                    {'key': 'type', 'string_value': 'custom_upload'},
                    {'key': 'upload_time', 'string_value': str(int(time.time()))}
                ]
            )

            print(f"[FileStoreManager] Upload success - user_id: {user_id}, file_id: {file_id}")

            return {
                "status": "success",
                "store_name": store_id,
                "user_id": user_id,
                "file_id": file_id,
                "google_file_name": google_file_name,
                "mode": "custom",
                "message": "Custom rules uploaded and indexed successfully"
            }

        except FileNotFoundError as e:
            print(f"[FileStoreManager] Upload failed - file not found: {e}")
            return {
                "status": "error",
                "message": f"File not found: {file_path}"
            }
        except Exception as e:
            print(f"[FileStoreManager] Upload failed: {e}")
            return {
                "status": "error",
                "message": f"Upload failed: {str(e)}"
            }

    def get_user_context(self, user_id: str, file_id: str) -> Dict[str, Any]:
        """
        Gets the context for a previously uploaded user document.
        Called when user clicks "Check Compliance" after uploading.

        Args:
            user_id: User identifier
            file_id: File identifier

        Returns:
            Context dict for compliance checking
        """
        store_id = self._get_or_create_store(self.USER_STORE_NAME)

        return {
            "store_name": store_id,
            "metadata_filter": f'user_id = "{user_id}" AND file_id = "{file_id}"',
            "file_to_cleanup": None,  # Will be set after finding the file
            "mode": "custom"
        }

    def cleanup_user_file(self, user_id: str, file_id: str) -> Dict[str, Any]:
        """
        Deletes a user's uploaded file from the store.
        Called after compliance check or when user removes document.

        Args:
            user_id: User identifier
            file_id: File identifier

        Returns:
            Cleanup result
        """
        try:
            store_id = self._get_or_create_store(self.USER_STORE_NAME)

            # Find the file by metadata
            files = list(self.client.file_search_stores.documents.list(
                parent=store_id
            ))

            for f in files:
                if hasattr(f, 'custom_metadata') and f.custom_metadata:
                    meta_dict = {}
                    for m in f.custom_metadata:
                        if hasattr(m, 'string_value'):
                            meta_dict[m.key] = m.string_value

                    if meta_dict.get('user_id') == str(user_id) and meta_dict.get('file_id') == str(file_id):
                        # Retrieve the actual file name from metadata if available
                        file_to_delete = meta_dict.get('google_file_name')

                        if file_to_delete:
                            self.client.files.delete(name=file_to_delete)
                            print(f"[FileStoreManager] Deleted file: {file_to_delete}")
                            return {"status": "success", "message": f"Deleted file {file_to_delete}"}
                        else:
                            # Fallback: Delete the document from the store
                            self.client.files.delete(name=f.name)
                            return {"status": "success", "message": f"Deleted document {f.name}"}

            return {"status": "not_found", "message": "File not found in store"}

        except Exception as e:
            print(f"[FileStoreManager] Cleanup failed: {e}")
            return {"status": "error", "message": str(e)}

    # =========================================================================
    # INTERNAL METHODS
    # =========================================================================

    def _upload_from_local_path(self, store_name: str, file_path: str, metadata: list) -> str:
        """Uploads a local file to Google File Store with metadata."""
        try:
            # Upload to Gemini Files API
            print(f"[FileStoreManager] Uploading file: {file_path}")
            uploaded_file = self.client.files.upload(
                file=file_path,
                config={'mime_type': 'application/pdf'}
            )

            # Wait for processing
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(1)
                uploaded_file = self.client.files.get(name=uploaded_file.name)

            if uploaded_file.state.name == "FAILED":
                raise ValueError(f"File upload failed: {uploaded_file.error.message}")

            # Add google_file_name to metadata for cleanup
            metadata.append({'key': 'google_file_name', 'string_value': uploaded_file.name})

            # Import to store with metadata
            print(f"[FileStoreManager] Importing to store {store_name} with metadata...")
            self.client.file_search_stores.import_file(
                file_search_store_name=store_name,
                file_name=uploaded_file.name,
                config={'custom_metadata': metadata}
            )

            print(f"[FileStoreManager] Successfully imported: {uploaded_file.name}")
            return uploaded_file.name

        except Exception as e:
            print(f"[FileStoreManager] Error uploading file: {e}")
            raise

    def _get_or_create_store(self, display_name: str) -> str:
        """Gets existing store or creates new one."""
        # Check cache
        if display_name == self.USER_STORE_NAME and self._user_store_id:
            return self._user_store_id

        # Search existing stores
        try:
            for store in self.client.file_search_stores.list():
                if store.display_name == display_name:
                    print(f"[FileStoreManager] Using existing store: {store.name}")
                    self._user_store_id = store.name
                    return store.name
        except Exception as e:
            print(f"[FileStoreManager] Error listing stores: {e}")

        # Create new store
        print(f"[FileStoreManager] Creating new store: {display_name}")
        new_store = self.client.file_search_stores.create(
            config={'display_name': display_name}
        )

        self._user_store_id = new_store.name
        return new_store.name
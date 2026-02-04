"""
Compliance File Store Manager

Manages Google File Search Stores for Compliance service.
"""
from __future__ import annotations

import os
import time
import tempfile
import logging
from typing import Optional, Dict, Any

import requests
from google import genai
# from google.genai import types


class ComplianceFileStoreManager:
    """
    Manages Google File Search Stores for compliance checking.

    """

    def __init__(self):
        self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)

        # --- STORE CONFIGURATION ---
        self.USER_STORE_NAME = "Lawvriksh_User_Uploads_v1"
        
        # Cache store IDs
        self._user_store_id = None

        logger.info(f"Initialized ComplianceFileStoreManager")

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def prepare_compliance_context(
        self,
        user_id: str,
        s3_key: Optional[str] = None,
        file_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        THE DECISION ENGINE:
        Determines which rules to use based on whether user uploaded a document.

        Args:
            user_id: Unique user identifier
            s3_key: S3 key of user-uploaded PDF (None if no upload)
            file_id: Unique identifier for the file

        Returns:
            Context dict with store_name, metadata_filter, cleanup info, and mode
        """

        # --- PATH A: USER HAS CUSTOM RULES ---
        if s3_key:
            logger.info(f"User {user_id} provided custom rules. Using USER store.")
            return self._setup_user_context(user_id, s3_key, file_id)

        # --- PATH B: NO UPLOAD (FALLBACK TO ADMIN RULES) ---
        else:
            logger.info(f"No custom upload from {user_id}. Using ADMIN standard rules.")
            return self._setup_admin_context()

    def upload_user_document(
        self,
        s3_key: str,
        user_id: str,
        file_id: str
    ) -> Dict[str, Any]:
        """
        Uploads a user's custom rules document to the User Store.
        Called when user uploads a PDF (before clicking compliance check).

        Args:
            s3_key: S3 key of the uploaded PDF
            user_id: User identifier
            file_id: Unique file identifier

        Returns:
            Upload result with status and metadata
        """
        try:
            store_id = self._get_or_create_store(self.USER_STORE_NAME)

            google_file_name = self._upload_from_s3(
                store_name=store_id,
                s3_key=s3_key,
                metadata=[
                    {'key': 'user_id', 'string_value': str(user_id)},
                    {'key': 'file_id', 'string_value': str(file_id)},
                    {'key': 'type', 'string_value': 'custom_upload'},
                    {'key': 'upload_time', 'string_value': str(int(time.time()))}
                ]
            )

            logger.info(f"Upload success - user_id: {user_id}, file_id: {file_id}")

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
            logger.warning(f"Upload failed - S3 file not found: {e}")
            return {
                "status": "error",
                "message": f"File not found in S3. Please ensure the file was uploaded successfully: {s3_key}"
            }
        except Exception as e:
            logger.error(f"Upload failed: {e}")
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
                            logger.info(f"Deleted file: {file_to_delete}")
                            return {"status": "success", "message": f"Deleted file {file_to_delete}"}
                        else:
                            logger.warning(f"'google_file_name' not found in metadata for {f.name}")
                            # Fallback: Delete the document from the store
                            self.client.files.delete(name=f.name)
                            return {"status": "success", "message": f"Deleted document {f.name} (File name unknown)"}

            return {"status": "not_found", "message": "File not found in store"}

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            return {"status": "error", "message": str(e)}

  
    # =========================================================================
    # INTERNAL METHODS
    # =========================================================================

    def _setup_user_context(
        self,
        user_id: str,
        s3_key: str,
        file_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sets up context for user's custom rules."""
        store_id = self._get_or_create_store(self.USER_STORE_NAME)

        # Generate file_id if not provided
        if not file_id:
            file_id = f"user_{user_id}_{int(time.time())}"

        # Upload file with metadata
        google_file_name = self._upload_from_s3(
            store_name=store_id,
            s3_key=s3_key,
            metadata=[
                {'key': 'user_id', 'string_value': str(user_id)},
                {'key': 'file_id', 'string_value': str(file_id)},
                {'key': 'type', 'string_value': 'custom_upload'}
            ]
        )

        return {
            "store_name": store_id,
            "metadata_filter": f'user_id = "{user_id}" AND file_id = "{file_id}"',
            "file_to_cleanup": google_file_name,
            "google_file_name": google_file_name,
            "user_id": user_id,
            "file_id": file_id,
            "mode": "custom"
        }

    def _setup_admin_context(self) -> Dict[str, Any]:
        """Sets up context for admin standard rules."""
        store_id = self._get_or_create_store(self.ADMIN_STORE_NAME)

        # Ensure admin file exists (self-healing)
        admin_file = self._ensure_admin_file_exists(store_id)

        return {
            "store_name": store_id,
            "metadata_filter": 'type = "standard_admin_rule"',
            "file_to_cleanup": None,  # NEVER delete admin files
            "google_file_name": admin_file,
            "mode": "standard"
        }

 
    def _get_or_create_store(self, display_name: str) -> str:
        """Gets existing store or creates new one."""
        # Check cache
        if display_name == self.USER_STORE_NAME and self._user_store_id:
            return self._user_store_id
        if display_name == self.ADMIN_STORE_NAME and self._admin_store_id:
            return self._admin_store_id

        # Search existing stores
        try:
            for store in self.client.file_search_stores.list():
                if store.display_name == display_name:
                    logger.info(f"Using existing store: {store.name}")
                    # Cache and return
                    if display_name == self.USER_STORE_NAME:
                        self._user_store_id = store.name
                    else:
                        self._admin_store_id = store.name
                    return store.name
        except Exception as e:
            logger.warning(f"Error listing stores: {e}")

        # Create new store
        logger.info(f"Creating new store: {display_name}")
        new_store = self.client.file_search_stores.create(
            config={'display_name': display_name}
        )

        # Cache and return
        if display_name == self.USER_STORE_NAME:
            self._user_store_id = new_store.name
        else:
            self._admin_store_id = new_store.name

        return new_store.name
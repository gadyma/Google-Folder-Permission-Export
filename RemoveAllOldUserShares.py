import os
import pickle
import logging
import sys
import time
from datetime import datetime
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from config import CRED_LOCATION

# Suppress the file_cache warning AND the noisy internal HTTP warnings
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
logging.getLogger('googleapiclient.http').setLevel(logging.ERROR)

# --- SETUP LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- SETUP INSTRUCTIONS ---
# 1. Go to the Google Cloud Console (https://console.cloud.google.com/)
# 2. Create a project (or select an existing one).
# 3. Enable the "Google Drive API".
# 4. Go to "Credentials" -> "Create Credentials" -> "OAuth client ID".
# 5. Select "Desktop app", name it, and click "Create".
# 6. Download the JSON file, rename it to 'credentials.json', and place it in:
#    ~/git/Google Folder Permission Export/
# --------------------------

# --- DYNAMIC PATH CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_LOCATION = os.path.join(SCRIPT_DIR, 'token.json')

SCOPES = ['https://www.googleapis.com/auth/drive']

# SET THIS TO True TO TEST WITHOUT DELETING ANYTHING
# SET THIS TO False TO ACTUALLY REMOVE PERMISSIONS
DRY_RUN = False 

# You can hardcode the email here if you don't want to type it every time
TARGET_USER_EMAIL = None 

def create_drive_service():
    """Create and return authenticated Drive service with token refresh logic."""
    creds = None
    if os.path.exists(TOKEN_LOCATION):
        token_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(TOKEN_LOCATION))
        if token_age.total_seconds() > 12 * 3600:
            logging.info(f"Token is {token_age} old, forcing refresh...")
            os.remove(TOKEN_LOCATION)

    if os.path.exists(TOKEN_LOCATION):
        with open(TOKEN_LOCATION, 'rb') as token:
            creds = pickle.load(token)
            
        if creds and not creds.has_scopes(SCOPES):
            logging.warning("Existing token does not have full 'drive' access. Forcing re-authentication...")
            creds = None
            os.remove(TOKEN_LOCATION)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logging.info("Refreshing expired token...")
            creds.refresh(Request())
        else:
            logging.info("No valid credentials or insufficient scopes, starting auth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(CRED_LOCATION, SCOPES)
            creds = flow.run_local_server(port=0)        
        
        with open(TOKEN_LOCATION, 'wb') as token:
            pickle.dump(creds, token)
        logging.info("Token saved/updated")    
        
    return build('drive', 'v3', credentials=creds)

def remove_shared_drive_memberships(service, target_email):
    """
    Checks all Shared Drives the authenticated user can see and removes the 
    target user if they are a direct member of the Shared Drive.
    """
    mode_label = "[DRY RUN - NO CHANGES]" if DRY_RUN else "[LIVE MODE - DELETING]"
    logging.info(f"--- {mode_label} Checking Shared Drive Memberships for: {target_email} ---")
    
    page_token = None
    drives_processed = 0
    permissions_removed = 0

    try:
        while True:
            results = service.drives().list(pageToken=page_token, pageSize=100).execute()
            drives = results.get('drives', [])
            if not drives and not page_token:
                logging.info("No Shared Drives found.")
                break

            for drive in drives:
                drives_processed += 1
                drive_id = drive.get('id')
                drive_name = drive.get('name')

                try:
                    perms_result = service.permissions().list(
                        fileId=drive_id,
                        supportsAllDrives=True,
                        fields="permissions(id, emailAddress, role)"
                    ).execute()
                    
                    for perm in perms_result.get('permissions', []):
                        if perm.get('emailAddress') == target_email:
                            role = perm.get('role')
                            perm_id = perm.get('id')

                            if DRY_RUN:
                                logging.info(f"[Drive] WOULD REMOVE: {target_email} ({role}) from Shared Drive '{drive_name}'")
                                permissions_removed += 1
                            else:
                                try:
                                    logging.info(f"[Drive] REMOVING: {target_email} from Shared Drive '{drive_name}'")
                                    service.permissions().delete(
                                        fileId=drive_id, permissionId=perm_id, supportsAllDrives=True
                                    ).execute()
                                    permissions_removed += 1
                                except Exception as e:
                                    logging.error(f"Error removing from Shared Drive '{drive_name}': {e}")
                except Exception:
                    pass

            page_token = results.get('nextPageToken')
            if not page_token:
                break
                
        logging.info(f"Shared Drives Scanned: {drives_processed} | Memberships Removed: {permissions_removed}")
    except Exception as e:
        logging.error(f"An error occurred checking Shared Drives: {e}")


def remove_all_user_permissions(service, target_email):
    """
    Searches across ALL accessible drives and folders. Automatically resolves 
    folder inheritance and collects root causes (Groups/Domains) for manual cleanup.
    """
    mode_label = "[DRY RUN - NO CHANGES]" if DRY_RUN else "[LIVE MODE - DELETING]"
    logging.info(f"--- {mode_label} Starting Global File/Folder Removal for: {target_email} ---")
    
    query = f"'{target_email}' in readers or '{target_email}' in writers"
    
    page_token = None
    files_processed = 0
    permissions_removed = 0
    skipped_owners = 0
    
    # Tracking root causes for the final report
    indirect_sources = set()
    name_cache = {}

    def get_source_name(file_obj):
        """Helper to resolve parent IDs to actual human-readable names."""
        drive_id = file_obj.get('driveId')
        parents = file_obj.get('parents', [])
        
        if drive_id:
            if drive_id not in name_cache:
                try:
                    d = service.drives().get(driveId=drive_id).execute()
                    name_cache[drive_id] = f"Shared Drive: '{d.get('name')}'"
                except Exception:
                    name_cache[drive_id] = f"Shared Drive (ID: {drive_id})"
            return name_cache[drive_id]
        elif parents:
            parent_id = parents[0]
            if parent_id not in name_cache:
                try:
                    f = service.files().get(fileId=parent_id, supportsAllDrives=True, fields="name").execute()
                    name_cache[parent_id] = f"Parent Folder: '{f.get('name')}'"
                except Exception:
                    name_cache[parent_id] = f"Parent Folder (ID: {parent_id})"
            return name_cache[parent_id]
        return "Unknown Source (My Drive Root or Hidden)"

    try:
        while True:
            # We updated the fields to include parents and driveId to trace the root
            results = service.files().list(
                q=query,
                spaces='drive',
                corpora='allDrives',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                fields="nextPageToken, files(id, name, parents, driveId, permissions(id, type, role, emailAddress, domain, permissionDetails), capabilities)",
                pageToken=page_token
            ).execute()

            items = results.get('files', [])

            if not items and not page_token:
                logging.info("No files found with permissions for this user.")
                break

            for file in items:
                files_processed += 1
                file_id = file.get('id')
                file_name = file.get('name')
                permissions = file.get('permissions', [])
                
                user_direct_perm = None
                is_inherited_from_folder = False

                # 1. Look for explicit, direct permission for this user
                for perm in permissions:
                    if perm.get('emailAddress') == target_email:
                        user_direct_perm = perm
                        
                        # Check if this explicit permission is actually inherited from a parent folder
                        details = perm.get('permissionDetails', [])
                        if any(d.get('inherited', False) for d in details):
                            is_inherited_from_folder = True
                        break
                
                # 2. Handle the findings
                if user_direct_perm:
                    role = user_direct_perm.get('role')
                    perm_id = user_direct_perm.get('id')
                    
                    if role == 'owner':
                        logging.info(f"Skipping: {target_email} is the OWNER of '{file_name}'")
                        skipped_owners += 1
                        continue
                        
                    if is_inherited_from_folder:
                        source = get_source_name(file)
                        logging.info(f"    -> Skipped '{file_name}': Permission is inherited from {source}")
                        indirect_sources.add(source)
                        continue

                    if DRY_RUN:
                        logging.info(f"[{files_processed}] WOULD REMOVE: {target_email} ({role}) from '{file_name}'")
                        permissions_removed += 1
                    else:
                        try:
                            logging.info(f"[{files_processed}] REMOVING: {target_email} from '{file_name}'")
                            service.permissions().delete(
                                fileId=file_id,
                                permissionId=perm_id,
                                supportsAllDrives=True
                            ).execute()
                            permissions_removed += 1
                        except Exception as e:
                            # Gracefully catch inherited permissions that weren't flagged correctly by the API
                            error_msg = str(e)
                            if 'cannotDeletePermission' in error_msg or 'inherited' in error_msg:
                                source = get_source_name(file)
                                logging.info(f"    -> Skipped '{file_name}': Permission is inherited from {source}")
                                indirect_sources.add(source)
                            else:
                                logging.error(f"Error removing permission on '{file_name}': {e}")
                
                else:
                    # User matched search query, but has NO direct permission.
                    source = get_source_name(file)
                    found_group_or_domain = False
                    
                    for perm in permissions:
                        ptype = perm.get('type')
                        if ptype == 'group' and perm.get('emailAddress'):
                            indirect_sources.add(f"Google Group: {perm.get('emailAddress')} (found on {source})")
                            found_group_or_domain = True
                        elif ptype == 'domain':
                            indirect_sources.add(f"Domain-wide rule: {perm.get('domain')} (found on {source})")
                            found_group_or_domain = True
                            
                    if not found_group_or_domain:
                        indirect_sources.add(source)

            page_token = results.get('nextPageToken')
            if not page_token:
                break

        # --- FINAL SUMMARY REPORT ---
        logging.info("="*50)
        logging.info(f"PROCESS COMPLETE ({'DRY RUN' if DRY_RUN else 'LIVE'})")
        logging.info(f"Files Found: {files_processed}")
        logging.info(f"Direct File/Folder Permissions {'identified' if DRY_RUN else 'removed'}: {permissions_removed}")
        if skipped_owners > 0:
            logging.info(f"Files skipped (User is Owner): {skipped_owners}")
            
        if indirect_sources:
            logging.info("-" * 50)
            logging.info("🚨 ACTION REQUIRED: INDIRECT ACCESS DETECTED 🚨")
            logging.info(f"The user STILL has access to files inherited from the following sources.")
            logging.info("You must remove the user from these folders/drives/groups manually:")
            for source in sorted(indirect_sources):
                logging.info(f"  👉 {source}")
        logging.info("="*50)

    except Exception as e:
        logging.error(f"An error occurred during the search loop: {e}")

def main():
    try:
        service = create_drive_service()
        
        if TARGET_USER_EMAIL:
            user_email = TARGET_USER_EMAIL
        else:
            user_email = input("Enter the user email to remove permissions for: ").strip()
        
        if not user_email or "@" not in user_email:
            logging.error("Invalid email address provided.")
            return

        if DRY_RUN:
            logging.info(f"NOTE: Script is in DRY_RUN mode. Checking permissions for: {user_email}")
            remove_shared_drive_memberships(service, user_email)
            remove_all_user_permissions(service, user_email)
        else:
            confirm = input(f"\nCRITICAL: You are in LIVE mode. Remove ALL permissions for {user_email}? (yes/no): ")
            if confirm.lower() == 'yes':
                remove_shared_drive_memberships(service, user_email)
                remove_all_user_permissions(service, user_email)
            else:
                logging.info("Operation cancelled.")

    except Exception as e:
        if not isinstance(e, FileNotFoundError):
            logging.error(f"Critical Failure: {e}")

if __name__ == "__main__":
    main()
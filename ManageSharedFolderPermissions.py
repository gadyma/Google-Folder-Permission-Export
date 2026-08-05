#pip install -r requirements.txt
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import argparse
import datetime
from datetime import datetime
import csv
from google_auth_oauthlib.flow import Flow
import os
import pickle
from google.auth.transport.requests import Request
import logging

# Configuration
from config import CRED_LOCATION, FOLDER_ID

SCOPES_READONLY = ['https://www.googleapis.com/auth/drive.readonly']
SCOPES_WRITE    = ['https://www.googleapis.com/auth/drive']

# For shared folders, you'll need to specify the folder ID directly
SHARED_FOLDER_ID = FOLDER_ID

def create_drive_service(scopes):
    token_file = 'token_write.json' if scopes == SCOPES_WRITE else 'token_readonly.json'
    creds = None
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CRED_LOCATION, scopes)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
    return build('drive', 'v3', credentials=creds)

def get_file_path_shared(service, file_id, root_folder_id):
    """Get file path for files in shared folders"""
    path = []
    current_id = file_id
    
    while current_id != root_folder_id:
        try:
            file = service.files().get(
                fileId=current_id, 
                fields='name, parents',
                supportsAllDrives=True
            ).execute()
            
            path.insert(0, file['name'])
            
            if 'parents' not in file or not file['parents']:
                break
                
            parent = file['parents'][0]
            if parent == root_folder_id:
                break
            current_id = parent
            
        except Exception as e:
            print(f"Error getting path for {current_id}: {str(e)}")
            break
    
    return '/'.join(path)

def export_shared_folder_permissions(folder_id, service):
    """Export permissions for a shared folder and all its contents"""
    results = []
    
    def process_folder(current_folder_id, is_root=False):
        page_token = None
        while True:
            try:
                # For shared folders, we don't specify corpora or driveId
                query = f"'{current_folder_id}' in parents and trashed=false"
                response = service.files().list(
                    q=query,
                    fields='nextPageToken, files(id, name, mimeType, webViewLink, parents)',
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()
                
                for file in response.get('files', []):
                    file_info = {
                        'id': file['id'],
                        'name': file['name'],
                        'path': get_file_path_shared(service, file['id'], folder_id),
                        'webViewLink': file.get('webViewLink', ''),
                        'permissions': []
                    }
                    
                    try:
                        permissions = service.permissions().list(
                            fileId=file['id'],
                            fields='permissions(id, type, role, emailAddress, permissionDetails)',
                            supportsAllDrives=True
                        ).execute().get('permissions', [])
                        
                        # Filter only non-inherited permissions
                        non_inherited_permissions = [
                            p for p in permissions if not any(
                                detail.get('inherited', False) for detail in p.get('permissionDetails', [])
                            )
                        ]
                        file_info['permissions'] = non_inherited_permissions
                        
                    except Exception as e:
                        print(f"Error fetching permissions for file {file['name']}: {str(e)}")
                    
                    results.append(file_info)
                    
                    # Recursively process subfolders
                    if file.get('mimeType') == 'application/vnd.google-apps.folder':
                        process_folder(file['id'])
                
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
                    
            except Exception as e:
                print(f"Error processing folder {current_folder_id}: {str(e)}")
                break
    
    # Also get permissions for the root folder itself
    try:
        root_folder = service.files().get(
            fileId=folder_id,
            fields='id, name, webViewLink',
            supportsAllDrives=True
        ).execute()
        
        root_info = {
            'id': root_folder['id'],
            'name': root_folder['name'],
            'path': root_folder['name'],  # Root folder path is just its name
            'webViewLink': root_folder.get('webViewLink', ''),
            'permissions': []
        }
        
        permissions = service.permissions().list(
            fileId=folder_id,
            fields='permissions(id, type, role, emailAddress, permissionDetails)',
            supportsAllDrives=True
        ).execute().get('permissions', [])
        
        non_inherited_permissions = [
            p for p in permissions if not any(
                detail.get('inherited', False) for detail in p.get('permissionDetails', [])
            )
        ]
        root_info['permissions'] = non_inherited_permissions
        results.append(root_info)
        
    except Exception as e:
        print(f"Error getting root folder permissions: {str(e)}")
    
    # Process all contents of the folder
    process_folder(folder_id, is_root=True)
    return results

def remove_permission_breaks(service, data):
    """Delete all non-inherited (direct) permissions from child items so they revert to inheriting from parent."""
    removed = 0
    errors = 0
    for file in data:
        for permission in file.get('permissions', []):
            pid = permission.get('id')
            if not pid or pid == 'anyoneWithLink':
                continue
            try:
                service.permissions().delete(
                    fileId=file['id'],
                    permissionId=pid,
                    supportsAllDrives=True
                ).execute()
                print(f"  Removed permission {pid} ({permission.get('emailAddress', permission.get('type'))}) from '{file['name']}'")
                removed += 1
            except Exception as e:
                print(f"  Error removing permission {pid} from '{file['name']}': {str(e)}")
                errors += 1
    print(f"\nDone. Removed {removed} permission(s). Errors: {errors}.")


def save_to_csv(data, filename):
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['File ID', 'File Name', 'File Path', 'File Link', 'Permission ID', 'Type', 'Role', 'Email']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for file in data:
            if not file['permissions']:
                # If no permissions, still write the file info with empty permission fields
                writer.writerow({
                    'File ID': file['id'],
                    'File Name': file['name'],
                    'File Path': file['path'],
                    'File Link': file['webViewLink'],
                    'Permission ID': '',
                    'Type': '',
                    'Role': '',
                    'Email': ''
                })
            else:
                for permission in file['permissions']:
                    writer.writerow({
                        'File ID': file['id'],
                        'File Name': file['name'],
                        'File Path': file['path'],
                        'File Link': file['webViewLink'],
                        'Permission ID': permission.get('id', ''),
                        'Type': permission.get('type', ''),
                        'Role': permission.get('role', ''),
                        'Email': permission.get('emailAddress', '')
                    })

def get_folder_id_from_url(url):
    """Extract folder ID from Google Drive URL"""
    if '/folders/' in url:
        return url.split('/folders/')[1].split('?')[0].split('/')[0]
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export (and optionally fix) Google Drive folder permission breaks.")
    parser.add_argument('--url', help='Google Drive folder URL (overrides config FOLDER_ID)')
    parser.add_argument('--remove', action='store_true', help='Remove permission breaks after export')
    parser.add_argument('--children-only', action='store_true', help='When removing, skip the root folder and only fix children')
    parser.add_argument('--yes', action='store_true', help='Skip confirmation prompt before removing')
    args = parser.parse_args()

    start_time = datetime.now()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info("Script started")

    if args.url:
        folder_id = get_folder_id_from_url(args.url)
        if not folder_id:
            print("Invalid URL format. Please provide a valid Google Drive folder URL.")
            exit(1)
    else:
        folder_id = SHARED_FOLDER_ID
        if not folder_id or folder_id == "your_shared_folder_id_here":
            print("Please set SHARED_FOLDER_ID or pass --url.")
            exit(1)

    scopes = SCOPES_WRITE if args.remove else SCOPES_READONLY
    service = create_drive_service(scopes)

    print(f"Processing folder ID: {folder_id}")

    try:
        data = export_shared_folder_permissions(folder_id, service)
        export_fileName = f"shared_folder_{folder_id}_permissions.csv"
        save_to_csv(data, export_fileName)

        end_time = datetime.now()
        logging.info(f"Permissions exported successfully to {export_fileName}")
        logging.info(f"Found {len(data)} files/folders")
        logging.info(f"Script ended")
        logging.info(f"Total execution time: {end_time - start_time}")

        if args.remove:
            broken = [f for f in data if f['permissions']]
            if args.children_only:
                broken = [f for f in broken if f['id'] != folder_id]
            if broken:
                print(f"\n{len(broken)} item(s) have direct (non-inherited) permissions (permission breaks).")
                if args.yes or input("Confirm removal? (yes/no): ").strip().lower() == 'yes':
                    remove_permission_breaks(service, broken)
                else:
                    print("No permissions were removed.")
            else:
                print("No permission breaks found — nothing to remove.")

    except Exception as e:
        logging.error(f"Script failed: {str(e)}")
        print(f"Error: {str(e)}")
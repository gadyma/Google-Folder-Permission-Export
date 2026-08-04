from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from datetime import datetime
import csv
import os
import pickle
import logging
import time
import argparse
from config import CRED_LOCATION, DRIVE_ID, FOLDER_ID, SCOPES, INCLUDE_EMPTY_PERMISSIONS, SKIP_TRASH_FOLDER, PROFILES

# Suppress the file_cache warning
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

# Configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def create_drive_service():
    """Create and return authenticated Drive service with token refresh logic."""
    creds = None
    token_file = 'token.json'   
    # Check if token exists and its age
    if os.path.exists(token_file):
        token_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(token_file))
        if token_age.total_seconds() > 12 * 3600:  # 12 hours
            logging.info(f"Token is {token_age} old, forcing refresh...")
            os.remove(token_file)
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logging.info("Refreshing expired token...")
            creds.refresh(Request())
        else:
            logging.info("No valid credentials, starting auth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(CRED_LOCATION, SCOPES)
            creds = flow.run_local_server(port=0)        
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
        logging.info("Token saved/updated")    
    return build('drive', 'v3', credentials=creds)


def get_file_path(service, file_id, drive_id, max_depth=50):
    """Get full path of a file with cycle protection."""
    path = []
    visited = set()    
    while len(path) < max_depth:
        if file_id in visited:
            logging.warning(f"Cycle detected in path for file {file_id}")
            break
        visited.add(file_id)        
        try:
            file = service.files().get(
                fileId=file_id,
                supportsAllDrives=True,
                fields='name, parents'
            ).execute()            
            path.insert(0, file['name'])            
            if 'parents' not in file or file['parents'][0] == drive_id:
                break            
            file_id = file['parents'][0]
        except Exception as e:
            logging.error(f"Error getting path for file {file_id}: {str(e)}")
            path.insert(0, f"[Error: {file_id}]")
            break    
    return '/'.join(path)


def get_permissions_with_retry(service, file_id, file_name, max_retries=3):
    """Fetch permissions with retry logic for rate limiting."""
    for attempt in range(max_retries):
        try:
            permissions = service.permissions().list(
                fileId=file_id,
                fields='permissions(id, type, role, emailAddress, permissionDetails)',
                supportsAllDrives=True
            ).execute().get('permissions', [])
            # Filter non-inherited permissions
            non_inherited = [
                p for p in permissions 
                if not any(detail.get('inherited', False) 
                          for detail in p.get('permissionDetails', []))
            ]
            return non_inherited
        except Exception as e:
            if 'quota' in str(e).lower() or 'rate' in str(e).lower():
                wait_time = (2 ** attempt) * 2  # Exponential backoff
                logging.warning(f"Rate limit hit for {file_name}, waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                logging.error(f"Error fetching permissions for {file_name}: {str(e)}")
                return []
    logging.error(f"Failed to fetch permissions for {file_name} after {max_retries} attempts")
    return []


def export_permissions_recursive(drive_id, folder_id=None):
    """Export permissions recursively with progress tracking."""
    service = create_drive_service()
    results = []
    processed_count = 0
    def process_folder(current_folder_id, depth=0):
        nonlocal processed_count
        page_token = None
        while True:
            try:
                query = f"'{current_folder_id}' in parents"
                response = service.files().list(
                    corpora='drive',
                    driveId=drive_id,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    fields='nextPageToken, files(id, name, mimeType, webViewLink)',
                    pageToken=page_token,
                    pageSize=100,  # Process more files per request
                    q=query
                ).execute()
                files = response.get('files', [])
                for file in files:
                    # Skip Trash folder if configured
                    if SKIP_TRASH_FOLDER and file['name'] == 'Trash':
                        logging.info(f"Skipping Trash folder")
                        continue
                    processed_count += 1
                    if processed_count % 50 == 0:
                        logging.info(f"Processed {processed_count} files...")
                    file_info = {
                        'id': file['id'],
                        'name': file['name'],
                        'path': get_file_path(service, file['id'], drive_id),
                        'webViewLink': file.get('webViewLink', ''),
                        'permissions': get_permissions_with_retry(
                            service, file['id'], file['name']
                        )
                    }
                    results.append(file_info)
                    # Recursively process subfolders
                    if file.get('mimeType') == 'application/vnd.google-apps.folder':
                        process_folder(file['id'], depth + 1)
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
            except Exception as e:
                logging.error(f"Error processing folder {current_folder_id}: {str(e)}")
                break
    start_folder = folder_id if folder_id else drive_id
    logging.info(f"Starting export from {'folder' if folder_id else 'drive root'}: {start_folder}")
    process_folder(start_folder)
    logging.info(f"Total files processed: {processed_count}")
    return results


def save_to_csv(data, filename):
    """Save permissions data to CSV with error handling."""
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['File ID', 'File Name', 'File Path', 'File Link', 
                         'Permission ID', 'Type', 'Role', 'Email']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            row_count = 0
            for file in data:
                if not file['permissions']:
                    # Write file even without non-inherited permissions only if INCLUDE_EMPTY_PERMISSIONS is True
                    if INCLUDE_EMPTY_PERMISSIONS:
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
                        row_count += 1
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
                        row_count += 1
            logging.info(f"Wrote {row_count} permission records to CSV")
    except Exception as e:
        logging.error(f"Error saving to CSV: {str(e)}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Export Google Drive folder permissions to CSV')
    if PROFILES:
        parser.add_argument('--profile', metavar='NAME', choices=list(PROFILES),
                            help=f'Named profile from ~/.google-folder-export.json ({", ".join(PROFILES)})')
    parser.add_argument('--drive-id', metavar='ID', help='Shared Drive ID (overrides config/profile)')
    parser.add_argument('--folder-id', metavar='ID', help='Start from this folder ID (default: entire drive)')
    parser.add_argument('--include-empty-permissions', action='store_true',
                        help='Include files with no explicit permissions in CSV output')
    parser.add_argument('--include-trash', action='store_true',
                        help='Include the Trash folder in the export (default: skip)')
    cli = parser.parse_args()

    prof = PROFILES.get(cli.profile, {}) if PROFILES and getattr(cli, 'profile', None) else {}
    drive_id  = cli.drive_id   or prof.get('drive_id')   or DRIVE_ID
    folder_id = cli.folder_id  or prof.get('folder_id')  or FOLDER_ID
    if cli.include_empty_permissions:
        INCLUDE_EMPTY_PERMISSIONS = True
    if cli.include_trash:
        SKIP_TRASH_FOLDER = False

    start_time = datetime.now()
    logging.info("="*50)
    logging.info("Script started")
    logging.info(f"Profile:   {getattr(cli, 'profile', None) or '(none)'}")
    logging.info(f"Drive ID:  {drive_id}")
    logging.info(f"Folder ID: {folder_id or 'None (entire drive)'}")

    try:
        data = export_permissions_recursive(drive_id, folder_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_filename = f"{drive_id[:8]}-permissions_{timestamp}.csv"
        save_to_csv(data, export_filename)
        end_time = datetime.now()
        logging.info(f"Permissions exported successfully to {export_filename}")
        logging.info(f"Total execution time: {end_time - start_time}")
        logging.info("="*50)
    except Exception as e:
        logging.error(f"Script failed: {str(e)}")
        raise
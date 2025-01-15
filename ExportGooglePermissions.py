#
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import datetime
# Add this at the beginning of the script, after the other imports
from datetime import datetime
import csv
from google_auth_oauthlib.flow import Flow


import logging


# Configuration
from config import CRED_LOCATION, DRIVE_ID, FOLDER_ID,SCOPES


print(FOLDER_ID)
print(DRIVE_ID)

def create_drive_service():
    flow = InstalledAppFlow.from_client_secrets_file(CRED_LOCATION, SCOPES)
    creds = flow.run_local_server(port=0)
    return build('drive', 'v3', credentials=creds)

def get_file_path(service, file_id, DRIVE_ID):
    path = []
    while True:
        file = service.files().get(fileId=file_id, 
                                   supportsAllDrives=True, 
                                   fields='name, parents').execute()
        path.insert(0, file['name'])
        if 'parents' not in file:
            return '/'.join(path)
        parent = file['parents'][0]
        if parent == DRIVE_ID:
            return '/'.join(path)
        file_id = parent


def export_permissionsdrive(DRIVE_ID):
    service = create_drive_service()
    results = []
    page_token = None
    while True:
        response = service.files().list(
            corpora='drive',
            driveId=DRIVE_ID,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields='nextPageToken, files(id, name, mimeType, webViewLink)',
            pageToken=page_token
        ).execute()
        for file in response.get('files', []):
            file_info = {
                'id': file['id'],
                'name': file['name'],
                'path': get_file_path(service, file['id'], DRIVE_ID),
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
        page_token = response.get('nextPageToken')
        if not page_token:
            break
    return results

def export_permissions_recursive(DRIVE_ID, FOLDER_ID=None):
    service = create_drive_service()
    results = []

    def process_folder(current_FOLDER_ID):
        page_token = None
        while True:
            query = f"'{current_FOLDER_ID}' in parents"
            response = service.files().list(
                corpora='drive',
                driveId=DRIVE_ID,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                fields='nextPageToken, files(id, name, mimeType, webViewLink)',
                pageToken=page_token,
                q=query
            ).execute()

            for file in response.get('files', []):
                file_info = {
                    'id': file['id'],
                    'name': file['name'],
                    'path': get_file_path(service, file['id'], DRIVE_ID),
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

    # Start processing from the given folder or drive root
    start_FOLDER_ID = FOLDER_ID if FOLDER_ID else DRIVE_ID
    process_folder(start_FOLDER_ID)

    return results


def save_to_csv(data, filename):
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['File ID', 'File Name', 'File Path', 'File Link', 'Permission ID', 'Type', 'Role', 'Email']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for file in data:
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

if __name__ == "__main__":
    start_time = datetime.now()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info(f"Script started")

    if FOLDER_ID is None: 
        data = export_permissionsdrive(DRIVE_ID)
    else:
        data = export_permissions_recursive(DRIVE_ID, FOLDER_ID)

    export_fileName= f"{DRIVE_ID}-{FOLDER_ID}-permissions_with_subfolders.csv"

    save_to_csv(data, export_fileName)
    end_time = datetime.now()
    logging.info(f"Permissions exported successfully to {export_fileName}")
    logging.info(f"Script ended")
    logging.info(f"Total execution time: {end_time - start_time}")
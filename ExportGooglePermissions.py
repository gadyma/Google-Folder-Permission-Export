from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

import csv

from google_auth_oauthlib.flow import Flow

SCOPES='https://www.googleapis.com/auth/drive.readonly'  #'https://www.googleapis.com/auth/drive'
Cred_Location = r'/Users/gadymargalit/Google Drive/My Drive/client_secret_889044164890-e7uaksnamilululifggvfv9d75hskram.apps.googleusercontent.com.json'
def create_drive_service():
    flow = InstalledAppFlow.from_client_secrets_file(Cred_Location, SCOPES)
    creds = flow.run_local_server(port=0)
    return build('drive', 'v3', credentials=creds)

def get_file_path(service, file_id, drive_id):
    path = []
    while True:
        file = service.files().get(fileId=file_id, 
                                   supportsAllDrives=True, 
                                   fields='name, parents').execute()
        path.insert(0, file['name'])
        if 'parents' not in file:
            return '/'.join(path)
        parent = file['parents'][0]
        if parent == drive_id:
            return '/'.join(path)
        file_id = parent

def export_permissions(drive_id):
    service = create_drive_service()
    results = []
    page_token = None
    while True:
        response = service.files().list(
            corpora='drive',
            driveId=drive_id,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields='nextPageToken, files(id, name)',
            pageToken=page_token
        ).execute()
        for file in response.get('files', []):
            file_info = {
                'id': file['id'],
                'name': file['name'],
                'path': get_file_path(service, file['id'], drive_id),
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


def save_to_csv(data, filename):
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['File ID', 'File Name', 'File Path', 'Permission ID', 'Type', 'Role', 'Email']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for file in data:
            for permission in file['permissions']:
                writer.writerow({
                    'File ID': file['id'],
                    'File Name': file['name'],
                    'File Path': file['path'],
                    'Permission ID': permission.get('id', ''),
                    'Type': permission.get('type', ''),
                    'Role': permission.get('role', ''),
                    'Email': permission.get('emailAddress', '')
                })

if __name__ == "__main__":
    drive_id = '0AOZRDL5IgELsUk9PVA' # Gadytest
    drive_id = '0AMtS8_BftCO5Uk9PVA' # מערך טכנולוגיה
    data = export_permissions(drive_id)
    save_to_csv(data, 'shared_drive_permissions.csv')
    print("Permissions exported successfully to shared_drive_permissions.csv")

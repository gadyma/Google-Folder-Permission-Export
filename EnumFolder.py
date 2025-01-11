from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow

# Define the required scopes
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
Cred_Location = r'/Users/gadymargalit/Google Drive/My Drive/client_secret_889044164890-e7uaksnamilululifggvfv9d75hskram.apps.googleusercontent.com.json'
def create_drive_service():
    flow = InstalledAppFlow.from_client_secrets_file(Cred_Location, SCOPES)
    creds = flow.run_local_server(port=0)
    return build('drive', 'v3', credentials=creds)

def list_files_in_shared_drive(service, shared_drive_id):
    results = []
    page_token = None
    
    while True:
        response = service.files().list(
            q=f"'root' in parents and trashed=false",
            corpora='drive',
            driveId=shared_drive_id,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
            fields='nextPageToken, files(id, name, mimeType)',
            pageToken=page_token
        ).execute()
        
        results.extend(response.get('files', []))
        page_token = response.get('nextPageToken')
        
        if not page_token:
            break
    
    return results

def main():
    service = create_drive_service()
    shared_drive_id = '0AOZRDL5IgELsUk9PVA'
    
    files = list_files_in_shared_drive(service, shared_drive_id)
    
    for file in files:
        print(f"Name: {file['name']}, ID: {file['id']}, Type: {file['mimeType']}")

if __name__ == '__main__':
    main()

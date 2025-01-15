# config.py
from pathlib import Path
SCOPES = 'https://www.googleapis.com/auth/drive.readonly'

CRED_LOCATION = Path.home() / 'client_secret_111190-replaceme.apps.googleusercontent.com.json'
DRIVE_ID = 'Replace with your actual drive ID'  # Replace with your actual drive ID
FOLDER_ID = None  # Set this to a folder ID if you want to start from a specific folder

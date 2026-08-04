# config.py — sensitive values live in ~/.google-folder-export.json (never committed)
from pathlib import Path
import json

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

_local_file = Path.home() / '.google-folder-export.json'
_local = json.loads(_local_file.read_text()) if _local_file.exists() else {}

PROFILES = _local.get('profiles', {})
_default = PROFILES.get(_local.get('default_profile', ''), {})

CRED_LOCATION = (
    Path(str(_local['cred_location']).replace('~', str(Path.home())))
    if _local.get('cred_location')
    else Path.home() / 'client_secret_placeholder.apps.googleusercontent.com.json'
)

DRIVE_ID  = _default.get('drive_id')  or _local.get('drive_id',  'Replace with your actual drive ID')
FOLDER_ID = _default.get('folder_id') or _local.get('folder_id', None)

INCLUDE_EMPTY_PERMISSIONS = _local.get('include_empty_permissions', False)
SKIP_TRASH_FOLDER         = _local.get('skip_trash_folder', True)

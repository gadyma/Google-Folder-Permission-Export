# Google Folder Permission Export

Exports non-inherited file permissions from a Google Shared Drive to CSV.
Walks the drive (or a specific folder) recursively and writes one row per explicit permission.

## Requirements

```bash
pip install -r requirements.txt
```

You also need a **Google Cloud OAuth 2.0 client secret** JSON file with the Drive API enabled.
Download it from the [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials.

## Setup

### 1. Local config file

Copy the sample and fill in your values:

```bash
cp google-folder-export.sample.json ~/.google-folder-export.json
```

Edit `~/.google-folder-export.json`:

| Key | Description |
|-----|-------------|
| `cred_location` | Path to your OAuth client secret JSON |
| `default_profile` | Profile used when no `--profile` flag is given |
| `include_empty_permissions` | Include files with no explicit permissions in the CSV (default: `false`) |
| `skip_trash_folder` | Skip the Trash folder (default: `true`) |
| `profiles` | Named drive/folder targets (see sample) |

The file lives in `~` and is never committed — keep your Drive IDs and credentials there.

### 2. First run — OAuth consent

On the first run the browser will open for Google sign-in. A `token.json` is saved locally (also gitignored) and reused on subsequent runs. Tokens older than 12 hours are refreshed automatically.

## Usage

```bash
# Use the default profile
python3 ExportGooglePermissions.py

# Use a named profile
python3 ExportGooglePermissions.py --profile my-drive

# Override drive/folder on the fly
python3 ExportGooglePermissions.py --drive-id 0XXXXXXXXXXXXXXXXXX
python3 ExportGooglePermissions.py --drive-id 0XXXXXXXXXXXXXXXXXX --folder-id 1YYYYYYYYYYYYYYYYY

# Include files that have no explicit permissions
python3 ExportGooglePermissions.py --include-empty-permissions

# Include the Trash folder
python3 ExportGooglePermissions.py --include-trash
```

Output is a CSV named `<drive-id-prefix>-permissions_<timestamp>.csv` in the current directory.

### CSV columns

| Column | Description |
|--------|-------------|
| File ID | Google Drive file ID |
| File Name | File or folder name |
| File Path | Full path within the drive |
| File Link | `webViewLink` URL |
| Permission ID | Google permission ID |
| Type | `user`, `group`, `domain`, or `anyone` |
| Role | `owner`, `writer`, `commenter`, or `reader` |
| Email | Email address (for `user`/`group` type) |

## Other scripts

| Script | Description |
|--------|-------------|
| `ExportGooglePermissions_Shared_folder.py` | Export permissions for items shared directly with your account |
| `RemoveAllOldUserShares.py` | Remove explicit share permissions from files in bulk |

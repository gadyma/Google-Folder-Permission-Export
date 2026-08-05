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

On the first run the browser will open for Google sign-in. Two token files are saved locally (both gitignored) and reused on subsequent runs:

| Token file | Used when |
|---|---|
| `token_readonly.json` | Export only |
| `token_write.json` | Export + remove (`--remove` flag) |

Tokens are refreshed automatically when expired.

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

## ManageSharedFolderPermissions.py

Exports non-inherited (direct) permissions from a shared folder and optionally removes them so children revert to inheriting from their parent.

```bash
# Export only
python3 ManageSharedFolderPermissions.py --url https://drive.google.com/drive/folders/FOLDER_ID

# Export and remove breaks from children only (prompts to confirm)
python3 ManageSharedFolderPermissions.py --url ... --remove --children-only

# Export and remove breaks from children + parent folder
python3 ManageSharedFolderPermissions.py --url ... --remove

# Skip confirmation prompt (useful for automation)
python3 ManageSharedFolderPermissions.py --url ... --remove --children-only --yes
```

### Flags

| Flag | Description |
|------|-------------|
| `--url` | Google Drive folder URL (overrides `FOLDER_ID` in config) |
| `--remove` | Remove permission breaks after export |
| `--children-only` | When removing, skip the root folder and only fix children |
| `--yes` | Skip confirmation prompt before removing |

Output is a CSV named `shared_folder_<folder-id>_permissions.csv` in the current directory. Only non-inherited (direct) permissions are included — items that inherit cleanly from their parent are listed with empty permission fields.

## Other scripts

| Script | Description |
|--------|-------------|
| `ManageSharedFolderPermissions.py` | Export and optionally remove permission breaks from a shared folder. Supports `--remove`, `--children-only`, and `--yes` flags. |
| `RemoveAllOldUserShares.py` | Remove explicit share permissions from files in bulk |

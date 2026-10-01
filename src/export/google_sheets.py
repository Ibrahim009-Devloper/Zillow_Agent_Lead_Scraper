import pandas as pd
import gspread
from google.oauth2 import service_account
from googleapiclient.discovery import build

from src import config

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
FOLDER_MIME = "application/vnd.google-apps.folder"


def _ensure_folder(drive, name, parent):
    q = f"name='{name}' and mimeType='{FOLDER_MIME}' and trashed=false and '{parent}' in parents"
    res = drive.files().list(q=q, fields="files(id)", supportsAllDrives=True,
                             includeItemsFromAllDrives=True).execute()
    if res["files"]:
        return res["files"][0]["id"]
    f = drive.files().create(body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent]},
                             fields="id", supportsAllDrives=True).execute()
    return f["id"]


def upload_to_sheets(xlsx_path, location):
    """Drive: <parent>/<location>/agent_lead/<location>_agent_leads (Google Sheet)"""
    creds = service_account.Credentials.from_service_account_file(config.GOOGLE_CREDENTIALS_FILE, scopes=SCOPES)
    drive = build("drive", "v3", credentials=creds)
    if not config.GOOGLE_PARENT_FOLDER_ID:
        raise RuntimeError("GOOGLE_PARENT_FOLDER_ID missing in .env")

    sheet_name = f"{location}_agent_leads"
    loc_folder = _ensure_folder(drive, location, config.GOOGLE_PARENT_FOLDER_ID)
    lead_folder = _ensure_folder(drive, "agent_lead", loc_folder)

    # Check if a sheet already exists in lead_folder, loc_folder, or parent folder
    target_sheet_id = None
    q = f"mimeType='application/vnd.google-apps.spreadsheet' and trashed=false and ('{lead_folder}' in parents or '{loc_folder}' in parents or '{config.GOOGLE_PARENT_FOLDER_ID}' in parents)"
    res = drive.files().list(q=q, fields="files(id, name)", supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    for f in res.get("files", []):
        if f["name"].lower() == sheet_name.lower():
            target_sheet_id = f["id"]
            break

    if not target_sheet_id:
        try:
            sheet_meta = drive.files().create(
                body={"name": sheet_name, "mimeType": "application/vnd.google-apps.spreadsheet",
                      "parents": [lead_folder]},
                fields="id", supportsAllDrives=True).execute()
            target_sheet_id = sheet_meta["id"]
        except Exception as e:
            if "storageQuotaExceeded" in str(e) or "quota" in str(e).lower():
                raise RuntimeError(
                    f"Google Service Accounts on personal Gmail have 0 MB storage quota and cannot create new files directly.\n"
                    f"👉 Please open your Google Drive folder 'Zillow_Real_Estate_Agent_Lead', create a new Google Sheet named '{sheet_name}', and run again!"
                ) from e
            raise

    df = pd.read_excel(xlsx_path).fillna("").astype(str)
    ws = gspread.authorize(creds).open_by_key(target_sheet_id).sheet1
    ws.clear()
    ws.update([df.columns.tolist()] + df.values.tolist())
    ws.freeze(rows=1)

    try:
        # Professional dark navy header styling with bold white text
        ws.format("1:1", {
            "backgroundColor": {"red": 0.106, "green": 0.212, "blue": 0.365},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
            "horizontalAlignment": "CENTER"
        })
    except Exception:
        pass

    return f"https://docs.google.com/spreadsheets/d/{target_sheet_id}"

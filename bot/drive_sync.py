import io
import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_NAME = "Flashcards"
FILE_NAME = "flashcards.json"

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CREDENTIALS_PATH = os.path.join(_BASE_DIR, "credentials.json")
_TOKEN_PATH = os.path.join(_BASE_DIR, "token.json")


def get_service():
    creds = None
    if os.path.exists(_TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(_TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(_CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(_TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def _get_or_create_folder(service) -> str:
    results = service.files().list(
        q=f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id)",
    ).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    folder = service.files().create(
        body={"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    return folder["id"]


def _find_file(service, folder_id: str) -> str | None:
    results = service.files().list(
        q=f"name='{FILE_NAME}' and '{folder_id}' in parents and trashed=false",
        fields="files(id)",
    ).execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


def load_cards(service) -> dict:
    folder_id = _get_or_create_folder(service)
    file_id = _find_file(service, folder_id)
    if not file_id:
        return {"cards": []}

    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return json.loads(buffer.read().decode("utf-8"))


def save_cards(service, data: dict):
    folder_id = _get_or_create_folder(service)
    file_id = _find_file(service, folder_id)

    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype="application/json")

    if file_id:
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        service.files().create(
            body={"name": FILE_NAME, "parents": [folder_id]},
            media_body=media,
            fields="id",
        ).execute()

import re

import fitz  # PyMuPDF
from youtube_transcript_api import YouTubeTranscriptApi


def extract_youtube(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/)([^&\n?#]+)", url)
    if not match:
        raise ValueError("URL YouTube invalide")
    video_id = match.group(1)
    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id, languages=["fr", "en", "fr-FR", "en-US"])
    return " ".join(snippet.text for snippet in transcript)


def extract_drive_file(service, url: str) -> str:
    file_id = _parse_drive_id(url)
    meta = service.files().get(fileId=file_id, fields="mimeType,name").execute()
    mime = meta["mimeType"]

    content: bytes = service.files().get_media(fileId=file_id).execute()

    if mime == "application/pdf":
        doc = fitz.open(stream=content, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    elif mime in ("text/plain", "text/markdown"):
        return content.decode("utf-8")
    else:
        raise ValueError(f"Type de fichier non supporté : {mime}. Utilise un PDF ou un fichier texte.")


def _parse_drive_id(url: str) -> str:
    # https://drive.google.com/file/d/{id}/view
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    # https://drive.google.com/open?id={id}
    match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    raise ValueError("Impossible d'extraire l'ID depuis l'URL Google Drive.")

"""Загрузка на YouTube через YouTube Data API v3."""
import os
import re

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .util import log

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def has_credentials():
    return all(os.environ.get(k, "").strip() for k in
               ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def _clean(s):
    return re.sub(r"[<>]", "", s or "").strip()


def make_title(title):
    title = _clean(re.sub(r"#\S+", "", title))
    title = re.sub(r"\s+", " ", title).strip()
    suffix = " #shorts"
    if len(title) + len(suffix) > 100:
        title = title[: 100 - len(suffix) - 1].rstrip() + "…"
    return title + suffix


def make_tags(hashtags, keywords):
    tags, total = [], 0
    for t in ["shorts", "тайны", "загадки", "мистика"] + [h.lstrip("#") for h in hashtags] + list(keywords):
        t = _clean(t).replace(",", " ").strip()
        if not t or t.lower() in (x.lower() for x in tags):
            continue
        if total + len(t) + 3 > 450:
            break
        tags.append(t)
        total += len(t) + 3
    return tags


def upload(path, title, description, tags):
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"].strip(),
        client_id=os.environ["YT_CLIENT_ID"].strip(),
        client_secret=os.environ["YT_CLIENT_SECRET"].strip(),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {
        "snippet": {
            "title": title,
            "description": _clean(description)[:4900],
            "tags": tags,
            "categoryId": "27",  # Образование
            "defaultLanguage": "ru",
            "defaultAudioLanguage": "ru",
        },
        "status": {
            "privacyStatus": os.environ.get("YT_PRIVACY", "public") or "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(path, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk(num_retries=5)
        if status:
            log(f"YouTube: {int(status.progress() * 100)}%")
    vid = resp["id"]
    log(f"YouTube: uploaded https://youtube.com/shorts/{vid}")
    return vid

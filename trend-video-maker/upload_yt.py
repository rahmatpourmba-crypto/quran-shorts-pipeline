# -*- coding: utf-8 -*-
"""upload_yt - YouTube upload + OAuth auth for the daily pipeline.

API surface expected by daily_quran_fm.py / build_long.py:
    auth(token_path) -> credentials/service
    upload(yt, video, thumb, title, desc, tags=..., privacy=..., made_for_kids=...,
           category_id=..., publish_at=...) -> video_id

Reconstructed after trend-video-maker was lost. Requires a valid OAuth token
pickle (token_aya.pickle); without it auth() raises.
"""
import pickle
from pathlib import Path

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def auth(token_path):
    import google.auth.transport.requests
    import google.oauth2.credentials
    import googleapiclient.discovery

    token_path = Path(token_path)
    if not token_path.exists():
        raise FileNotFoundError(f"no token at {token_path}")
    with open(token_path, "rb") as fh:
        creds = pickle.load(fh)
    if creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
        with open(token_path, "wb") as fh:
            pickle.dump(creds, fh)
    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def clean_orphans(yt, limit=8):
    """Delete own broken uploads (not processed) so retries never pile up dead
    videos. Each crashed resumable session leaves a zero-duration video."""
    import time
    try:
        r = yt.channels().list(part="contentDetails", mine=True).execute()
        pl = r["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        ids = []
        page = None
        for _ in range(3):
            p = yt.playlistItems().list(part="contentDetails", playlistId=pl,
                                        maxResults=50, pageToken=page).execute()
            ids += [i["contentDetails"]["videoId"] for i in p.get("items", [])]
            page = p.get("nextPageToken")
            if not page:
                break
            time.sleep(0.2)
        ids = ids[:limit]
        for i in range(0, len(ids), 50):
            vv = yt.videos().list(part="status", id=",".join(ids[i:i + 50])).execute()
            for v in vv.get("items", []):
                us = v["status"].get("uploadStatus", "")
                if us != "processed":
                    try:
                        yt.videos().delete(id=v["id"]).execute()
                        print(f"  orphan removed: {v['id']} ({us})", flush=True)
                    except Exception as e:
                        print(f"  orphan del failed {v['id']}: {e}", flush=True)
                    time.sleep(0.3)
    except Exception as e:
        print(f"  orphan scan skipped: {e}", flush=True)


def upload(yt, video, thumb, title, desc, tags=None, privacy="public",
           made_for_kids=False, category_id=27, publish_at=None, skip_orphans=False):
    from googleapiclient.http import MediaFileUpload

    if not skip_orphans:
        clean_orphans(yt)
    if publish_at:
        from datetime import datetime, timezone
        try:
            when = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
            if when <= datetime.now(timezone.utc):
                publish_at = None
                privacy = "public"
        except Exception:
            pass

    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": made_for_kids}
    if publish_at:
        status["publishAt"] = publish_at
    body = {
        "snippet": {
            "title": title,
            "description": desc,
            "tags": tags or [],
            "categoryId": str(category_id),
        },
        "status": status,
    }
    media = MediaFileUpload(str(video), chunksize=8 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    import time
    response = None
    attempt = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"  upload {int(status.progress() * 100)}%", flush=True)
                attempt = 0
        except Exception as e:
            attempt += 1
            print(f"  upload err {attempt}: {type(e).__name__} {str(e)[:130]} "
                  f"(wait {min(30 * attempt, 300)}s)", flush=True)
            time.sleep(min(30 * attempt, 300))
    vid = response.get("id")
    print(f"  uploaded: https://youtu.be/{vid}", flush=True)
    if vid and thumb and thumb.exists():
        try:
            yt.thumbnails().set(
                videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()
            print(f"  thumbnail set: {thumb.name}", flush=True)
        except Exception:
            pass
    return vid
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
            msg = str(e)
            if "quota" in msg.lower() or "429" in msg or "Uploads per day" in msg:
                print(f"  QUOTA EXCEEDED (daily upload cap): {type(e).__name__} {msg[:120]}", flush=True)
                raise
            attempt += 1
            print(f"  upload err {attempt}: {type(e).__name__} {msg[:130]} "
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


# === YouTube Channel Optimizations (SEO + Engagement) ===

def create_or_get_playlist(yt, title, description="", privacy="private"):
    """Find existing playlist by title, or create one. Returns playlist_id."""
    import time
    r = yt.playlists().list(part="snippet,contentDetails", mine=True, maxResults=25).execute()
    for item in r.get("items", []):
        if item["snippet"]["title"] == title:
            print(f"  playlist exists: {title} -> {item['id']}", flush=True)
            return item["id"]
    body = {"snippet": {"title": title, "description": description},
            "status": {"privacyStatus": privacy}}
    resp = yt.playlists().insert(part="snippet,status", body=body).execute()
    pid = resp["id"]
    print(f"  playlist created: {title} -> {pid}", flush=True)
    time.sleep(0.5)
    return pid


def add_to_playlist(yt, playlist_id, video_id):
    """Add a video to a playlist. Idempotent."""
    import time
    try:
        r = yt.playlistItems().list(part="snippet", playlistId=playlist_id,
                                     maxResults=50).execute()
        for item in r.get("items", []):
            if item["snippet"]["resourceId"]["videoId"] == video_id:
                return  # already in playlist
        yt.playlistItems().insert(
            part="snippet",
            body={"snippet": {"playlistId": playlist_id,
                              "resourceId": {"kind": "youtube#video",
                                             "videoId": video_id}}}).execute()
        print(f"  added to playlist {playlist_id[:16]}: {video_id}", flush=True)
        time.sleep(0.3)
    except Exception as e:
        print(f"  playlist add failed: {e}", flush=True)


def post_pinned_comment(yt, video_id, text):
    """Post a pinned comment on a video."""
    import time
    try:
        body = {"snippet": {"videoId": video_id,
                            "topLevelComment": {"snippet": {"textOriginal": text}}},
                "regionCode": "US"}
        resp = yt.commentThreads().insert(
            part="snippet", body=body).execute()
        cid = resp["id"]
        # Pin it
        yt.commentThreads().update(
            part="snippet",
            body={"id": cid,
                  "snippet": {"topLevelComment": {"snippet": {"textOriginal": text,
                                                              "authorDisplayName": ""}}}}).execute()
        print(f"  pinned comment on {video_id[:11]}", flush=True)
        time.sleep(0.3)
    except Exception as e:
        print(f"  comment failed: {e}", flush=True)


def update_channel_metadata(yt, description, keywords=""):
    """Update channel branding description and keywords."""
    try:
        r = yt.channels().list(part="brandingSettings", mine=True).execute()
        if not r.get("items"):
            return
        settings = r["items"][0].get("brandingSettings", {})
        current_desc = settings.get("channel", {}).get("description", "")
        current_keywords = settings.get("channel", {}).get("keywords", "")
        if current_desc != description or current_keywords != keywords:
            yt.channels().update(
                part="brandingSettings",
                body={"brandingSettings": {
                    "channel": {"description": description, "keywords": keywords}}}).execute()
            print(f"  channel metadata updated (keywords: {keywords[:30]}...)", flush=True)
    except Exception as e:
        print(f"  channel metadata update skipped: {e}", flush=True)


def get_uploads_playlist_id(yt):
    """Return the special 'uploads' playlist ID for the channel."""
    r = yt.channels().list(part="contentDetails", mine=True).execute()
    return r["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
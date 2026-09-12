# -*- coding: utf-8 -*-
"""Channel registry + YouTube/Analytics clients (multi-channel OAuth)."""
import json
import pickle
import threading
from datetime import date, timedelta
from pathlib import Path

from google.auth.transport.requests import Request
from googleapiclient.discovery import build

HOME = Path(__file__).resolve().parent
REGISTRY = HOME / "channels.json"
LOCK = threading.Lock()


def _default_registry():
    return {"channels": {
        "aya": {
            "id": "UC7P9VOk6zxBLnG3Zd_wyJNw",
            "name": "آیه آرامش",
            "token": "trend-video-maker/token_aya.pickle",
            "goal_hours": 4000,
        }
    }}


def load_registry():
    with LOCK:
        if REGISTRY.exists():
            try:
                return json.loads(REGISTRY.read_text(encoding="utf-8"))
            except Exception:
                pass
        reg = _default_registry()
        REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
        return reg


def save_registry(reg):
    with LOCK:
        REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def creds_for(profile):
    path = Path(profile["token"])
    if not path.is_absolute():
        path = HOME.parent / path
    if not path.exists():
        raise FileNotFoundError(f"token file not found: {path}")
    creds = pickle.loads(path.read_bytes())
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        path.write_bytes(pickle.dumps(creds))
    return creds


def cli_for(profile, kind="youtube"):
    creds = creds_for(profile)
    return build(kind, "v2" if kind == "youtubeAnalytics" else "v3", credentials=creds)


def channel_stats(profile, days365=365, days28=28, days7=7):
    out = {}
    yt = cli_for(profile, "youtube")
    ch = yt.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()["items"][0]
    st = ch["statistics"]
    out["id"] = ch["id"]
    out["title"] = ch["snippet"]["title"]
    out["subs"] = int(st.get("subscriberCount", 0))
    out["videos"] = int(st.get("videoCount", 0))
    out["views"] = int(st.get("viewCount", 0))
    try:
        ya = cli_for(profile, "youtubeAnalytics")

        def watch(ndays):
            end = date.today() - timedelta(days=1)
            start = end - timedelta(days=ndays - 1)
            r = ya.reports().query(
                ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
                metrics="estimatedMinutesWatched,views,averageViewDuration,subscribersGained",
            ).execute()
            rows = r.get("rows", []) or []
            if not rows:
                return [0.0, 0, 0.0, 0]
            row = rows[0]
            return [float(row[0]) if len(row) > 0 else 0.0,
                    int(row[1]) if len(row) > 1 else 0,
                    float(row[2]) if len(row) > 2 else 0.0,
                    int(row[3]) if len(row) > 3 else 0]

        w365 = watch(days365)
        w28 = watch(days28)
        w7 = watch(days7)
        out["hours365"] = w365[0] / 60.0
        out["hours28"] = w28[0] / 60.0
        out["hours7"] = w7[0] / 60.0
        out["views28"] = w28[1]
        out["views7"] = w7[1]
        out["avgViewSec28"] = (w28[2] / w28[1]) if w28[1] else 0.0
        out["subsGained28"] = w28[3]
        goal = profile.get("goal_hours", 4000)
        out["goal"] = goal
        out["pct"] = round(out["hours365"] / goal * 100, 1)
        out["needed"] = max(0.0, goal - out["hours365"])
        pace = out["hours7"] / 7.0  # hours/day
        out["pace_day"] = round(pace, 2)
        out["forecast_days"] = int(out["needed"] / pace) if pace > 0 else None
    except Exception as e:
        out["analytics_error"] = str(e)
    return out


def top_videos(profile, limit=10, days=28):
    yt = cli_for(profile, "youtube")
    ya = cli_for(profile, "youtubeAnalytics")
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    r = ya.reports().query(
        ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
        metrics="estimatedMinutesWatched,views,likes",
        dimensions="video", sort="-estimatedMinutesWatched", maxResults=limit,
    ).execute()
    rows = r.get("rows", [])
    if not rows:
        return []
    ids = [row[0] for row in rows]
    yt23 = build("youtube", "v3", credentials=creds_for(profile))
    res = yt23.videos().list(part="snippet,statistics", id=",".join(ids)).execute()
    by_id = {v["id"]: v for v in res.get("items", [])}
    out = []
    for row in rows:
        vid = by_id.get(row[0])
        d = {"videoId": row[0], "minutes": row[1], "views": row[2], "likes": row[3]}
        if vid:
            sn = vid["snippet"]
            d["title"] = sn["title"]
            d["published"] = sn["publishedAt"]
            d["tags"] = sn.get("tags", [])
            st = vid["statistics"]
            d["duration"] = vid.get("contentDetails", {}).get("duration", "")
            d["totalViews"] = int(st.get("viewCount", 0))
            d["commentCount"] = int(st.get("commentCount", 0))
        out.append(d)
    return out


def suggest_keywords(q, modifiers=None, arabic=True):
    import json
    import requests
    if modifiers is None:
        modifiers = ["للنوم", "للدراسة", "للتركيز", "للاطفال", "مكتوبة", "شهيرة",
                     "طويلة", "قصيرة", "بدون نت", "للمذاكرة", "قبل النوم",
                     "الصباح", "بصوت", "ياسر الدوسري", "عبد الباسط",
                     "مشاري العفاسي", "سعد الغامدي", "الشريم", "المنشاوي",
                     "أحمد العجمي", "ساعة", "ثلاث ساعات", "كامل", "جديد",
                     "حزين", "مؤثر", "نادر", "خاشعة", "راحة نفسية", "سكينة",
                     "ضيق الصدر", "القران كامل", "للقلب", "تلاوة", "2024",
                     "2025", "2026"]
    base = "https://suggestqueries.google.com/complete/search"
    pool = []
    for m in modifiers:
        try:
            rr = requests.get(base, params={"client": "youtube", "ds": "yt",
                                            "q": f"{q} {m}"}, timeout=3)
            if rr.status_code != 200:
                continue
            txt = rr.text
            if txt.startswith("window.google.ac.h(") and txt.endswith(")"):
                txt = txt[len("window.google.ac.h("):-1]
            data = json.loads(txt)
            sug = data[1] if isinstance(data, list) and len(data) > 1 else []
            for item in sug:
                val = item[0] if isinstance(item, list) and item and isinstance(item[0], str) else item
                if isinstance(val, str):
                    pool.append(val)
        except Exception:
            continue
    pool = list(dict.fromkeys(pool))
    if arabic:
        out = []
        for s in pool:
            rest = s[len(q):] if s.startswith(q) else s
            if not rest or any(0x600 <= ord(ch) <= 0x2000 for ch in rest):
                out.append(s)
        pool = out
    return pool
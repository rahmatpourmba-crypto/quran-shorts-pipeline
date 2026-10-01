# -*- coding: utf-8 -*-
"""Daily monetization-progress snapshot for YouTube (YPP thresholds).

Tracks the two numbers that unlock monetization for a Shorts channel:
    1. subscribers           (target: 1000)
    2. Shorts views / 90 days (target: 10 000 000)

Shorts views are approximated as the sum of public views on videos published
within the trailing 90 days (this channel only uploads Shorts).

Snapshot history is stored OUTSIDE the Git workspace under TG_WORK/work, so
Actions checkouts never wipe it. Safe to run daily on the self-hosted runner.
"""
import json, os, sys, time
from pathlib import Path
from datetime import datetime, timedelta, timezone

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TG = Path(os.getenv("TG_WORK", str(Path.home() / "tg_work")))
PY_MAKER = Path(os.getenv("TG_PYMAKER",
                          str(Path.home() / "tg_code" / "trend-video-maker")))
HIST = TG / "work" / "monetization_history.json"
SUBS_TARGET = 1000
SHORTS_TARGET = 10_000_000


def _latest(hist):
    e = hist.get("latest")
    if isinstance(e, dict):
        return e
    h = hist.get("history", [])
    return h[-1] if h else None


def main():
    sys.path.insert(0, str(PY_MAKER))
    from upload_yt import auth
    yt = auth(str(PY_MAKER / "token_aya.pickle"))

    ch = yt.channels().list(part="statistics,contentDetails", mine=True).execute()
    info = ch["items"][0]
    st = info["statistics"]
    subs = int(st.get("subscriberCount", 0) or 0)
    views = int(st.get("viewCount", 0) or 0)
    videos = int(st.get("videoCount", 0) or 0)
    upl = info["contentDetails"]["relatedPlaylists"]["uploads"]
    now = datetime.now(timezone.utc)

    ids, page = [], None
    while True:
        p = yt.playlistItems().list(part="contentDetails", playlistId=upl,
                                    maxResults=50, pageToken=page).execute()
        ids += [i["contentDetails"]["videoId"] for i in p.get("items", [])]
        page = p.get("nextPageToken")
        if not page:
            break
        time.sleep(0.15)

    shorts90 = videos90 = 0
    for i in range(0, len(ids), 50):
        chunk = ",".join(ids[i:i + 50])
        vv = yt.videos().list(part="snippet,statistics", id=chunk).execute()
        for v in vv.get("items", []):
            pub = v["snippet"].get("publishedAt", "")
            vc = int(v.get("statistics", {}).get("viewCount", 0) or 0)
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                continue
            if dt >= now - timedelta(days=90):
                shorts90 += vc
                videos90 += 1
        time.sleep(0.15)

    hist = {}
    try:
        hist = json.loads(HIST.read_text(encoding="utf-8"))
    except Exception:
        pass
    if not isinstance(hist, dict):
        hist = {}

    prev = _latest(hist)
    rate = days_subs = None
    if prev and isinstance(prev.get("date"), str):
        try:
            pdt = datetime.fromisoformat(prev["date"])
            gap = (now - pdt).total_seconds() / 86400.0
            if gap > 0.5:
                rate = (views - prev.get("views", views)) / gap
                srate = (subs - prev.get("subs", subs)) / gap
                if srate > 0:
                    days_subs = (SUBS_TARGET - subs) / srate
        except Exception:
            pass

    entry = {"date": now.isoformat(), "subs": subs, "views": views,
             "videos": videos, "shorts90": shorts90, "videos90": videos90,
             "daily_views_rate": round(rate) if rate is not None else None}
    hist["latest"] = entry
    h = hist.get("history", [])
    if not isinstance(h, list):
        h = []
    h.append(entry)
    hist["history"] = h[-90:]
    HIST.parent.mkdir(parents=True, exist_ok=True)
    HIST.write_text(json.dumps(hist, ensure_ascii=True), encoding="utf-8")

    print("== Monetization progress ==", flush=True)
    print(f"  subscribers: {subs:,} / {SUBS_TARGET:,} "
          f"({subs / SUBS_TARGET * 100:.1f}%)", flush=True)
    print(f"  Shorts views (90d): {shorts90:,} / {SHORTS_TARGET:,} "
          f"({shorts90 / SHORTS_TARGET * 100:.2f}%)", flush=True)
    print(f"  videos 90d: {videos90} | total: {videos} "
          f"| channel views: {views:,}", flush=True)
    if rate is not None:
        print(f"  daily view rate: {rate:,.0f}/day", flush=True)
    if days_subs is not None:
        print(f"  est. days to 1000 subs (current rate): {days_subs:.0f}", flush=True)
    print("  snapshot:", HIST, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
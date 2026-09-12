# -*- coding: utf-8 -*-
"""TrendThumbnail engine — reads top international thumbnails in the niche,
computes the dominant visual pattern (palette, contrast, text size, layout)
and returns a style that our Remotion TrendThumbnail builds from.
"""
import io
import json
import os
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import requests
from googleapiclient.discovery import build

import core
import seo

HOME = Path(__file__).resolve().parent
DATA = HOME / "data"
DATA.mkdir(exist_ok=True)

QUERIES = [
    "quran for sleep",
    "surah al mulk",
    "قرأن للنوم",
]
REGIONS = ["US", "GB", "SA", "AE", "EG", "ID"]
PER_REGION = 3
FRESH_AFTER_MIN = 60 * 10


HEAT_FIRE = 10000     # views/day (+Δ) => 🔥
HEAT_BOLT = 1000      # views/day (+Δ) => ⚡
HIST_TTL_DAYS = 7     # keep dropped-out videos in history so Δ stays computable
OWN_LOOKBACK_H = 48   # own-uploads table only shows the last 48h
KEYWORD_QUERY_LIMIT = 2
HISTORY_FILE = DATA / "trend_history.json"


def _row_from_video(it, region, kind):
    sn = it.get("snippet", {})
    st = it.get("statistics", {})
    try:
        views = int(st.get("viewCount", 0))
    except Exception:
        views = 0
    try:
        likes = int(st.get("likeCount", 0))
    except Exception:
        likes = 0
    vid = it.get("id", "")
    if isinstance(vid, dict):          # search.list wraps id
        vid = vid.get("videoId", "")
    return {"id": vid, "title": sn.get("title", ""), "channel": sn.get("channelTitle", ""),
            "region": region, "kind": kind, "views": views, "likes": likes,
            "published": sn.get("publishedAt", ""),
            "thumb_url": f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"}


def _hist_load():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _hist_save(h):
    try:
        HISTORY_FILE.write_text(json.dumps(h, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _metrics(row, prev, now):
    try:
        pub = datetime.fromisoformat((row.get("published") or "").replace("Z", "+00:00"))
    except Exception:
        pub = now
    age_d = max((now - pub).total_seconds() / 86400.0, 1 / 24.0)
    vpd = row["views"] / age_d
    d24 = None
    if prev:
        try:
            gap_h = (now - datetime.fromisoformat(prev["ts"])).total_seconds() / 3600.0
            if 0 < gap_h <= 72:
                d24 = max(0.0, (row["views"] - prev["views"])) * (24.0 / gap_h)
        except Exception:
            pass
    if age_d >= 2 and d24:
        heat = vpd * 0.6 + d24 * 0.4
    else:
        heat = vpd                      # avoid double-counting for brand-new videos
    flag = "🔥" if heat >= HEAT_FIRE else ("⚡" if heat >= HEAT_BOLT else "")
    return {"age_days": round(age_d, 1), "vpd": round(vpd, 1), "d24": round(d24, 1) if d24 else None,
            "heat": round(heat, 1), "flag": flag,
            "likepct": round(row["likes"] / row["views"] * 100, 1) if row["views"] else 0.0}


def _api_scan(profile, limit):
    """Official-API scan: mostPopular (regions) + capped keywords + own last-48h.
    Returns list of metric-rich rows, or None if the API/auth path is unavailable."""
    import pickle
    import time as _time
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    tok = Path(str(profile.get("token", "")))
    if not tok.is_absolute():
        tok = Path(__file__).resolve().parent.parent / tok
    if not tok.exists():
        return None
    creds = pickle.loads(tok.read_bytes())
    if not creds.valid:
        creds.refresh(Request())
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    now = datetime.now(timezone.utc)

    def exe(req, tries=3):
        for i in range(tries):
            try:
                return req.execute()
            except Exception:
                if i == tries - 1:
                    raise
                _time.sleep(3)

    rows, _seen = [], set()

    def add(r):
        if r["id"] and r["id"] not in _seen:
            _seen.add(r["id"])
            rows.append(r)

    for region in REGIONS:                       # 1) official trending per region
        try:
            res = exe(yt.videos().list(chart="mostPopular", regionCode=region,
                                       part="snippet,statistics", maxResults=min(24, int(limit) * 2)))
            for it in res.get("items", []):
                add(_row_from_video(it, region, "trend"))
        except Exception:
            continue

    for q in QUERIES[:KEYWORD_QUERY_LIMIT]:      # 2) real search (costly: 100 units/call)
        try:
            res = exe(yt.search().list(q=q, type="video", part="snippet",
                                       regionCode="US", maxResults=8))
            ids = [i.get("id", {}).get("videoId", "") for i in res.get("items", [])]
            ids = [i for i in ids if i]
            if ids:
                vres = exe(yt.videos().list(id=",".join(ids[:20]), part="snippet,statistics"))
                for it in vres.get("items", []):
                    add(_row_from_video(it, "US", "keyword"))
        except Exception:
            continue

    up_id = "UU" + str(profile.get("id", ""))[2:]  # 3) own last-48h uploads
    try:
        res = exe(yt.playlistItems().list(playlistId=up_id, part="snippet", maxResults=24))
        ids = [i.get("snippet", {}).get("resourceId", {}).get("videoId", "") for i in res.get("items", [])]
        ids = [i for i in ids if i]
        if ids:
            vres = exe(yt.videos().list(id=",".join(ids[:20]), part="snippet,statistics"))
            for it in vres.get("items", []):
                r = _row_from_video(it, "SELF", "own")
                r["self"] = True
                r["thumb_url"] = ""
                add(r)
    except Exception:
        pass

    if not rows:
        return None
    hist = _hist_load()
    out = []
    for r in rows:
        age_d = _metrics(r, hist.get(r["id"]), now)["age_days"]
        if r.get("self") and age_d > OWN_LOOKBACK_H / 24:
            continue                            # own table: last 48h only
        m = _metrics(r, hist.get(r["id"]), now)
        r.update(m)
        hist[r["id"]] = {"views": r["views"], "ts": now.isoformat()}
        out.append(r)
    for vid in [v for v, e in hist.items() if (now - datetime.fromisoformat(e["ts"])).days > HIST_TTL_DAYS]:
        hist.pop(vid, None)
    _hist_save(hist)
    out.sort(key=lambda r: -r["heat"])
    return out


def _thumb_url(id):
    base = f"https://i.ytimg.com/vi/{id}"
    for res in ("maxresdefault", "sddefault", "hqdefault"):
        yield f"{base}/{res}.jpg"


def _best_thumb(vid):
    for url in _thumb_url(vid["id"]):
        try:
            r = requests.get(url, timeout=12)
            if r.status_code == 200 and len(r.content) > 8000:
                return url, r.content
        except Exception:
            continue
    return None, None


def _scrape_search(q, region):
    """Scrape youtube search results for videoId+title+channel (no API quota)."""
    import re
    url = "https://www.youtube.com/results"
    params = {"search_query": q, "region": region, "sp": "EgIIBA%3D%3D"}  # sp=uploads(45d)? keep default order=relevance
    try:
        r = requests.get(url, params=params, timeout=20,
                         headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                                  "Accept-Language": "ar,en;q=0.8"})
        if r.status_code != 200:
            return []
        txt = r.text
        m = re.search(r"ytInitialData\s*=\s*(\{.*?\});", txt, re.S)
        if not m:
            m = re.search(r"var ytInitialData = (\{.*?\});</script>", txt, re.S)
        if not m:
            return []
        data = json.loads(m.group(1))
    except Exception:
        return []

    out = []
    try:
        conts = data["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"]["sectionListRenderer"]["contents"]
        for sec in conts:
            vids = sec.get("itemSectionRenderer", {}).get("contents", [])
            for it in vids:
                vr = it.get("videoRenderer")
                if not vr:
                    continue
                vid = vr.get("videoId")
                if not vid:
                    continue
                out.append({
                    "id": vid,
                    "title": vr.get("title", {}).get("runs", [{}])[0].get("text", "") if vr.get("title") else "",
                    "channel": vr.get("ownerText", {}).get("runs", [{}])[0].get("text", "") if vr.get("ownerText") else "",
                    "region": region,
                    "thumb_url": "https://i.ytimg.com/vi/%s/maxresdefault.jpg" % vid,
                })
    except Exception:
        pass
    return out


def fetch_top(profile):
    """Top recent videos per region/query via scraping (no API quota)."""
    seen, rows = set(), []
    for region in REGIONS:
        for q in QUERIES:
            try:
                hits = _scrape_search(q, region)
            except Exception:
                hits = []
            for it in hits:
                if it["id"] in seen:
                    continue
                seen.add(it["id"])
                rows.append(it)
    return rows[:50]


def _pil_image(buf):
    try:
        from PIL import Image
        return Image.open(io.BytesIO(buf)).convert("RGB")
    except Exception:
        return None


def analyze_thumbnail(buf):
    """Extract visual features from one thumbnail via numpy (no opencv)."""
    img = _pil_image(buf)
    if img is None:
        return None
    img = img.resize((128, 72))
    arr = np.asarray(img, dtype=np.float32) / 255.0  # HxWx3
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    sat = np.maximum(mx - mn, 1e-6)
    # colorfulness (Hasler-Süsstrunk style)
    rg = r - g
    yb = 0.5 * (r + g) - b
    colorfulness = float(np.sqrt(np.mean(rg * rg) + np.mean(yb * yb))) * 36.0
    np.seterr(invalid="ignore")
    # hue (vectorized through all pixels, kept 2D)
    m = mx > 0
    hue = np.zeros_like(mx)
    hue[m] = np.degrees(np.arctan2(2.0 * (r[m] - g[m]) * (r[m] - b[m]),
                                   (g[m] - b[m]) ** 2 + (r[m] - b[m]) ** 2 - (r[m] - g[m]) ** 2))
    hue = np.mod(hue, 360.0)
    smask = (sat > 0.12) & (lum > 0.06)

    def ratio(pred):
        if len(hs2d := hue[smask]) == 0:
            return 0.0
        return float(np.mean(pred(hs2d)))

    gold_ratio = ratio(lambda h: np.abs(((h + 30) % 360) - 45) < 48)
    blue_ratio = ratio(lambda h: (h >= 175) & (h <= 255))
    green_ratio = ratio(lambda h: (h >= 90) & (h < 175))
    red_ratio = ratio(lambda h: (h < 40) | (h >= 320))
    # contrast + edge density (proxy for text presence)
    gy = np.abs(r[1:, :] - r[:-1, :]) + np.abs(g[1:, :] - g[:-1, :]) + np.abs(b[1:, :] - b[:-1, :])
    gx = np.abs(r[:, 1:] - r[:, :-1]) + np.abs(g[:, 1:] - g[:, :-1]) + np.abs(b[:, 1:] - b[:, :-1])
    h1 = min(gy.shape[0], gx.shape[0])
    w1 = min(gy.shape[1], gx.shape[1])
    edge = gx[:h1, :w1] + gy[:h1, :w1]
    edge_density = float(np.mean(edge > 0.42))
    brightness = float(np.mean(lum))
    dark_ratio = float(np.mean(lum < 0.28))
    # center-focus: is subject concentrated near middle band?
    c = lum[24:48, 40:88]
    ring = lum[:24, :]
    ring = np.concatenate([ring, lum[48:, :]])
    center_bias = float((np.mean(c) - np.mean(ring)) / (np.mean(lum) + 1e-6)) if np.mean(lum) > 0.03 else 0.0
    # specular/gold accents: very bright warm pixels
    gold_accents = float(np.mean((lum > 0.72) & (sat > 0.18) & (np.abs(((hue + 30) % 360) - 45) < 38)))
    return {
        "colorfulness": round(colorfulness, 1),
        "gold_ratio": round(gold_ratio, 3),
        "blue_ratio": round(blue_ratio, 3),
        "green_ratio": round(green_ratio, 3),
        "red_ratio": round(red_ratio, 3),
        "edge_density": round(edge_density, 3),
        "brightness": round(brightness, 3),
        "dark_ratio": round(dark_ratio, 3),
        "center_bias": round(center_bias, 3),
        "gold_accents": round(gold_accents, 3),
    }


def aggregate(features):
    """Turn per-thumbnail features into a build style for TrendThumbnail."""
    if not features:
        return _default_style()
    avg = {k: sum(f[k] for f in features) / len(features) for k in features[0]}
    # dominant palette: gold/emerald are the two brand-safe winners
    warm_bias = avg["gold_ratio"] + avg["red_ratio"]
    cool_bias = avg["blue_ratio"] + avg["green_ratio"]
    palette = "gold" if warm_bias >= cool_bias else "emerald"
    if avg["dark_ratio"] > 0.45:
        contrast = "deep"
    else:
        contrast = "soft"
    # busier thumbs => smaller hook text; cleaner => big bold single phrase
    ed = avg["edge_density"]
    if ed < 0.08:
        text_scale, words = 1.0, 3
    elif ed < 0.15:
        text_scale, words = 0.85, 3
    else:
        text_scale, words = 0.75, 2
    brightness = avg["brightness"]
    if brightness < 0.18:
        glow = "strong"
    else:
        glow = "soft"
    return {
        "palette": palette,
        "contrast": contrast,
        "text_scale": round(text_scale, 2),
        "max_words": words,
        "glow": glow,
        "gold_accents": round(avg["gold_accents"], 2),
        "center_bias": round(avg["center_bias"], 2),
        "features_avg": {k: round(v, 3) for k, v in avg.items()},
    }


def _default_style():
    return {"palette": "gold", "contrast": "deep", "text_scale": 1.0,
            "max_words": 3, "glow": "strong", "gold_accents": 0.5,
            "center_bias": 0.5, "features_avg": {}}


def snapshot_path(profile=None):
    return DATA / (f"trend_{profile['id']}.json" if profile else "trend.json")


def _scraper_refresh(profile, prior, limit):
    """Fallback path: pixel-scrape + thumbnail analysis (no API quota)."""
    tops = fetch_top(profile)
    feats = {}
    for t in tops[:limit]:
        try:
            r = requests.get(t["thumb_url"], timeout=10)
            f = analyze_thumbnail(r.content) if r.status_code == 200 else None
        except Exception:
            f = None
        if f:
            t["features"] = f
            feats[t["id"]] = f
    if tops and feats:
        style = aggregate(list(feats.values()))
        out = {"fetched": datetime.now().isoformat(), "scan": "scraper",
               "top": tops[:limit], "style": style}
        try:
            snapshot_path(profile).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
        return out
    if prior and prior.get("top"):
        return prior
    return {"fetched": datetime.now().isoformat(), "scan": "scraper",
            "top": [] if not tops else tops[:limit], "style": _default_style()}


def refresh(profile, force=False, name="aya", limit=12):
    """Fetch + analyze + cache. Preferred source: official YouTube API (growth
    analytics via trend_history.json). Falls back to the thumbnail scraper when
    the API/auth path is unavailable. Returns dict {fetched, scan, top, style}."""
    snap = snapshot_path(profile)
    prior = None
    if snap.exists():
        prior = json.loads(snap.read_text(encoding="utf-8"))
    if not force and prior:
        age = datetime.now().timestamp() - snap.stat().st_mtime
        if age < FRESH_AFTER_MIN * 60:
            return prior
    try:
        rows = _api_scan(profile, limit)
    except Exception:
        rows = None
    if rows:
        feats = {}
        for t in rows[:limit]:
            if t.get("self"):
                continue
            try:
                r = requests.get(t["thumb_url"], timeout=10)
                f = analyze_thumbnail(r.content) if r.status_code == 200 else None
            except Exception:
                f = None
            if f:
                t["features"] = f
                feats[t["id"]] = f
        style = aggregate(list(feats.values())) if feats else _default_style()
        out = {"fetched": datetime.now().isoformat(), "scan": "api",
               "top": rows[:limit], "style": style}
        try:
            snap.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
        return out
    return _scraper_refresh(profile, prior, limit)


def build_props(profile, items=None, hook=None, style_over=None, name="aya"):
    """Produce props for the TrendThumbnail Remotion composition."""
    style = style_over or refresh(profile, name=name).get("style") or _default_style()
    return {"items": items or [], "hook": hook or None,
            "style": style, "date": datetime.now().strftime("%Y-%m-%d")}


if __name__ == "__main__":
    import sys
    prof = core.load_registry()["channels"].get("aya")
    dat = refresh(prof, force=("--force" in sys.argv))
    print(json.dumps({"fetched": dat["fetched"], "scan": dat.get("scan"),
                      "style": dat["style"],
                      "top_count": len(dat["top"])}, ensure_ascii=False, indent=2))
    print("-" * 108)
    print(f"{'TITLE':46} {'CHANNEL':16} {'RGN':4} {'VIEWS':>10} {'V/DAY':>9} {'Δ24h':>10} {'LIKE%':>6}  FLAG")
    print("-" * 108)
    for t in dat["top"][:15]:
        vd = t.get("vpd", "--")
        d24 = t.get("d24", "--")
        print(f"{t['title'][:45]:46} {t['channel'][:15]:16} {t.get('region','')[:4]:4} "
              f"{t.get('views', 0):>10,} {vd if isinstance(vd, (int, float)) else 0:>9,} "
              f"{d24 if isinstance(d24, (int, float)) else 0:>10,} {t.get('likepct', 0):>5.1f}  {t.get('flag', '')}")
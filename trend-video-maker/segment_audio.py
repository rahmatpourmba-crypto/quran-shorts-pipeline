# -*- coding: utf-8 -*-
"""segment_audio - ayah audio download + duration probing for the daily pipeline.

Reconstructed after trend-video-maker was lost. API surface expected by
daily_quran_fm.py / build_long.py:
    download_ayah(code, dst) -> bool
    probe_duration(src) -> float
    AUDIO_DIR  (Path)  -> trend-video-maker/content/quran_full/audio
    DUR_CACHE  (Path)  -> json cache of {code: duration_sec}
"""
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"

# Reciter selection (default = historical default). Set env QURAN_RECITER to a
# directory slug on everyayah.com/data/ (e.g. aziz_alili_128kbps).
RECITER = os.environ.get("QURAN_RECITER", "Yasser_Ad-Dussary_128kbps")
RECITER_SLUG = "".join(c if c.isalnum() or c in "._- " else "_" for c in RECITER).strip()

AUDIO_DIR = CONTENT / "quran_full" / "audio" / RECITER_SLUG
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
DUR_CACHE = CONTENT / "quran_full" / f"duration_cache_{RECITER_SLUG}.json"

BASE = f"https://everyayah.com/data/{RECITER}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def _probe_ffprobe(src: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nk=1:nw=1", str(src)],
            capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip())
    except Exception:
        return -1.0


def probe_duration(src) -> float:
    src = Path(src)
    if not src.exists():
        return -1.0
    try:
        from mutagen.mp3 import MP3
        return float(MP3(str(src)).info.length)
    except Exception:
        pass
    d = _probe_ffprobe(src)
    if d > 0:
        return d
    try:
        return max(2.0, src.stat().st_size / (128 * 1024 / 8))
    except Exception:
        return -1.0


def download_ayah(code: str, dst) -> bool:
    dst = Path(dst)
    if dst.exists() and dst.stat().st_size > 1000:
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    local = AUDIO_DIR / f"{code}.mp3"
    if local.exists() and local.stat().st_size > 1000:
        shutil.copyfile(local, dst)
        return True
    url = f"{BASE}/{code}.mp3"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as rsp:
                with open(dst, "wb") as fh:
                    shutil.copyfileobj(rsp, fh)
            if dst.exists() and dst.stat().st_size > 1000:
                return True
        except Exception:
            time.sleep(5)
    return False


def refresh_dur_cache():
    """Merge any existing cache file into memory (kept for build_long compat)."""
    return
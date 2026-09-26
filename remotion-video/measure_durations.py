# -*- coding: utf-8 -*-
"""Probe MP3 durations (cache) so the 55s block fits exactly."""
import json, subprocess, sys
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r'C:\Users\Admin\actions-runner\_work\quran-shorts-pipeline\quran-shorts-pipeline\remotion-video')
TIL = ROOT / 'public' / 'tilawat'
CACHE = ROOT / 'work' / 'dur_cache.json'

try:
    import imageio_ffmpeg
    FF = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FF = 'ffmpeg'

cache = {}
if CACHE.exists():
    try:
        cache = json.loads(CACHE.read_text(encoding='utf-8'))
    except Exception:
        cache = {}

files = sorted(TIL.glob('seg_*.mp3'))
for f in files:
    code = f.stem.replace('seg_', '')
    if code in cache:
        continue
    r = subprocess.run([FF, '-i', str(f)], capture_output=True, text=True)
    d = None
    for line in r.stderr.splitlines():
        if 'Duration:' in line:
            try:
                part = line.split('Duration:')[1].split(',')[0].strip().split(':')
                d = float(part[0])*3600 + float(part[1])*60 + float(part[2])
            except Exception:
                pass
            break
    if d and d > 0.5:
        cache[code] = round(d, 2)
    else:
        cache[code] = 4.0
    print(code, cache[code], flush=True)

CACHE.parent.mkdir(parents=True, exist_ok=True)
CACHE.write_text(json.dumps(cache, ensure_ascii=True), encoding='utf-8')
print("cache entries:", len(cache), flush=True)
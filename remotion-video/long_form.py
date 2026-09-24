# -*- coding: utf-8 -*-
"""long_form.py - Generate a 60-minute continuous Quran recitation video for sleep/peace.

Uses existing seg audio files from public/tilawat/, concatenates enough to fill
60 minutes, renders a static background (subtle zoompan) with ffmpeg, uploads to
YouTube as a long-form video that accumulates watch-hours for YPP eligibility.
"""
import json, random, subprocess, sys, time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(ROOT))
from youtube_optimizer import make_seo_title, make_seo_tags, make_seo_desc

ROOT = Path(__file__).resolve().parent
SEG_DIR = ROOT / "public" / "tilawat"
BG_PATH = ROOT / "public" / "backgrounds" / "bg8_moon.jpg"
OUT_DIR = ROOT / "out"
WORK_DIR = ROOT / "work"
STATE_PATH = WORK_DIR / "quran_fm_state.json"
TARGET_DURATION = 3600  # 60 minutes in seconds
AUDIO_BITRATE = "192k"
VIDEO_RES = "1080x1920"

sys.path.insert(0, str(ROOT.parent / "trend-video-maker"))
from upload_yt import auth, upload
from imageio_ffmpeg import get_ffmpeg_exe

FFMPEG = get_ffmpeg_exe()
TOKEN = ROOT.parent / "trend-video-maker" / "token_aya.pickle"

def probe_duration(mp3_path: Path) -> float:
    """Return audio duration in seconds (fallback 30s)."""
    r = subprocess.run([FFMPEG, "-i", str(mp3_path), "-f", "null", "-"],
                       capture_output=True, text=True)
    for line in r.stderr.split("\n"):
        if "Duration:" in line:
            try:
                h, m, s = line.split("Duration:")[1].split(",")[0].split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
            except Exception:
                return 30
    return 30

def build_long_video() -> Path | None:
    """Concatenate shuffled segs into >=60 min audio, render a video, return path."""
    segs = sorted(SEG_DIR.glob("seg_*.mp3"))
    if not segs:
        print("[long] No seg files found", flush=True)
        return None
    # Shuffle, cap at 400 files for speed
    segs = random.sample(segs, min(len(segs), 400))
    selected = []
    total = 0.0
    for seg in segs:
        d = probe_duration(seg)
        selected.append((seg, d))
        total += d
        if total >= TARGET_DURATION:
            break
    print(f"[long] {len(selected)} segs, {total:.0f}s audio selected", flush=True)

    # Write concat demuxer list (forward slashes for ffmpeg cross-platform)
    concat_list = OUT_DIR / "long_concat.txt"
    with open(concat_list, "w") as f:
        for seg, _ in selected:
            f.write(f"file '{str(seg).replace(chr(92), chr(47))}'\n")

    # Concatenate audio into one mp3 using libmp3lame
    audio_out = OUT_DIR / "long_audio.mp3"
    print("[long] Concatenating audio...", flush=True)
    subprocess.run([FFMPEG, "-f", "concat", "-safe", "0", "-i", str(concat_list),
                    "-c:a", "libmp3lame", "-b:a", "192k", "-y", str(audio_out)],
                   check=True)
    concat_list.unlink()

    # Render video: static bg + audio with very subtle zoompan
    date_str = date.today().isoformat()
    video_out = OUT_DIR / f"long_{date_str}.mp4"
    print("[long] Rendering video...", flush=True)
    cmd = [
        FFMPEG, "-loop", "1", "-i", str(BG_PATH),
        "-i", str(audio_out),
        "-filter:v",
        "zoompan=z='min(1.05,zoom+0.000005)':d=1:s=1080x1920,format=yuv420p",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-tune", "stillimage",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE,
        "-shortest", "-t", str(TARGET_DURATION),
        "-movflags", "+faststart",
        "-y", str(video_out)
    ]
    subprocess.run(cmd, check=True)
    audio_out.unlink()
    print(f"[long] Video ready: {video_out.name}", flush=True)
    return video_out

def main():
    today = date.today().isoformat()
    print(f"[long] Building long-form video for {today}", flush=True)
    video = build_long_video()
    if not video:
        print("[long] Skipping long-form upload (no audio)", flush=True)
        return

    # Determine primary language from today's state plan
    lang = "en"
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        plans = state.get("plans", {})
        if today in plans and plans[today]:
            # Infer from slot/lang if present; default en
            plan = plans[today]
            if isinstance(plan, list) and plan and "lang" in plan[0]:
                lang = plan[0]["lang"]
            elif "slot_lang" in state:
                lang = state["slot_lang"]
    except Exception:
        pass

    title = make_seo_title(lang, "Quran", 0, "")
    desc = make_seo_desc(lang, make_title(lang), "Quran")
    tags = make_seo_tags(lang)

    yt = auth(str(TOKEN))
    try:
        vid = upload(yt, video, BG_PATH, title, desc, tags=tags,
                     privacy="public", category_id=27, skip_orphans=True)
    except Exception as e:
        if "quota" in str(e).lower() or "429" in str(e) or "Uploads per day" in str(e):
            print("[long] DAILY UPLOAD QUOTA — long-form skipped (shorts already done)", flush=True)
            return
        raise
    if vid:
        print(f"[long] Uploaded: https://youtu.be/{vid}", flush=True)

if __name__ == "__main__":
    main()

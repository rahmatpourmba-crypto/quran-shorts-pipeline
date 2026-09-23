# -*- coding: utf-8 -*-
"""long_form.py - Generate a 60-minute continuous Quran recitation video for sleep/peace.

Uses existing seg audio files from public/tilawat/, concatenates enough to fill
60 minutes, renders a static background (subtle zoompan) with ffmpeg, uploads to
YouTube as a long-form video that accumulates watch-hours for YPP eligibility.
"""
import json, random, subprocess, sys, time
from datetime import date, datetime, timezone
from pathlib import Path

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

    # Concatenate audio into one mp3
    audio_out = OUT_DIR / "long_audio.mp3"
    print("[long] Concatenating audio...", flush=True)
    subprocess.run([FFMPEG, "-f", "concat", "-safe", "0", "-i", str(concat_list),
                    "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-y", str(audio_out)],
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

def make_title(lang: str) -> str:
    titles = {
        "ar":   "تلاوة القرآن الكامل | تلاوة هادئة للصيام والاستراحة",
        "fa":   "تلاوت کامل قرآن | تلاوت آرامش بخش برای خواب و تمرکز",
        "en":   "Complete Quran Recitation | Peaceful Long Tilaawah for Sleep",
        "ku":   "Quranê bi Zimanê Kurdî | Tîlavên Baran ji bo Xewnê",
        "zh":   "古兰经全文诵读 | 宁静古兰经朗诵助眠",
        "hi":   "पूरा कुरआन तिलावात | नींद और ध्यान के लिए शांत तिलावात",
    }
    return titles.get(lang, titles["en"])

def make_desc(lang: str, vid_id: str) -> str:
    cta = ("\n\n🔔 اشتراك في قناة آية آرامش ليصلك كل يوم تلاوة جديدة!\n"
           "https://youtube.com/@ayearamash")
    tags_block = ("#quran #quranrecitation #tilaawah #sleep #quranforsleep "
                  "#islam #calm #dua #meditation #peace")
    meta = (f"\n\nVideo ID: {vid_id}\n"
            f"Recited by Yasser Ad-Dussary (128kbps)\n"
            f"Duration: ~60 minutes\n"
            f"Category: Quran Recitation / Sleep Aid\n")
    return f"{make_title(lang)}\n\n{cta}\n{tags_block}{meta}"

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

    title = make_title(lang)
    desc = make_desc(lang, "")
    tags = ["quran", "quranrecitation", "tilaawah", "sleep", "quranforsleep",
            "islam", "calm", "dua", "meditation", "peace"]

    yt = auth(str(TOKEN))
vid = upload(yt, video, BG_PATH, title, desc, tags=tags,
                 privacy="public", category_id=27, skip_orphans=True)
    if vid:
        # Patch description with real vid_id
        print(f"[long] Uploaded: https://youtu.be/{vid}", flush=True)

if __name__ == "__main__":
    main()

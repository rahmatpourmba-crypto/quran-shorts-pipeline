# -*- coding: utf-8 -*-
"""Quick 55s Short maker: raw video + tilaawah audio + Arabic text (ffmpeg+PIL).
No Remotion needed — fast and robust. Usage:
    python make_short.py <raw_video> [ayah_code1,ayah_code2,...]
"""
import json, os, subprocess, sys, time, random, urllib.request
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(r'C:\Users\Admin\actions-runner\_work\quran-shorts-pipeline\quran-shorts-pipeline\remotion-video')
RAW_DIR = ROOT / 'public' / 'raw_videos'
TILAWAT_DIR = ROOT / 'public' / 'tilawat'
FONT = ROOT / 'public' / 'fonts' / 'Cairo.ttf'
TOKEN = ROOT.parent / 'trend-video-maker' / 'token_aya.pickle'
PY_MAKER = str(ROOT.parent / 'trend-video-maker')

TARGET = 55
RAW_DIR.mkdir(parents=True, exist_ok=True)
if not FONT.exists():
    os.makedirs(str(FONT.parent), exist_ok=True)
    urllib.request.urlretrieve('https://fonts.gstatic.com/s/cairo/v31/SLXgc1nY6HkvangtZmpQdkhzfH5lkSs2SgRjCAGMQ1z0hOA-W1Q.ttf', str(FONT))

def get_ffmpeg():
    import shutil
    ff = shutil.which('ffmpeg')
    if not ff:
        try:
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ff = None
    if not ff:
        print("ffmpeg not found!"); sys.exit(1)
    return ff

def probe_dur(ff, path):
    r = subprocess.run([ff, '-i', str(path)], capture_output=True, text=True)
    for line in r.stderr.splitlines():
        if 'Duration:' in line:
            try:
                d = line.split('Duration:')[1].split(',')[0].strip().split(':')
                return float(d[0])*3600 + float(d[1])*60 + float(d[2])
            except Exception: pass
    return 0

def local_audio_codes():
    return {f.stem.replace('seg_','') for f in TILAWAT_DIR.glob('seg_*.mp3') if f.stat().st_size > 1000}

def load_durs():
    cache = {}
    for p in [ROOT/'work'/'dur_cache.json',
              ROOT.parent/'trend-video-maker'/'content'/'quran_full'/'duration_cache.json']:
        if p.exists():
            try:
                cache.update(json.loads(p.read_text(encoding='utf-8')))
            except Exception:
                pass
    return cache

def pick_block(docodes=None, target=TARGET, max_ayah=14):
    codes = sorted(local_audio_codes())
    if not codes:
        print("no local tilaawat audio!"); sys.exit(1)
    DUR = load_durs()
    def dur(c): return float(DUR.get(c, 0) or max(3, len(c)/10))
    random.shuffle(codes)
    block, total, prev = [], 0.0, None
    tries = 0
    while total < target - 6 and tries < 3000:
        tries += 1
        c = codes[random.randrange(len(codes))]
        d = dur(c)
        if c == prev or (docodes and c in docodes): continue
        if d > 30: continue
        if total + d > target + 1.5: continue
        block.append(c); total += d; prev = c
    if len(block) < 2:
        block = codes[:2]
    print(f"    block dur ~ {round(total,1)}s ({len(block)} ayahs)", flush=True)
    return block

def concat_audio(ff, codes, out):
    lst = ROOT/'work'/'tilaawat_list.txt'
    lst.parent.mkdir(parents=True, exist_ok=True)
    with open(lst, 'w', encoding='utf-8') as f:
        for c in codes:
            p = TILAWAT_DIR / f'seg_{c}.mp3'
            # mp3 concat via demuxer needs same params; use file concat
            f.write(f"file '{p.as_posix()}'\n")
    subprocess.run([ff, '-y', '-f', 'concat', '-safe', '0', '-i', str(lst),
                    '-c', 'copy', str(out)], check=True, capture_output=True, timeout=120)

def make_vertical(ff, src, dst):
    subprocess.run([ff, '-y', '-i', str(src), '-an',
        '-vf', 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1',
        '-c:v', 'libx264', '-crf', '20', '-preset', 'fast', '-movflags', '+faststart', str(dst)],
        check=True, capture_output=True, timeout=180)

def loop_to(ff, src, dst, target):
    p = probe_dur(ff, src)
    if p <= 0: p = 5
    reps = max(1, int(target / p) + 1)
    subprocess.run([ff, '-y', '-stream_loop', str(reps), '-i', str(src),
                    '-c', 'copy', '-t', str(target), '-an', '-movflags', '+faststart', str(dst)],
                    check=True, capture_output=True, timeout=180)

def overlay_text_and_audio(ff, video, audio, text_png, dst):
    """Combine: looped muted video + tilaawah audio + Arabic text overlay."""
    subprocess.run([ff, '-y', '-i', str(video), '-i', str(audio),
        '-i', str(text_png),
        '-filter_complex', '[2:v]format=rgba[txt];[0:v][txt]overlay=0:1360[tv];[tv]format=yuv420p[vout];[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,atrim=0:55,apad=pad_dur=1.2[aout]',
        '-map', '[vout]', '-map', '[aout]', '-c:v', 'libx264', '-crf', '20', '-preset', 'fast',
        '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', str(dst)],
        check=True, capture_output=True, timeout=300)

def make_text_png(lines, out):
    """Render Arabic text lines to a 1080-wide overlay PNG (bottom area)."""
    from PIL import Image, ImageDraw, ImageFont
    import arabic_reshaper
    from bidi.algorithm import get_display
    W, H = 1080, 400
    img = Image.new('RGBA', (W, H), (0,0,0,0))
    d = ImageDraw.Draw(img)
    # dark translucent gradient bar
    for yy in range(H):
        alpha = int(170 * (yy / H) ** 1.2)
        d.line([(0, yy), (W, yy)], fill=(5, 7, 12, alpha))
    sizes = [78 if len(l) < 45 else 52 for l in lines]
    y = 40
    for line, sz in zip(lines, sizes):
        try:
            reshaped = get_display(arabic_reshaper.reshape(line))
        except Exception:
            reshaped = line
        f = ImageFont.truetype(str(FONT), sz)
        bbox = d.textbbox((0,0), reshaped, font=f)
        tw = bbox[2]-bbox[0]
        x = (W - tw) // 2
        d.text((x-2, y+2), reshaped, font=f, fill=(0,0,0,180))            # shadow
        d.text((x, y), reshaped, font=f, fill=(232,179,96,255))           # gold
        y += sz + int(sz * 0.35)
    img.save(str(out))
    print(f"text png saved: {out}", flush=True)

def make_thumb(ff, video_path, out_jpg, lines):
    """Send / thumbnail in the 55s stream (no extra remotion): extract frame + text."""
    from PIL import Image, ImageDraw, ImageFont
    import arabic_reshaper
    from bidi.algorithm import get_display
    frame = ROOT/'work'/'thumb_raw.jpg'
    subprocess.run([ff, '-y', '-ss', '6', '-i', str(video_path), '-frames:v', '1', '-q:v', '2', str(frame)],
                    check=True, capture_output=True, timeout=60)
    img = Image.open(frame).convert('RGB').resize((1080,1920), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines[:3]):
        try:
            reshaped = get_display(arabic_reshaper.reshape(line))
        except Exception:
            reshaped = line
        sz = 84 if len(line) < 45 else 54
        f = ImageFont.truetype(str(FONT), sz)
        bbox = d.textbbox((0,0), reshaped, font=f)
        tw = bbox[2]-bbox[0]
        yy = 1500 + i * (sz + 34)
        d.text(((1080-tw)//2-3, yy+3), reshaped, font=f, fill=(0,0,0,200))
        d.text(((1080-tw)//2, yy), reshaped, font=f, fill=(232,179,96,255))
    img.save(str(out_jpg), quality=92)
    print(f"thumb saved: {out_jpg}", flush=True)

def main():
    args = sys.argv[1:]
    if not args:
        print("usage: make_short.py <raw_video> [ayah...]"); sys.exit(1)
    src = Path(args[0]).resolve()
    if not src.exists():
        print("src missing:", src); sys.exit(1)
    ff = get_ffmpeg()
    work = ROOT/'work'; work.mkdir(exist_ok=True)

    # concurrency guard: make sure previous render not running
    lock = work/'makingshort.lock'
    if lock.exists() and (time.time() - lock.stat().st_mtime) < 1800:
        print("another make_short running, wait 10 min"); sys.exit(0)
    lock.write_text('1')

    base = src.stem
    muted = RAW_DIR / f'{base}_m.mp4'
    looped = RAW_DIR / f'{base}_l.mp4'

    print("1) vertical + strip audio", flush=True)
    make_vertical(ff, src, muted)
    print("2) loop to 55s", flush=True)
    loop_to(ff, muted, looped, TARGET)

    print("3) pick ayahs", flush=True)
    chosen = args[1].split(',') if len(args) > 1 else None
    block = chosen if chosen else pick_block()
    print("   block:", block, flush=True)

    print("4) concat tilaawah audio", flush=True)
    tilaud = work / 'tilaud.mp3'
    concat_audio(ff, block, tilaud)
    ad = probe_dur(ff, tilaud)
    print("   tilaawah audio:", round(ad,1), "s", flush=True)

    print("5) Arabic text overlay", flush=True)
    texts = build_texts(block)
    tp = work / 'text_overlay.png'
    make_text_png(texts, tp)

    print("6) composite", flush=True)
    final = OUT_DIR() / f'{base}_short.mp4'
    overlay_text_and_audio(ff, looped, tilaud, tp, final)
    print("7) thumbnail", flush=True)
    th = OUT_DIR() / f'{base}_thumb.jpg'
    make_thumb(ff, final, th, texts)

    print("FINAL:", final, final.stat().st_size, flush=True)
    print("THUMB:", th, th.stat().st_size, flush=True)
    try: lock.unlink()
    except: pass

def OUT_DIR():
    d = ROOT/'out'; d.mkdir(exist_ok=True); return d

def build_texts(block, max_secs=56):
    SEG = json.loads((ROOT/'src'/'segments.json').read_text(encoding='utf-8'))
    info = {}
    for seg in SEG:
        for j in range(seg['to'] - seg['from'] + 1):
            code = f"{seg['surah']:03d}{seg['from']+j:03d}"
            info[code] = (seg['surah_name'], seg['from']+j, seg['surah_en'])
    DUR = load_durs()
    def dur(c): return float(DUR.get(c, 0) or max(3, len(c)/10))
    titles, t = [], 0.0
    for c in block:
        n, a, en = info.get(c, ('…', 1, ''))
        if t < max_secs:
            ref = f"{n} : {a}"
            if ref not in titles:
                titles.append(ref)
        t += dur(c)
    return titles[:4]

if __name__ == '__main__':
    main()
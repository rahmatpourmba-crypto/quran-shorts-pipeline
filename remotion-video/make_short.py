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
WORKROOT = Path(os.getenv('TG_WORK', str(ROOT / 'public' / 'raw_videos')))
RAW_DIR = WORKROOT
TILAWAT_DIR = ROOT / 'public' / 'tilawat'
FONT = ROOT / 'public' / 'fonts' / 'Cairo.ttf'
TOKEN = ROOT.parent / 'trend-video-maker' / 'token_aya.pickle'
PY_MAKER = str(ROOT.parent / 'trend-video-maker')

TARGET = 55
RAW_DIR.mkdir(parents=True, exist_ok=True)

# Arabic theme phrase per surah (used on thumbnails / captions)
SURAH_THEME = {
    1: "أُمُّ الْكِتَابِ", 2: "هُدىً لِلْمُتَّقين", 3: "ثَباتُ الْقُلوبِ",
    4: "حُقوقٌ وَهُدى", 5: "حِفظُ الْعُهودِ", 6: "قُدرَةُ اللهِ فِي الْخَلقِ",
    7: "بَينَ الجَنَّةِ وَالنَّار", 8: "نَصرُ اللهِ", 9: "التَّوْبَةُ وَالرَّحمَة",
    10: "آياتٌ تُسكِنُ الْقُلوب", 11: "صَبرُ الأَنبِياء", 12: "أَحسَنُ الْقَصَصِ",
    13: "آياتٌ فِي الْغَيبِ", 14: "شُكرُ النِّعَمِ", 15: "الحِكْمَةُ وَالتَّذْكير",
    16: "النِّعَمُ تَترى", 17: "سُبحانَ الَّذي أَسرَى", 18: "حِكاياتٌ مِنَ الْغَيبِ",
    19: "رَحمَةُ اللهِ لِعِبادِه", 20: "قُرآنٌ لِلْهُدى", 21: "الرُّسُلُ وَالْبُشرى",
    22: "حَقُّ الْبَيتِ الْعَتيق", 23: "فَلاحُ الْمُؤمِنين", 24: "نورُ اللهِ وَالظُّلُمات",
    25: "الْفُرْقانُ وَالتَّنْزيل", 26: "وَحْيٌ وَرِسالات", 27: "آياتُ سُليمانَ",
    28: "قِصَّةُ مُوسى", 29: "حَقُّ الْحَقيقَة", 30: "وَعْدُ اللهِ",
    31: "حِكمَةُ لُقْمان", 32: "السَّجْدَةُ لِلْحَقّ", 33: "الأُسْوَةُ الْحَسَنَة",
    34: "شُكرُ الْمَلِكِ الشَّكور", 35: "بَديعُ السَّماواتِ", 36: "قَلْبُ الْقُرآنِ",
    37: "تَسْبيحُ الصَّافّاتِ", 38: "ذِكْرٌ مُبارَك", 39: "سيروا إِلَى الْجَنَّة",
    40: "غافِرُ الذَّنْبِ", 41: "آياتٌ مُفَصَّلَة", 42: "أَمْرُهُم شُورى",
    43: "زُخرُفُ الدُّنيا وَالْحَقّ", 44: "لَيْلَةٌ مُبارَكَة", 45: "الْحَقُّ مِنْ عِندِ الله",
    46: "الأَحْقافُ وَالْوَعْد", 47: "هُدىً وَشِفاء", 48: "فَتحٌ مُبين",
    49: "آدابُ التَّعامُلِ", 50: "الْبَعثُ وَالْحِساب", 51: "الذّارِياتُ وَالْخَلق",
    52: "الطُّورُ وَالْعَهْد", 53: "وَالنَّجْمِ إِذا هَوَى", 54: "اِقْتَرَبَتِ السَّاعَة",
    55: "فَبِأَيِّ آلاءِ رَبِّكُما", 56: "أَهلُ الْيَمينِ", 57: "الْحَديدُ وَالإيمان",
    58: "نَجْوى وَتَوْبَة", 59: "الْخَيرُ لِلْمُهاجِرين", 60: "الْوِلاءُ وَالْبَراء",
    61: "صَفُّ الْأَنصارِ", 62: "الجُمْعَةُ وَالذِّكْر", 63: "النِّفاقُ وَالْخِداع",
    64: "يَوْمُ التَّغابُنِ", 65: "حِفْظُ الأُسَرِ", 66: "تَحْصينُ الْبُيوتِ",
    67: "تَبارَكَ الْمُلْكُ", 68: "وَالقَلَمِ وَما يَسطُرون", 69: "الْحاقَّةُ الثَّقيلَة",
    70: "الْمَعارِجُ إِلَى الله", 71: "دَعْوَةُ نوحٍ", 72: "جِنٌّ سَمِعوا",
    73: "تَهَجُّدُ اللَّيْلِ", 74: "فَأَنذِرْ", 75: "يَوْمُ الْقِيامَةِ",
    76: "سُورَةُ الإِنسانِ", 77: "وَالمُرسَلاتِ عُرفًا", 78: "الْعَظيمُ النَّبَأ",
    79: "وَالنّازِعاتِ غَرقًا", 80: "ذِكْرٌ لِمَنْ شاءَ", 81: "التَّكويرُ وَالشَّمسُ",
    82: "يَوْمُ الْحِسابِ", 83: "وَيْلٌ لِلْمُطَفِّفين", 84: "اِنشَقَّتِ السَّماء",
    85: "وَالبُروجِ", 86: "وَالنَّجْمِ الطّارِق", 87: "سَبِّحِ اسْمَ رَبِّكَ الأَعلى",
    88: "حَديثُ الْغاشِيَةِ", 89: "الْفَجْرُ وَلَيالٍ عَشْر", 90: "الْبَلَدِ الأَمين",
    91: "نَفْسٌ وَما سَوّاها", 92: "وَالتَّقوى قَدَّمَها", 93: "الضُّحى",
    94: "فَإِنَّ مَعَ الْعُسرِ يُسْرًا", 95: "وَالتّينِ وَالزَّيتون", 96: "اِقْرَأْ بِاسْمِ رَبِّكَ",
    97: "لَيْلَةُ الْقَدْرِ خَيْرٌ", 98: "الْبَيِّنَةُ وَالْهُدى", 99: "الزِّلْزالُ وَالْخَير",
    100: "وَالعادِياتِ ضَبحًا", 101: "الْقارِعَةُ وَالْميزان", 102: "التَّكاثُرُ",
    103: "إِنَّ الإِنسانَ لَفي خُسْر", 104: "وَيْلٌ لِكُلِّ هُمَزَةٍ", 105: "أَصحابُ الْفيلِ",
    106: "إِيلافِ قُريشٍ", 107: "دينٌ بِلا عَمَل", 108: "أَعْطَيناكَ الْكَوْثَر",
    109: "لَكُمْ دينُكُمْ وَلِيَ دين", 110: "جاءَ نَصْرُ اللهِ", 111: "تَبَّتْ يَدا أَبي لَهَب",
    112: "قُلْ هُوَ اللهُ أَحَد", 113: "أَعوذُ بِرَبِّ الْفَلَق", 114: "أَعوذُ بِرَبِّ النّاسِ",
}

def theme_for_block(block):
    if not block:
        return "تلاوةٌ مِنَ الْقُرآنِ الْكَريم", "القرآن الكريم"
    surah = int(block[0][:3])
    return SURAH_THEME.get(surah, "تلاوةٌ مِنَ الْقُرآنِ الْكَريم"), f"سورة {surah}"

def save_json(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=True), encoding='utf-8')
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
    for p in [WORK() / 'dur_cache.json',
              ROOT / 'work' / 'dur_cache.json',
              ROOT.parent / 'trend-video-maker' / 'content' / 'quran_full' / 'duration_cache.json']:
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

def WORK():
    d = WORKROOT / 'work'; d.mkdir(parents=True, exist_ok=True)
    return d

def OUT_DIR():
    d = WORKROOT / 'out'; d.mkdir(parents=True, exist_ok=True)
    return d

def concat_audio(ff, codes, out):
    lst = WORK() / 'tilaawat_list.txt'
    with open(lst, 'w', encoding='utf-8') as f:
        for c in codes:
            p = TILAWAT_DIR / f'seg_{c}.mp3'
            f.write(f"file '{p.as_posix()}'\n")
    # re-encode so varying mp3 params produce an honest duration
    subprocess.run([ff, '-y', '-f', 'concat', '-safe', '0', '-i', str(lst),
                    '-c:a', 'libmp3lame', '-b:a', '192k', str(out)],
                   check=True, capture_output=True, timeout=240)

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

def make_thumb(ff, video_path, out_jpg, lines, theme=None, ref=None):
    """Beautiful thumbnail: smart frame + cinematic overlay + gold typography."""
    import json
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
    import arabic_reshaper
    from bidi.algorithm import get_display

    dur = probe_dur(ff, video_path) or 55
    frames = []
    for frac in (0.3, 0.5, 0.7):
        t = max(0.5, dur * frac)
        frame = WORK() / f'thumb_raw{int(frac*100)}.jpg'
        subprocess.run([ff, '-y', '-ss', str(round(t,1)), '-i', str(video_path),
                        '-frames:v', '1', '-q:v', '2', str(frame)],
                       check=True, capture_output=True, timeout=60)
        with Image.open(frame) as im:
            im = im.convert('RGB')
            g = im.convert('L').resize((64,36))
            px = list(g.getdata())
            frames.append((sum(px)/len(px), im.copy()))
    # prefer a bright, well-exposed frame (avoid black intros)
    frames.sort(key=lambda f: abs(f[0]-145))
    base = frames[0][1]

    # cover-crop to 9:16
    w, h = base.size
    th = int(w * 16 / 9)
    if h >= th:
        top = (h - th) // 2
        base = base.crop((0, top, w, top + th))
    else:
        tw = int(h * 9 / 16)
        left = (w - tw) // 2
        base = base.crop((left, 0, left + tw, h))
    base = base.resize((1080, 1920), Image.LANCZOS)
    img = base.convert('RGBA')

    # cinematic dark gradients (top & bottom) + vignette
    ov = Image.new('RGBA', img.size, (0,0,0,0))
    od = ImageDraw.Draw(ov)
    for yy in range(0, 640):
        a = int(150 * (1 - yy/640.0) ** 1.5)
        od.line([(0, yy), (1080, yy)], fill=(4, 7, 14, a))
    for yy in range(1280, 1920):
        a = int(200 * ((yy-1280)/640.0) ** 1.4)
        od.line([(0, yy), (1080, yy)], fill=(4, 7, 14, a))
    # thin gold top & bottom rules
    od.rectangle([(40, 46), (1040, 50)], fill=(211, 175, 96, 255))
    od.rectangle([(40, 1872), (1040, 1876)], fill=(211, 175, 96, 255))
    # vignette
    vig = Image.new('L', (1080//2, 1920//2), 0)
    vd = ImageDraw.Draw(vig)
    vd.ellipse([0,0,1079,1919], fill=255)
    vig = vig.resize((1080,1920))
    vig = vig.filter(ImageFilter.GaussianBlur(120))
    dark = Image.new('RGBA', img.size, (0,0,0,110))
    img = Image.composite(img, dark, vig.point(lambda p: 255 - (255-p)*36//255))
    img = Image.alpha_composite(img, ov)

    d = ImageDraw.Draw(img)
    def shape(s):
        return get_display(arabic_reshaper.reshape(s)) if s.strip() else s

    # top label
    label = shape("تلاوة قرآن — ياسر الدوسري")
    f1 = ImageFont.truetype(str(FONT), 74)
    b = d.textbbox((0,0), label, font=f1)
    d.text((1080//2 - (b[2]-b[0])//2, 178), label, font=f1,
           fill=(240, 240, 244, 255), stroke_width=4, stroke_fill=(10,12,18,255))

    # surah refs (big, gold), only first 2 fit
    y = 1280
    if theme:
        y += _draw_gold_line(d, theme, y)
        y += _draw_gold_line(d, ref or "", y, size=64)
    else:
        y = 1400
    for line in lines[:2]:
        ss = shape(line)
        if len(ss) > 40:
            fsz = 60
        elif len(ss) > 22:
            fsz = 72
        else:
            fsz = 96
        f = ImageFont.truetype(str(FONT), fsz)
        b = d.textbbox((0,0), ss, font=f)
        x = 1080//2 - (b[2]-b[0])//2
        # glow
        for dx, dy in ((-3,-3),(3,-3),(-3,3),(3,3),(0,-4),(0,4)):
            d.text((x+dx, y+dy), ss, font=f, fill=(211,175,96,150))
        d.text((x, y), ss, font=f, fill=(255, 214, 130, 255),
               stroke_width=2, stroke_fill=(30,26,16,255))
        y += fsz + 30

    img.convert('RGB').save(str(out_jpg), quality=94)
    print(f"thumb saved: {out_jpg}", flush=True)

def _cover_crop_9x16(im):
    """Cover-crop a PIL RGB image to 9:16."""
    from PIL import Image
    w, h = im.size
    th = int(w * 16 / 9)
    if h >= th:
        top = (h - th) // 2
        im = im.crop((0, top, w, top + th))
    else:
        tw = int(h * 9 / 16)
        left = (w - tw) // 2
        im = im.crop((left, 0, left + tw, h))
    return im.resize((1080, 1920), Image.LANCZOS)

def _thumb_backdrop(base_rgb):
    """Return (img, draw) with cinematic gradients + vignette + gold rules baked in."""
    from PIL import Image, ImageDraw, ImageFilter
    img = _cover_crop_9x16(base_rgb).convert('RGBA')
    ov = Image.new('RGBA', img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for yy in range(0, 640):
        a = int(150 * (1 - yy / 640.0) ** 1.5)
        od.line([(0, yy), (1080, yy)], fill=(4, 7, 14, a))
    for yy in range(1280, 1920):
        a = int(200 * ((yy - 1280) / 640.0) ** 1.4)
        od.line([(0, yy), (1080, yy)], fill=(4, 7, 14, a))
    od.rectangle([(40, 46), (1040, 50)], fill=(211, 175, 96, 255))
    od.rectangle([(40, 1872), (1040, 1876)], fill=(211, 175, 96, 255))
    vig = Image.new('L', (1080 // 2, 1920 // 2), 0)
    vd = ImageDraw.Draw(vig)
    vd.ellipse([0, 0, 1079, 1919], fill=255)
    vig = vig.resize((1080, 1920)).filter(ImageFilter.GaussianBlur(120))
    dark = Image.new('RGBA', img.size, (0, 0, 0, 110))
    img = Image.composite(img, dark, vig.point(lambda p: 255 - (255 - p) * 36 // 255))
    img = Image.alpha_composite(img, ov)
    return img, ImageDraw.Draw(img)

def _draw_top_label(d, label):
    from PIL import ImageFont
    d.text((1080 // 2 - d.textbbox((0, 0), label, font=ImageFont.truetype(str(FONT), 74))[2] // 2, 178),
           label, font=ImageFont.truetype(str(FONT), 74), fill=(240, 240, 244, 255),
           stroke_width=4, stroke_fill=(10, 12, 18, 255))

def _draw_gold_line(d, text, y, gold=(255, 214, 130, 255), glow=(211, 175, 96, 150), size=None):
    from PIL import ImageFont
    from bidi.algorithm import get_display
    import arabic_reshaper
    ss = get_display(arabic_reshaper.reshape(text)) if text.strip() else text
    if size is None:
        size = 96 if len(ss) <= 18 else (72 if len(ss) <= 34 else 54)
    f = ImageFont.truetype(str(FONT), size)
    b = d.textbbox((0, 0), ss, font=f)
    x = 1080 // 2 - (b[2] - b[0]) // 2
    for dx, dy in ((-3, -3), (3, -3), (-3, 3), (3, 3), (0, -4), (0, 4)):
        d.text((x + dx, y + dy), ss, font=f, fill=glow)
    d.text((x, y), ss, font=f, fill=gold, stroke_width=2, stroke_fill=(30, 26, 16, 255))
    return f.size + 26

def make_thumb_from_photo(photo_path, out_jpg, theme_line, ref_line):
    """Turn a USER-provided photo into a beautiful 9:16 thumb with Arabic text."""
    from PIL import Image
    import arabic_reshaper
    from bidi.algorithm import get_display
    with Image.open(photo_path) as im:
        base = im.convert('RGB')
    img, d = _thumb_backdrop(base)
    _draw_top_label(d, get_display(arabic_reshaper.reshape("تلاوة قرآن — ياسر الدوسري")))
    y = 1300
    y += _draw_gold_line(d, theme_line, y)
    y += _draw_gold_line(d, ref_line, y, size=64)
    img.convert('RGB').save(str(out_jpg), quality=94)
    print(f"user-photo thumb saved: {out_jpg}", flush=True)

def main():
    args = sys.argv[1:]
    if not args:
        print("usage: make_short.py <raw_video> [ayah...]"); sys.exit(1)
    src = Path(args[0]).resolve()
    if not src.exists():
        print("src missing:", src); sys.exit(1)
    ff = get_ffmpeg()
    work = WORK()

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
    save_json(work/'last_block.json', {'block': block})

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
    theme, ref = theme_for_block(block)
    make_thumb(ff, final, th, texts, theme, ref)

    print("FINAL:", final, final.stat().st_size, flush=True)
    print("THUMB:", th, th.stat().st_size, flush=True)
    try: lock.unlink()
    except: pass

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
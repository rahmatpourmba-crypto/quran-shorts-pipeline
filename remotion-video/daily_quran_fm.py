# -*- coding: utf-8 -*-
"""
Daily Remotion auto-upload for "آیه آرامش" — Full Quran Edition (Mushaf order).

Each day:
  • 5 Shorts  — individual ayahs (<50s audio), vertical 1080×1920
  • 1 Long    — ~10 min continuous tilaawah, vertical 1080×1920

Usage:
  python daily_quran_fm.py                # render + upload next day
  python daily_quran_fm.py --dry-run      # plan only, no render/upload
  python daily_quran_fm.py --count 1      # override number of videos (default 6)
  python daily_quran_fm.py --date 2026-09-07
  python daily_quran_fm.py --now          # upload as PUBLIC immediately
"""
import json, os, subprocess, sys, time, importlib.util
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
REMO_ROOT = ROOT                          # same dir (remotion-video)
INDEX_TS = REMO_ROOT / "src" / "index.ts"
OUT = REMO_ROOT / "out"
WORK = REMO_ROOT / "work"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
REMOTION = REMO_ROOT / "node_modules" / ".bin" / "remotion.cmd"
BUNDLE_DIR = REMO_ROOT / "build"          # prebuilt site (avoids public-copy race)
TILAWAT_DIR = REMO_ROOT / "public" / "tilawat"
SEGMENTS_SRC = REMO_ROOT / "src" / "segments.json"
TOKEN = ROOT.parent / "trend-video-maker" / "token_aya.pickle"
PY_MAKER = str(ROOT.parent / "trend-video-maker")

STATE = WORK / "quran_fm_state.json"
FPS = 30

# Everyday-configurable reciter (mirrors segment_audio, kept in sync here so
# SEO/descriptions can name the actual voice).
import os as _os
RECITER = _os.environ.get("QURAN_RECITER", "Yasser_Ad-Dussary_128kbps")
RECITER_NAME = _os.environ.get("QURAN_RECITER_NAME", "Yasser Al-Dosari")

# Quick-config for the trilingual 45-day push (9 Shorts/day in 3+3+3):
#   • each video targets ~42–45s of tilaawah → lands well under the 60s cap
#   • 3 international (EN) + 3 Arabic (AR) + 3 Persian (FA) every day
#   • every language publishes at ITS region primetime (SLOT_LANG below)
VIDEOS_PER_DAY = 9
TARGET_BLOCK_SEC = 38          # aim for ~38s of tilaawah per video
BLOCK_MAX_SEC   = 42           # hard-ish cap per block (total lands < 50s)
MAX_AYAH_PER_VIDEO = 14         # many short ayahs may be needed to hit ~38s

# Language → Middle-East-evening slots (UTC), all clustered 15:00–21:00 UTC
# = 18:30–00:30 IRST / 18:00–00:00 Saudi-Egypt. 9 slots, 3+3+3 (EN/AR/FA):
LANG_SLOTS = [
    ((15,  0), "en"),  # IRST 18:30 · EU 17:00                       — international early
    ((15, 30), "ar"),  # KSA 18:30 · Egypt 17:30                     — Arabia eve start
    ((16,  0), "fa"),  # IRST 19:30                                  — Iran eve start
    ((16, 30), "en"),  # IRST 20:00 · EU 19:30                       — international prime
    ((17,  0), "ar"),  # KSA 20:00 · Egypt 19:00 · UAE 21:00         — Arabia evening
    ((17, 30), "fa"),  # IRST 21:00                                  — Iran prime
    ((18, 30), "ar"),  # KSA 21:30 · Egypt 20:30 · UAE 22:30         — Arabia prime
    ((20,  0), "fa"),  # IRST 23:30 / Persian diaspora US morning    — Iran late
    ((21,  0), "en"),  # IRST 00:30 · US east 17:00 · US west 14:00  — international late
]
PUBLISH_SLOTS = [s for s, _ in LANG_SLOTS]
SLOT_LANG = {s: lang for s, lang in LANG_SLOTS}

# Curated vertical (9:16) backgrounds, cropped from freely-licensed imagery on
# Wikimedia Commons (CC BY/CC BY-SA/Public domain). Rotated per block so each
# Short gets a fresh vibrant backdrop behind the tilaawah.
BG_IMAGES = [
    "/backgrounds/bg1_mosque.jpg",  # golden mosque silhouette
    "/backgrounds/bg2_ocean.jpg",   # sunset over the Atlantic
    "/backgrounds/bg3_stars.jpg",   # Gazing at the Milky Way (ESO, CC BY)
    "/backgrounds/bg4_dunes.jpg",   # Mesquite sand dunes at dusk
    "/backgrounds/bg5_meadow.jpg",  # wild-flower meadow in morning light
]

# ── surah message → English thumbnail hook ────────────────────────────────────
# One trending-style English message per surah (the "پیام سوره"). Shown as the
# headline on TrendThumbnail so each Short carries a meaningful global message.
SURAH_MESSAGES = {
    "001": "The opening prayer of guidance",
    "002": "Guidance for the mindful ones",
    "003": "Trust in Allah, the Ever-Living",
    "004": "Justice for every family",
    "005": "A complete way of life",
    "006": "The one true Creator",
    "007": "Between truth and temptation",
    "008": "Victory comes from Allah",
    "009": "Mercy after repentance",
    "010": "No guidance without patience",
    "011": "Hope after the storm",
    "012": "From sorrow to glory",
    "013": "Peace in remembering Allah",
    "014": "Gratitude multiplies blessings",
    "015": "The Quran is protected",
    "016": "Countless favors of Allah",
    "017": "The night journey of light",
    "018": "Protection from trials",
    "019": "Mercy wrapped in faith",
    "020": "Patience brings calm",
    "021": "Allah hears every prayer",
    "022": "Submission opens the heart",
    "023": "Build your faith with sincerity",
    "024": "Purity is your light",
    "025": "Knowing right from wrong",
    "026": "Truth over falsehood",
    "027": "The wisdom of humility",
    "028": "Your story is in your sabr",
    "029": "Trials strengthen the soul",
    "030": "After loss comes relief",
    "031": "Wisdom for everyday life",
    "032": "Prostration brings peace",
    "033": "Trust Allah with your affairs",
    "034": "Gratitude opens doors",
    "035": "Hope in His mercy",
    "036": "The heart of the Quran",
    "037": "Guardians stand for truth",
    "038": "Patience turns pain into victory",
    "039": "Return to Him before it's late",
    "040": "He forgives those who ask",
    "041": "Revelation made clear",
    "042": "Unity in consultation",
    "043": "Worldly shine fades",
    "044": "The night of mercy",
    "045": "Every nation bears witness",
    "046": "Guidance reached your ears",
    "047": "True believers are calm",
    "048": "A clear victory is near",
    "049": "Respect before words",
    "050": "The return is to Allah",
    "051": "Everything has a purpose",
    "052": "The proof stands before you",
    "053": "Follow the revealed truth",
    "054": "Warnings are clear",
    "055": "Count every favor, then thank",
    "056": "Your deeds shape your fate",
    "057": "Iron, light, and certainty",
    "058": "Your voice is heard above",
    "059": "Hold nothing back from Him",
    "060": "Loyalty to faith",
    "061": "Say less, do more",
    "062": "Friday is a gift",
    "063": "Hypocrisy never lasts",
    "064": "Loss becomes your gain",
    "065": "Every provision has provision",
    "066": "Sincere love protects you",
    "067": "Dominion belongs to Allah",
    "068": "Good character wins",
    "069": "The inevitable will come",
    "070": "Patience climbs mountains",
    "071": "Call to Him in every era",
    "072": "Even the unseen hears",
    "073": "Night prayer calms the soul",
    "074": "Rise and warn with grace",
    "075": "The soul will know",
    "076": "Human, be grateful",
    "077": "Sent reminders, one by one",
    "078": "The great news is true",
    "079": "Every soul meets its moment",
    "080": "Never belittle a seeking heart",
    "081": "The sun will fold",
    "082": "Every deed is recorded",
    "083": "Fairness in every scale",
    "084": "Meet your Lord prepared",
    "085": "Faith survives the fire",
    "086": "The piercing star knows",
    "087": "Exalt His name, ease follows",
    "088": "Look, reflect, then thank",
    "089": "The dawn after the dark",
    "090": "The harder path is higher",
    "091": "Purify your soul, win",
    "092": "Night ends with light",
    "093": "Your Lord never left you",
    "094": "With hardship comes ease",
    "095": "Best design, remember Him",
    "096": "Read, rise, and learn",
    "097": "A night worth months",
    "098": "Clear proof, clean heart",
    "099": "Every deed makes the scale",
    "100": "The heart knows its value",
    "101": "The day of the knock",
    "102": "Less is more, reflect",
    "103": "Time is your investment",
    "104": "Backbiting steals peace",
    "105": "Plans fade, Allah's plan stays",
    "106": "Safety is a blessing, thank",
    "107": "Kindness is the real worship",
    "108": "Your good is endless",
    "109": "Your faith is your line",
    "110": "Help comes, then gratitude",
    "111": "Wealth can't hide the truth",
    "112": "One God, no equal",
    "113": "Run to Him from all harm",
    "114": "Refuge from the whisperer",
}
IRST = timezone(timedelta(hours=3, minutes=30))

WORK.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
TILAWAT_DIR.mkdir(parents=True, exist_ok=True)

# ── import segment_audio for download/probe ────────────────────────────────────
_spec = importlib.util.spec_from_file_location("segment_audio", str(ROOT.parent / "trend-video-maker" / "segment_audio.py"))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
# alias helpers
ensure_ayah_audio = _mod.download_ayah
probe_duration     = _mod.probe_duration
AUDIO_DIR          = _mod.AUDIO_DIR          # trend-video-maker/content/quran_full/audio
DUR_CACHE_PATH     = _mod.DUR_CACHE

def load_dur_cache():
    if DUR_CACHE_PATH.exists():
        try:
            return json.loads(DUR_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

DUR_CACHE = load_dur_cache()
def refresh_dur_cache():
    global DUR_CACHE
    DUR_CACHE = load_dur_cache()

def save_dur_cache():
    """Persist probed durations (per reciter) so future runs/CI never re-download
    just to plan blocks."""
    try:
        DUR_CACHE_PATH.write_text(json.dumps(DUR_CACHE, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"  warn: could not save duration cache: {e}", flush=True)

# ── load segments → flat ayah list ─────────────────────────────────────────────
ALL_SEGMENTS = json.loads(SEGMENTS_SRC.read_text(encoding="utf-8"))
FLAT = []   # list of {code, surah, surah_name, surah_en, ayah_num}
_code_set = set()
for seg in ALL_SEGMENTS:
    for j, code in enumerate(seg["ayahs"]):
        FLAT.append({
            "code": code,
            "surah": seg["surah"],
            "surah_name": seg["surah_name"],
            "surah_en": seg["surah_en"],
            "ayah_num": seg["from"] + j,
        })
        _code_set.add(code)

print(f"Loaded {len(FLAT)} ayahs from {len(ALL_SEGMENTS)} segments", flush=True)

# ── ayah text cache (loaded on demand) ────────────────────────────────────────
_TEXT_CACHE = None
def _load_texts():
    global _TEXT_CACHE
    if _TEXT_CACHE is not None:
        return _TEXT_CACHE
    cache = ROOT.parent / "trend-video-maker" / "content" / "quran_full" / "full_quran_texts.json"
    if cache.exists():
        _TEXT_CACHE = json.loads(cache.read_text(encoding="utf-8"))
        return _TEXT_CACHE
    print("WARN: full_quran_texts.json not found, building from segments.json", flush=True)
    _TEXT_CACHE = {}
    for seg in ALL_SEGMENTS:
        for j, code in enumerate(seg["ayahs"]):
            _TEXT_CACHE[code] = {
                "arabic": seg["arabic_ayahs"][j],
                "fa":     seg["fa_ayahs"][j],
                "en":     seg["en_ayahs"][j],
            }
    return _TEXT_CACHE

def get_text(code: str) -> dict:
    texts = _load_texts()
    if code in texts:
        return texts[code]
    # last resort: scan FLAT entry
    for f in FLAT:
        if f["code"] == code:
            return {"arabic": "", "fa": "", "en": ""}
    return {"arabic": "", "fa": "", "en": ""}

def make_item(flat_entry: dict) -> dict:
    t = get_text(flat_entry["code"])
    return {
        "code":      flat_entry["code"],
        "surahName": flat_entry["surah_name"],
        "surahEn":   flat_entry["surah_en"],
        "ayahNum":   flat_entry["ayah_num"],
        "arabic":    t["arabic"],
        "fa":        t.get("fa", ""),
        "en":        t["en"],
    }

# ── state ──────────────────────────────────────────────────────────────────────
def load_state():
    if STATE.exists():
        try: return json.loads(STATE.read_text(encoding="utf-8"))
        except: pass
    return {}

def save_state(state: dict):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ── crash-safe repo persistence ─────────────────────────────────────────────────
# GitHub kills jobs at the 6h wall; the terminal "Persist state" step then never
# runs and progress is lost. Instead we best-effort `git push` the state file
# (and duration cache) right after each save, using the runner's GITHUB_TOKEN.
def _push_pipeline_state():
    repo = ROOT.parent                    # repo root (remotion-video is a subdir)
    if not (repo / ".git").exists():
        return False
    env = dict(os.environ)
    files = [
        "remotion-video/work/quran_fm_state.json",
        "trend-video-maker/content/quran_full/duration_cache_aziz_alili_128kbps.json",
    ]
    for attempt in range(2):
        try:
            subprocess.run(["git", "-C", str(repo), "add", "-f"] + files,
                           env=env, capture_output=True)
            subprocess.run(
                ["git", "-C", str(repo),
                 "-c", "user.name=quran-actions[bot]",
                 "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                 "commit", "-m", "chore: persist quran pipeline state [skip ci]"],
                env=env, capture_output=True)
            push = subprocess.run(["git", "-C", str(repo), "push"], env=env,
                                  capture_output=True)
            if push.returncode == 0:
                return True
        except Exception:
            pass
        time.sleep(15)
    return False

def ayah_dur_estimate(code: str) -> float:
    """Real duration if cached, else estimate from Arabic text length (~7.5 chars/sec for Dossary)."""
    if code in DUR_CACHE and DUR_CACHE[code] > 0.1:
        return DUR_CACHE[code]
    t = get_text(code)
    n = len(t.get("arabic", ""))
    return max(2.5, n / 7.5)


def _real_dur(code: str) -> float:
    """Best-known duration for `code` with the CURRENT reciter: uses DUR_CACHE,
    else downloads to TILAWAT_DIR and probes, else estimates from text length."""
    d = DUR_CACHE.get(code, 0.0)
    if d > 0.1:
        return d
    dst = TILAWAT_DIR / f"seg_{code}.mp3"
    if not (dst.exists() and dst.stat().st_size > 1000):
        try:
            ensure_ayah_audio(code, dst)
        except Exception:
            pass
    if dst.exists() and dst.stat().st_size > 1000:
        d = probe_duration(dst)
        if d > 0:
            DUR_CACHE[code] = d
            return d
    return ayah_dur_estimate(code)

# ── viral popular-ayah pool ─────────────────────────────────────────────────────
# Curated famous, emotional ayahs (short audio => strong Shorts). Each entry is
# (code, hook_ar) where hook_ar is the Arabic phrase shown in the first seconds.
POPULAR_AYAHS = [
    ("002255", "اللَّهُ لَا إِلَهَ إِلَّا هُوَ الْحَيُّ الْقَيُّومُ"),
    ("055013", "فَبِأَيِّ آلَاءِ رَبِّكُمَا تُكَذِّبَانِ"),
    ("036001", "يس"),
    ("036002", "وَالْقُرْآنِ الْحَكِيمِ"),
    ("036027", "فَاغْفِرْ لَهُ رَبِّهِ فَجَعَلَهُ مِنَ الْمُكْرَمِينَ"),
    ("067001", "تَبَارَكَ الَّذِي بِيَدِهِ الْمُلْكُ"),
    ("094001", "أَلَمْ نَشْرَحْ لَكَ صَدْرَكَ"),
    ("094008", "وَإِلَى رَبِّكَ فَارْغَب"),
    ("103001", "وَالْعَصْرِ"),
    ("108001", "إِنَّا أَعْطَيْنَاكَ الْكَوْثَرَ"),
    ("110001", "إِذَا جَاءَ نَصْرُ اللَّهِ وَالْفَتْحُ"),
    ("112001", "قُلْ هُوَ اللَّهُ أَحَدٌ"),
    ("112004", "وَلَمْ يَكُنْ لَهُ كُفُوًا أَحَدٌ"),
    ("113001", "قُلْ أَعُوذُ بِرَبِّ الْفَلَقِ"),
    ("114001", "قُلْ أَعُوذُ بِرَبِّ النَّاسِ"),
    ("013027", "وَيَدْرَءُونَ بِالْحَسَنَةِ السَّيِّئَةَ"),
    ("013028", "أَلَا بِذِكْرِ اللَّهِ تَطْمَئِنُّ الْقُلُوبُ"),
    ("017079", "وَمِنَ اللَّيْلِ فَتَهَجَّدْ بِهِ"),
    ("048001", "إِنَّا فَتَحْنَا لَكَ فَتْحًا مُبِينًا"),
    ("048002", "لِيَغْفِرَ لَكَ اللَّهُ مَا تَقَدَّمَ مِنْ ذَنْبِكَ"),
    ("003008", "رَبَّنَا لَا تُزِغْ قُلُوبَنَا بَعْدَ إِذْ هَدَيْتَنَا"),
    ("003009", "رَبَّنَا إِنَّكَ جَامِعُ النَّاسِ لِيَوْمٍ لَا رَيْبَ فِيهِ"),
    ("039053", "قُلْ يَا عِبَادِيَ الَّذِينَ أَسْرَفُوا عَلَى أَنْفُسِهِمْ"),
    ("057002", "يُؤْتِي الْمُلْكَ مَنْ يَشَاءُ"),
    ("002152", "فَاذْكُرُونِي أَذْكُرْكُمْ"),
    ("002153", "يَا أَيُّهَا الَّذِينَ آمَنُوا اسْتَعِينُوا بِالصَّبْرِ"),
]

def _block_from_seed(code: str, max_sec: float = BLOCK_MAX_SEC) -> list:
    """Return a block of consecutive ayahs (starting at the BEGINNING of the
    surah that contains a famous `code`), sized to ~TARGET_BLOCK_SEC using
    REAL probed durations of the CURRENT reciter, so the finished video lands
    well under the 60s Shorts cap. Ayahs longer than one clip (e.g. Ayat
    al-Kursi) are skipped, and long runs never exceed the cap."""
    idx = next((k for k, f in enumerate(FLAT) if f["code"] == code), None)
    if idx is None:
        return []
    surah = FLAT[idx]["surah"]
    start = next((k for k in range(idx, -1, -1) if FLAT[k]["surah"] != surah), -1) + 1
    block, total, k = [], 0.0, start
    while k < len(FLAT) and len(block) < MAX_AYAH_PER_VIDEO:
        f = FLAT[k]
        d = _real_dur(f["code"])
        if d > 45.0:            # whole ayah longer than one Shorts clip -> skip
            k += 1
            continue
        if block and total + d > max_sec:
            break               # enough real audio for this Short
        block.append(f)
        total += d
        k += 1
    # don't return a scrap-of-an-ayah block (too little watch-time)
    return block if len(block) >= 3 else []

def _block_from_idx(start_k: int, max_sec: float = BLOCK_MAX_SEC,
                    max_ayah: int = MAX_AYAH_PER_VIDEO) -> list:
    """Consecutive block of ayahs starting at FLAT[start_k] (skip done later)."""
    block, total, k = [], 0.0, start_k
    while k < len(FLAT) and len(block) < max_ayah:
        f = FLAT[k]
        d = _real_dur(f["code"])
        if d > 45.0:
            k += 1
            continue
        if block and total + d > max_sec:
            break
        block.append(f)
        total += d
        k += 1
    return block

def _build_sequential(state: dict, count: int, done_codes: set) -> list:
    """Fallback: walk the whole Quran from short_cursor, take blocks of ayahs
    whose codes were never uploaded. Never repeats."""
    cursor = state.get("short_cursor", 0)
    plan, i, tried = [], cursor, 0
    if cursor >= len(FLAT):
        cursor = 0
    while len(plan) < count and tried < len(FLAT):
        if i >= len(FLAT):
            i = 0
        block = _block_from_idx(i)
        if len(block) >= 3 and not any(f["code"] in done_codes for f in block):
            hook_ar = f"{FLAT[i]['surah_name']}"
            plan.append({"slots": [(FLAT.index(f), f) for f in block],
                         "slot": None, "kind": "short", "hook": hook_ar,
                         "total_sec": sum(DUR_CACHE.get(f["code"], 0.0) for f in block)})
            i += len(block)
            tried += len(block)
        else:
            i += max(1, (len(block) if block else 1))
            tried += 1
    state["short_cursor"] = (cursor + count) % len(FLAT)
    return plan

# Short, beautiful surahs are the channel's identity: a whole such surah is one
# ~45s Short. Tried FIRST so the feed keeps delivering these gems before any
# long-surah sequential filler.
SHORT_SURAH_LIST = [93, 94, 95, 97, 99, 100, 103, 104, 105, 106, 107, 108,
                    109, 110, 111, 112, 113, 114]

_SURAH_CODES: dict = {}
for _f in FLAT:
    _SURAH_CODES.setdefault(_f["surah"], []).append(_f["code"])


def _short_surah_plan(state: dict, count: int, done_codes: set) -> list:
    """Fill plan slots from the short-surah pool (whole-surah blocks ≈ one 45s
    Short). Rotates surahs via `short_surah_cursor` and skips any surah whose
    block overlaps already-uploaded ayahs. Returns 0..count blocks."""
    cur = int(state.get("short_surah_cursor", 0))
    plan, tried = [], 0
    used_codes = set()
    while len(plan) < count and tried < len(SHORT_SURAH_LIST):
        s = SHORT_SURAH_LIST[cur % len(SHORT_SURAH_LIST)]
        cur += 1
        tried += 1
        seed = next((c for c in _SURAH_CODES.get(s, []) if c not in done_codes), None)
        if seed is None:
            continue  # whole surah already uploaded
        block = _block_from_seed(seed)
        if len(block) < 3:
            continue
        if any(f["code"] in done_codes or f["code"] in used_codes for f in block):
            continue
        plan.append({"slots": [(FLAT.index(f), f) for f in block],
                     "slot": None, "kind": "short", "hook": block[0]["surah_name"],
                     "total_sec": sum(DUR_CACHE.get(f["code"], 0.0) for f in block)})
        used_codes.update(f["code"] for f in block)
    state["short_surah_cursor"] = cur % len(SHORT_SURAH_LIST)
    return plan

def build_plan(state: dict, today: str, count: int) -> list:
    """Build a viral plan: `count` shorts, each a block of 5–6 consecutive
    ayahs starting from a famous ayah (POPULAR_AYAHS). Multi-ayah blocks get
    far better watch-time/retention than single-ayah clips.

    Rotates through POPULAR_AYAHS via `viral_cursor`, but skips any block
    whose ayahs were ALREADY uploaded (state['done']). When the popular list
    is exhausted it falls back to sequential fresh ayahs.
    """
    if count < 1:
        return []

    done_codes = set(state.get("done", []))
    cursor = state.get("viral_cursor", 0)
    # 1) fill from short beautiful surahs first (channel identity)
    plan = _short_surah_plan(state, count, done_codes)
    used_codes = {f["code"] for p in plan for _, f in p["slots"]}
    used, i = 0, cursor
    while len(plan) < count and used < len(POPULAR_AYAHS):
        code, hook_ar = POPULAR_AYAHS[i % len(POPULAR_AYAHS)]
        i += 1; used += 1
        block = _block_from_seed(code)
        if len(block) < 5:
            continue  # short/skipped ayah -> try next popular seed
        b_codes = [f["code"] for f in block]
        # reject blocks overlapping ayahs used already in this plan or in the past
        if any(c in used_codes for c in b_codes) or any(c in done_codes for c in b_codes):
            continue
        used_codes.update(b_codes)
        # ensure real audio/durations for this block
        total = 0.0
        for f in block:
            d = _real_dur(f["code"])
            total += d
        plan.append({"slots": [(FLAT.index(f), f) for f in block],
                     "slot": None, "kind": "short", "hook": hook_ar, "total_sec": total})

    # popular list exhausted -> keep the channel fresh with sequential ayahs
    if len(plan) < count:
        plan2 = _build_sequential(state, count - len(plan), done_codes)
        taken = {f["code"] for p in plan for _, f in p["slots"]}
        plan2 = [p for p in plan2 if not any(f["code"] in taken for _, f in p["slots"])]
        plan.extend(plan2)

    # assign timestamps + per-language audience
    for p, it in zip(plan, PUBLISH_SLOTS[:len(plan)]):
        p["slot"] = it
        p["lang"] = SLOT_LANG.get(it, "en")
    plan = plan[:count]

    state["viral_cursor"] = (cursor + count) % len(POPULAR_AYAHS)
    return plan

# ── SEO ────────────────────────────────────────────────────────────────────────
# Emotional rotating hooks per language + Arabic hashtags that worked on the
# winning shorts (1.2K views) targeting the huge Arabic-speaking audience.
# Proven title formula:  <emotional hook + emoji> | <surah range>
HOOK_POOL_FA = [
    "این آیه آرامش قلبت را برمی‌گرداند 🕊",
    "بگذار این آیه قلب و ذهنت را پاک کند 🌿",
    "یک لحظه آرامش با تلاوت دلنشین ✨",
    "آیه‌ای که استرس‌ات را می‌گیرد 🍃",
    "آرامش به قلب خسته 🌙",
    "صلحی برای قلب تشنه ☁️",
]

HOOK_POOL_AR = [
    "أَلَا بِذِكْرِ اللَّهِ تَطْمَئِنُّ الْقُلُوبُ 💛",
    "آيةٌ تُسكِنُ القُلوبَ 🌙",
    "سَكينةٌ لِأرواحِكم 🕊",
    "فَاذْكُرُونِي أَذْكُرْكُمْ 💛",
    "راحةٌ من همِّ الدنيا ✨",
    "داوُوا قُلوبَكُم بهذه الآية 🌿",
]

HOOK_POOL_EN = [
    "Hear what calms your heart 💛",
    "The verse that resets your mind 🕊",
    "Let these words heal your soul 🌿",
    "One minute of true peace ✨",
    "The verse that melts stress 🍃",
    "Peace for a tired heart 🌙",
]

AR_TAGS = "#القرآن_الكريم #quran #اكسبلور #الرحمن #القران #تلاوة #وَقَالَ_رَبُّكُم #quranrecitation #اللهم_صل_وسلم_على_نبينا_محمد #عبدالرحمن_عبدالصمد"
FA_TAGS = "#قرآن #تلاوت_قرآن #آیه_آرامش #یاسر_الدوسری #آرامش_قلب"
EN_TAGS = "#quran #quranrecitation #sleep #islam #calm #dua #quranforsleep #muslim #relax #peace"
KU_TAGS = "#قورئان #quran #ئارامی #خۆ" "ڕاستكان #dua #islam #کوردی"
KURDISH_SUFFIX = " · کوردی"

def _pick_hook(lang: str, code: str) -> str:
    idx = sum(ord(c) for c in code) % 6
    if lang == "en":
        return HOOK_POOL_EN[idx]
    if lang == "ar":
        return HOOK_POOL_AR[idx]
    return HOOK_POOL_FA[idx]

def _lang_title(lang: str, hook: str, ayah_range: str, code: str) -> str:
    """Localise the first part of the title for the thumbnail's language."""
    if lang == "en":
        return f"{hook} | {ayah_range} "
    if lang == "ar":
        return f"{hook} | {ayah_range} "
    if lang == "ku":
        return f"{hook} · کوردی | {ayah_range} "
    return f"{hook} | {ayah_range} "

def _lang_desc(lang: str, ref: str, ayah_ar: str, ayah_en: str) -> list:
    if lang == "en":
        return [
            ref,
            ayah_ar,
            "",
            f"\"{ayah_en}\"",
            "",
            "Peaceful Quran recitation, perfect for sleep & relaxation. "
            f"Recited by {RECITER_NAME}. 🌙",
            "",
            EN_TAGS,
            "",
            "#Shorts",
        ]
    if lang == "ar":
        return [
            ref,
            ayah_ar,
            "",
            "تلاوة بصوت الطالب یاسر الدوسري 🌙",
            "",
            f"\"{ayah_en}\"",
            "",
            AR_TAGS,
            FA_TAGS,
            "",
            "#Shorts",
        ]
    if lang == "ku":
        return [
            ref,
            ayah_ar,
            "",
            f"خوێندنی قورئان بە دەنگی {RECITER_NAME} 🌙 · {ayah_en}",
            "",
            KU_TAGS,
            "",
            "#Shorts",
        ]
    return [
        ref,
        ayah_ar,
        "",
        f"تلاوة بصوت " + RECITER_NAME + " 🌙",
        "",
        f"\"{ayah_en}\"",
        "",
        f"{ref}",
        "",
        FA_TAGS,
        "",
        "#Shorts",
    ]

def seo_block(items: list, today: str, lang: str = "en") -> tuple:
    first, last = items[0], items[-1]
    hook = _pick_hook(lang, items[0]["code"])
    surah_ar = first["surahName"]
    if first["surahEn"] != last["surahEn"]:
        ayah_range = f"{first['code'][:3]} {first['ayahNum']}–{last['code'][:3]} {last['ayahNum']}"
        desc_ref = (f"{first['surahName']} ({first['surahEn']}) آیات {first['ayahNum']} تا "
                    f"{last['surahName']} ({last['surahEn']}) آیهٔ {last['ayahNum']}")
    else:
        ayah_range = (f"{first['code'][:3]} {first['ayahNum']}" if first["ayahNum"] == last["ayahNum"]
                      else f"{first['code'][:3]} {first['ayahNum']}–{last['ayahNum']}")
        desc_ref = f"{first['surahName']} ({first['surahEn']}) {ayah_range.split()[1]}"
    title = _lang_title(lang, hook, ayah_range, first["code"][:3]).strip() + f" — تلاوة {surah_ar}"
    title = " ".join(title.split())[:95]
    en = first["en"].split('"')[0].strip()[:110]
    desc_lines = (desc_ref,) + tuple(_lang_desc(lang, desc_ref, first["arabic"], en))
    tags = ["quran", "quran recitation", "آیه آرامش", "القرآن الكريم", "تلاوة", "تلاوت قرآن"]
    return title, "\n".join(desc_lines), tags


def slot_str(slot) -> str:
    try:
        return f"{slot[0]:02d}:{slot[1]:02d}"
    except Exception:
        return str(slot)


# ── publish UTC ────────────────────────────────────────────────────────────────
# PUBLISH_SLOTS entries are (hour, minute) in UTC — publish string straight away.
def publish_utc(slot, today: str) -> str:
    h, m = (slot[0], slot[1]) if isinstance(slot, (tuple, list)) else (slot, 0)
    return f"{today}T{h:02d}:{m:02d}:00Z"

# ── render helpers ─────────────────────────────────────────────────────────────
def _remotion_cmd():
    return [str(REMOTION)]

def _write_props_file(props: dict, name: str) -> Path:
    f = WORK / f"{name}_props.json"
    f.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    return f

def master_audio(video: Path) -> bool:
    """Copyright-safe mastering pass (duration-preserving):
     1) pitch +3% (asetrate+aresample+atempo) — kills Content-ID spectral match
     2) subtle reverb/acoustic change
     3) loudnorm to -14 LUFS (YouTube target) + AAC 192k @44.1k
    Video stream is copied; audio duration is preserved, so no A/V desync.
    """
    import shutil
    ff = shutil.which("ffmpeg")
    if not ff:
        try:
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ff = None
    if not ff:
        return True  # no ffmpeg on PATH -> keep remotion mix as-is
    tmp = video.with_suffix(".master.mp4")
    try:
        rc = subprocess.run(
            [ff, "-y", "-i", str(video),
             # asetrate=44100*1.03 -> +3% pitch, then atempo restores duration
             "-af", "asetrate=45423,aresample=44100,atempo=0.97087,"
                    "aecho=0.8:0.75:40:0.25,loudnorm=I=-14:TP=-1.5:LRA=11",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
             "-movflags", "+faststart", str(tmp)],
            capture_output=True, timeout=1200).returncode
        if rc == 0 and tmp.exists() and tmp.stat().st_size > 1000:
            tmp.replace(video)
            return True
        if tmp.exists():
            tmp.unlink()
    except Exception:
        pass
    return False


def _ensure_bundle() -> bool:
    """Build (once) the Remotion site bundle into build/ so the public/
    folder (esp. ~212MB of tilawat mp3s) is copied fully BEFORE a render.
    Rendering straight from src/ copies public/ in parallel with the first
    frames, which races and 404s audio files. Rebundle only when source or
    public assets changed."""
    idx = BUNDLE_DIR / "index.html"
    if idx.exists():
        b = idx.stat().st_mtime
        fresh = True
        for base in (REMO_ROOT / "src", REMO_ROOT / "public"):
            try:
                for f in base.rglob("*"):
                    if f.is_file() and f.stat().st_mtime > b:
                        fresh = False
                        break
            except Exception:
                fresh = False
            if not fresh:
                break
        if fresh:
            return True
    log = WORK / "bundle_build.log"
    cmd = [str(REMOTION), "bundle", str(INDEX_TS), str(BUNDLE_DIR)]
    try:
        with open(log, "w", encoding="utf-8", errors="replace") as fh:
            rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                                timeout=1800, cwd=REMO_ROOT).returncode
        return rc == 0 and idx.exists()
    except Exception:
        return False


def render_video(name: str, comp: str, props: dict, out_file: Path) -> bool:
    props_file = _write_props_file(props, name)
    target = str(INDEX_TS) if not _ensure_bundle() else str(BUNDLE_DIR)
    cmd = _remotion_cmd() + ["render", target, comp, str(out_file),
                             f"--props={props_file}",
                             "--browser-executable", CHROME]
    for attempt in range(3):
        log = WORK / f"render_{name}_{attempt}.log"
        try:
            with open(log, "w", encoding="utf-8", errors="replace") as fh:
                rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                                    timeout=7200, cwd=REMO_ROOT).returncode
            if rc == 0 and out_file.exists() and out_file.stat().st_size > 0:
                master_audio(out_file)
                return True
        except Exception as e:
            import traceback
            log.write_text(traceback.format_exc(), encoding="utf-8", errors="replace")
        time.sleep(20)
    return False

def mark_thumb_props(props):
    """Merge trend-derived style into thumbnail props (never breaks the build)."""
    try:
        sys.path.insert(0, str(ROOT.parent / "channel-api"))
        import json
        import core, trend as _trend
        prof = core.load_registry()["channels"].get("aya", {})
        tprop = _trend.build_props(prof, items=props.get("items", []),
                                   hook=props.get("hook"))
        out = dict(props)
        out["style"] = tprop.get("style")
        return out
    except Exception:
        return props


_LANG_CYCLE = ["en"]  # world-language strategy: every channel English only


def next_lang_cycle() -> str:
    st = WORK / "thumb_lang.state"
    idx = 0
    try:
        idx = int(st.read_text().strip())
    except Exception:
        pass
    lang = _LANG_CYCLE[idx % len(_LANG_CYCLE)]
    try:
        st.write_text(str(idx + 1))
    except Exception:
        pass
    return lang


def render_thumb(name: str, comp: str, props: dict, out_file: Path) -> bool:
    if comp == "TrendThumbnail":
        props = mark_thumb_props(props)
        if not props.get("lang"):
            props["lang"] = next_lang_cycle()
    props_file = _write_props_file(props, name)
    target = str(INDEX_TS) if not _ensure_bundle() else str(BUNDLE_DIR)
    cmd = _remotion_cmd() + ["still", target, comp, str(out_file),
                             "--frame", "20", "--scale=2", f"--props={props_file}",
                             "--browser-executable", CHROME]
    for attempt in range(3):
        log = WORK / f"thumb_{name}_{attempt}.log"
        try:
            with open(log, "w", encoding="utf-8", errors="replace") as fh:
                rc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT,
                                    timeout=300, cwd=REMO_ROOT).returncode
            if rc == 0 and out_file.exists() and out_file.stat().st_size > 0:
                return True
        except: pass
        time.sleep(10)
    return False

# ── upload helper ──────────────────────────────────────────────────────────────
def upload_video(yt, video: Path, thumb: Path, title: str, desc: str, tags: list, publish: str | None) -> str | None:
    sys.path.insert(0, PY_MAKER)
    from upload_yt import auth, upload
    vid = None
    for attempt in range(10):
        try:
            vid = upload(yt, video, thumb if thumb.exists() else None,
                         title, desc, tags=tags,
                         privacy="public" if publish is None else "private",
                         made_for_kids=False, category_id=27,
                         publish_at=publish)
            return vid
        except Exception as e:
            err = repr(e)
            conn = isinstance(e, (ConnectionError, OSError)) or "connect" in err.lower()
            print(f"  upload retry {attempt+1}: {err} (wait {20+attempt*10}s)", flush=True)
            if attempt > 5 and not conn:
                break
            time.sleep(20 + attempt * 10)
    return None

# ── main ───────────────────────────────────────────────────────────────────────
def make_custom_bg_video(bg_image: str, yt=None, publish_day: str | None = None):
    """Render + upload ONE pending block from the daily plan using a custom
    public/ background image (Ken Burns animated). Returns video id or None.
    Safe to call next to main(): reuses the same OUT markers + state['done']."""
    today = publish_day or date.today().isoformat()
    state = load_state()
    plan = state.get("plans", {}).get(today)
    if plan is None:
        plan = build_plan(state, today, VIDEOS_PER_DAY)
        if plan:
            state.setdefault("plans", {})[today] = plan
            save_state(state)
            _push_pipeline_state()
    done_uploaded = set(state.get("done", []))
    pending = None
    for p in plan or []:
        codes = [s[1]["code"] for s in p["slots"]]
        vname = "qfm_" + codes[0] + "_" + codes[-1]
        if (OUT / f"{vname}.uploaded").exists():
            continue
        if all(c in done_uploaded for c in codes):
            continue
        pending = p
        break
    if pending is None:
        print("[custom-bg] no pending block available", flush=True)
        return None

    pairs = list(pending["slots"])
    items = [make_item(e) for _, e in pairs]
    durations = [DUR_CACHE.get(e["code"], 5.0) for _, e in pairs]
    while durations and (98 + sum(max(10, round(d * 30)) for d in durations)) / 30 >= 50:
        durations.pop(); items.pop(); pairs.pop()
    codes = [e["code"] for _, e in pairs]

    # ensure tilawat audio + durations
    for code in codes:
        dst = TILAWAT_DIR / f"seg_{code}.mp3"
        if not (dst.exists() and dst.stat().st_size > 1000):
            src = AUDIO_DIR / f"{code}.mp3"
            if src.exists() and src.stat().st_size > 1000:
                dst.write_bytes(src.read_bytes())
            else:
                ensure_ayah_audio(code, dst)
    refresh_dur_cache()
    for code in codes:
        if code not in DUR_CACHE or DUR_CACHE[code] <= 0.1:
            dst = TILAWAT_DIR / f"seg_{code}.mp3"
            if dst.exists() and dst.stat().st_size > 1000:
                d = probe_duration(dst)
                if d > 0:
                    DUR_CACHE[code] = d
    save_dur_cache()

    first, last = items[0], items[-1]
    video_name = f"qfm_{pairs[0][1]['code']}_{pairs[-1][1]['code']}"
    ref = f"{first['surahEn']} {first['ayahNum']}-{last['ayahNum']} ({len(items)} ayahs)"
    video, thumb = OUT / f"{video_name}.mp4", OUT / f"{video_name}.jpg"
    marker = OUT / f"{video_name}.uploaded"
    if marker.exists():
        print(f"[custom-bg] already uploaded {video_name}", flush=True)
        return None
    lang = pending.get("lang", "en")
    surah_msg = SURAH_MESSAGES.get(pairs[0][1]["code"][:3], "")
    props = {"items": items, "durations": durations, "hook": pending.get("hook", ""),
             "surahMsg": surah_msg, "lang": lang, "bg": "image", "bgImage": bg_image}
    print(f"[custom-bg] rendering {ref}  bg={bg_image}", flush=True)
    ok_v = render_video(video_name, "NatureDaily", props, video)
    ok_t = render_thumb(video_name, "TrendThumbnail", props, thumb) if ok_v else False
    if not ok_v or not ok_t:
        print("[custom-bg] render failed", flush=True)
        return None

    title, desc, tags = seo_block(items, today, lang=lang)
    if yt is None:
        sys.path.insert(0, PY_MAKER)
        from upload_yt import auth as yt_auth
        yt = yt_auth(TOKEN)
    print(f"[custom-bg] uploading {title}", flush=True)
    vid = upload_video(yt, video, thumb, title, desc, tags, None)
    if vid:
        marker.write_text("ok", encoding="utf-8")
        for _, e in pairs:
            if e["code"] not in state.setdefault("done", []):
                state["done"].append(e["code"])
        save_state(state)
        _push_pipeline_state()
        for f in (video, thumb):
            try:
                if f.exists():
                    f.unlink()
            except Exception:
                pass
        print(f"[custom-bg] DONE https://youtu.be/{vid}", flush=True)
        return vid
    print("[custom-bg] upload failed", flush=True)
    return None


def main():
    dry   = "--dry-run" in sys.argv
    now   = "--now" in sys.argv
    today = date.today().isoformat()
    count = VIDEOS_PER_DAY
    if "--count" in sys.argv:
        count = int(sys.argv[sys.argv.index("--count") + 1])
    publish_day = today
    if "--date" in sys.argv:
        publish_day = sys.argv[sys.argv.index("--date") + 1]
    forced_publish = None
    if "--publish-at" in sys.argv:
        forced_publish = sys.argv[sys.argv.index("--publish-at") + 1]

    if (WORK / "PAUSE_UPLOAD").exists() and not dry:
        print("PAUSE_UPLOAD is set; refusing to upload (copyright review).", flush=True)
        print("  rendered videos stay local until you delete work/PAUSE_UPLOAD", flush=True)
        return 1

    state = load_state()
    plan_key = publish_day
    plan = state.get("plans", {}).get(plan_key)

    if plan is None:
        plan = build_plan(state, today, count)
        if not dry:
            state.setdefault("plans", {})[plan_key] = plan
            save_state(state)
            _push_pipeline_state()
        print(f"plan for {plan_key}: {len(plan)} items", flush=True)
        for p in plan:
            refs = [s[1]["code"] for s in p["slots"]]
            print(f"  slot {slot_str(p['slot'])}  kind={p['kind']}  ayahs={len(refs)}", flush=True)
            print(f"    codes: {refs[:8]}{'...' if len(refs)>8 else ''}", flush=True)

    done_uploaded = set(state.get("done", []))
    remaining = []
    for p in plan:
        codes = [s[1]["code"] for s in p["slots"]]
        vname = "qfm_" + codes[0] + "_" + codes[-1]
        if (OUT / f"{vname}.uploaded").exists():
            continue
        remaining.append(p)

    if not remaining and not dry:
        # stored plan is fully uploaded (cursor wrapped) -> rebuild with fresh ayahs
        print(f"plan for {plan_key} fully used; rebuilding fresh...", flush=True)
        plan = build_plan(state, today, count)
        if not dry:
            state.setdefault("plans", {})[plan_key] = plan
            save_state(state)
            _push_pipeline_state()
        print(f"fresh plan for {plan_key}: {len(plan)} items", flush=True)
        for p in plan:
            refs = [s[1]["code"] for s in p["slots"]]
            print(f"  slot {slot_str(p['slot'])}  ayahs={len(refs)}  codes={refs[:6]}...", flush=True)
        remaining = plan if plan else []

    if not remaining:
        print(f"all done for {today}, nothing to do.", flush=True)
        return 0

    # ── ensure audio for all ayahs in plan ─────────────────────────────────────
    all_codes = set()
    for p in remaining:
        for idx, entry in p["slots"]:
            all_codes.add(entry["code"])
    if not dry:
        print(f"ensuring audio for {len(all_codes)} ayahs...", flush=True)
        for code in sorted(all_codes):
            dst = TILAWAT_DIR / f"seg_{code}.mp3"
            if dst.exists() and dst.stat().st_size > 1000:
                continue
            # try audio dir first
            src = AUDIO_DIR / f"{code}.mp3"
            if src.exists() and src.stat().st_size > 1000:
                dst.write_bytes(src.read_bytes())
                continue
            ok = ensure_ayah_audio(code, dst)
            if not ok:
                # try source dir again
                src2 = AUDIO_DIR / f"{code}.mp3"
                if src2.exists() and src2.stat().st_size > 1000:
                    dst.write_bytes(src2.read_bytes())
                    ok = True
            if not ok:
                print(f"  FAILED audio {code}", flush=True)
        # refresh durations from the local mp3s
        refresh_dur_cache()
        for code in sorted(all_codes):
            if code in DUR_CACHE and DUR_CACHE[code] > 0.1:
                continue
            dst = TILAWAT_DIR / f"seg_{code}.mp3"
            if dst.exists() and dst.stat().st_size > 1000:
                d = probe_duration(dst)
                if d > 0:
                    DUR_CACHE[code] = d
            else:
                src = AUDIO_DIR / f"{code}.mp3"
                if src.exists() and src.stat().st_size > 1000:
                    d = probe_duration(src)
                    if d > 0:
                        DUR_CACHE[code] = d
        save_dur_cache()
        _push_pipeline_state()

    # ── upload auth ────────────────────────────────────────────────────────────
    sys.path.insert(0, PY_MAKER)
    from upload_yt import auth as yt_auth
    yt = None
    if not dry:
        for attempt in range(9):
            try:
                yt = yt_auth(TOKEN)
                print("authenticated", flush=True)
                break
            except Exception as e:
                print(f"auth attempt {attempt+1}: {e} (wait 40s)", flush=True)
                time.sleep(40)
        if yt is None:
            print("AUTH FAILED", flush=True)
            return 1

    results = []
    for slot_pos, p in enumerate(remaining):
        slot = p["slot"]
        pairs = p["slots"]  # list of (idx, entry)

        # every video is a block of consecutive ayahs
        items = [make_item(e) for _, e in pairs]
        durations = [DUR_CACHE.get(e["code"], 5.0) for _, e in pairs]
        # hard cap: never exceed 50s total (NatureDaily overhead ≈ 3.3s + 0.4s/ayah)
        while durations and (98 + sum(max(10, round(d * 30)) for d in durations)) / 30 >= 50:
            durations.pop()
            items.pop()
            pairs.pop()
        first, last = items[0], items[-1]
        video_name = f"qfm_{pairs[0][1]['code']}_{pairs[-1][1]['code']}"
        ref = f"{first['surahEn']} {first['ayahNum']}-{last['ayahNum']} ({len(items)} ayahs)"

        video  = OUT / f"{video_name}.mp4"
        thumb  = OUT / f"{video_name}.jpg"
        marker = OUT / f"{video_name}.uploaded"

        stamps = slot_str(slot)
        lang = p.get("lang", "en")
        print(f"[{today}] slot {slot_pos+1}/{len(remaining)}  lang={lang}  ref={ref}  publish {stamps}", flush=True)

        if marker.exists():
            print(f"  already uploaded {marker.name}; skipping", flush=True)
            results.append((slot, ref, "skip"))
            continue

        # CI retry-safety: without .uploaded markers a re-run would otherwise
        # re-upload blocks whose ayahs are already in state['done'].
        if all(_e[1]["code"] in done_uploaded for _e in pairs):
            print(f"  all ayahs already uploaded {video_name} (done); skipping", flush=True)
            results.append((slot, ref, "skip-done"))
            continue

        if video.exists() and video.stat().st_size > 0 and thumb.exists() and thumb.stat().st_size > 0:
            print(f"  reusing {video.name}", flush=True)
            ok_v, ok_t = True, True
        elif dry:
            print(f"  [dry-run] would render block ({len(items)} ayahs) -> {video.name}", flush=True)
            ok_v, ok_t = True, True
        else:
            print(f"  rendering block ({len(items)} ayahs, {sum(durations):.0f}s)...", flush=True)
            surah_msg = SURAH_MESSAGES.get(pairs[0][1]["code"][:3], "")
            bg_img = BG_IMAGES[(slot_pos + 1) % len(BG_IMAGES)] if BG_IMAGES else ""
            props = {"items": items, "durations": durations, "hook": p.get("hook", ""), "surahMsg": surah_msg, "lang": lang, "bg": "image", "bgImage": bg_img}
            ok_v = render_video(video_name, "NatureDaily", props, video)
            ok_t = render_thumb(video_name, "TrendThumbnail", props, thumb) if ok_v else False
            if ok_v:
                print(f"  video: {video.stat().st_size:,} B", flush=True)
            if ok_t:
                print(f"  thumb: {thumb.stat().st_size:,} B", flush=True)

        if not ok_v:
            print(f"  VIDEO RENDER FAILED", flush=True)
            results.append((slot, ref, "fail-render"))
            continue

        # SEO
        title, desc, tags = seo_block(items, publish_day, lang=p.get("lang", "en"))

        if dry:
            print(f"  [dry-run] {title}", flush=True)
            results.append((slot, ref, "dry"))
            continue

        publish = None if now else (forced_publish or publish_utc(slot, publish_day))
        # if the slot time already passed (e.g. evening retry), publish immediately
        if publish and not forced_publish:
            try:
                pub_dt = datetime.fromisoformat(publish.replace("Z", "+00:00"))
                if datetime.now(timezone(timedelta(hours=0))) > pub_dt:
                    publish = None
            except Exception:
                pass
        print(f"  uploading... (publish={publish})", flush=True)
        vid = upload_video(yt, video, thumb, title, desc, tags, publish)
        if vid:
            marker.write_text("ok", encoding="utf-8")
            # mark individual codes done (tracks Quran progress)
            for _, e in pairs:
                state.setdefault("done", [])
                if e["code"] not in state["done"]:
                    state["done"].append(e["code"])
            save_state(state)
            _push_pipeline_state()
            # user rule: delete any local video after successful upload
            for f in (video, thumb):
                try:
                    if f.exists():
                        f.unlink()
                        print(f"  deleted local {f.name}", flush=True)
                except Exception as e:
                    print(f"  delete {f.name} failed: {e}", flush=True)
            print(f"  DONE https://youtu.be/{vid}", flush=True)
            results.append((slot, ref, f"ok:{vid}"))
        else:
            results.append((slot, ref, "fail-upload"))

    print("\n" + "=" * 60, flush=True)
    print(f"SUMMARY {today} ({len(results)} items)", flush=True)
    for r in results:
        print(f"  slot {slot_str(r[0])}  {r[1]:>40}  -> {r[2]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

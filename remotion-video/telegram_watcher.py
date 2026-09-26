# -*- coding: utf-8 -*-
"""Telegram watcher: takes videos posted to the channel / sent to the bot,
turns each one into a 55s Short (tilaawah voice + Arabic text, thumb from video),
uploads to YouTube (Arabic) and posts the link back to the channel.

Runs via .github/workflows/telegram-watcher.yml every 15 min (self-hosted).
"""
import json, os, subprocess, sys, time, importlib.util
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-1004354666671")
UPLIMIT = int(os.getenv("TG_DAILY_LIMIT", "3"))

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / 'public' / 'raw_videos'
WORK_DIR = ROOT / 'work'
OUT_DIR = ROOT / 'out'
RAW_DIR.mkdir(parents=True, exist_ok=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)
CURL = r'C:\Windows\System32\curl.exe'

# --- make_short module ------------------------------------------------------
_spec = importlib.util.spec_from_file_location('make_short', str(ROOT / 'make_short.py'))
MS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MS)

def log(m): print(f"[watcher] {m}", flush=True)

def tg(url_extra, timeout=60):
    import urllib.request
    with urllib.request.urlopen('https://api.telegram.org/bot' + TOKEN + url_extra, timeout=timeout) as r:
        return json.loads(r.read())

def send(url_extra, data, timeout=60):
    import urllib.request, urllib.error
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request('https://api.telegram.org/bot' + TOKEN + url_extra, data=body)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

# --- state ------------------------------------------------------------------
def load_json(p, dflt=None):
    try:
        if p.exists():
            return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        pass
    return dict(dflt) if isinstance(dflt, dict) else (list(dflt) if isinstance(dflt, list) else dflt)

def save_json(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=True), encoding='utf-8')

def get_update_offset():
    return load_json(WORK_DIR / 'offset.json', 0)

def set_update_offset(off):
    save_json(WORK_DIR / 'offset.json', off)

def get_processed():
    return set(load_json(WORK_DIR / 'processed.json', []))

def mark_processed(key):
    p = get_processed(); p.add(key)
    save_json(WORK_DIR / 'processed.json', sorted(p))

# --- fetch new videos ---------------------------------------------------------
def fetch_videos():
    off = get_update_offset()
    updates = tg('/getUpdates?timeout=10&allowed_updates=message,channel_post' +
                 (f'&offset={off}' if off else ''))
    videos = []
    max_id = off
    for u in updates.get('result', []):
        max_id = max(max_id, u['update_id'])
        m = u.get('channel_post') or u.get('message') or {}
        v = m.get('video')
        if not v:
            continue
        chat = m.get('chat', {})
        key = v.get('file_unique_id', '') or str(m.get('message_id'))
        videos.append({'key': key, 'file_id': v['file_id'], 'msg_id': m.get('message_id'),
                       'chat_id': chat.get('id'), 'duration': v.get('duration', 0),
                       'caption': m.get('caption', '') or ''})
    if max_id > off:
        set_update_offset(max_id)
    return videos

# --- download ----------------------------------------------------------------
def download(fid, dest):
    path = tg('/getFile?file_id=' + fid)['result']['file_path']
    url = 'https://api.telegram.org/file/bot' + TOKEN + '/' + path
    r = subprocess.run([CURL, '-L', '--fail', '-C', '-', '--retry', '3', '--retry-delay', '5',
                        '--max-time', '1100', '-o', str(dest), url],
                       capture_output=True, text=True, timeout=1300)
    if r.returncode != 0:
        return None, r.stderr[-200:]
    return dest, None

# --- upload + post -------------------------------------------------------------
def upload_short(final, thumb, title_base):
    sys.path.insert(0, str(ROOT.parent / 'trend-video-maker'))
    from upload_yt import auth, upload
    yt = auth(str(ROOT.parent / 'trend-video-maker' / 'token_aya.pickle'))
    title = "🎙 تلاوة قرآن | " + title_base + " — ياسر الدوسري 🌙"
    desc = ("🌙 تلاوة آيات من القرآن الكريم\n🎙 بصوت الشيخ ياسر الدوسري\n\n"
            "#القرآن_الكريم #quran #تلاوة #yasseraldossary #Shorts #الجزائر #مصري #العراق")
    try:
        vid = upload(yt, final, thumb if thumb and thumb.exists() else None, title, desc,
                     tags=['quran', 'quranrecitation', 'Shorts', 'القرآن', 'تلاوة', 'yasseraldossary'],
                     privacy='public', made_for_kids=False, category_id=27)
        return vid, None
    except Exception as e:
        return None, repr(e)[:300]

def post_channel(final, caption):
    capf = WORK_DIR / 'caption.txt'
    capf.write_text(caption, encoding='utf-8')
    pr = subprocess.run([CURL, '-sS', '--max-time', '900',
                         '-F', f'chat_id={CHAT_ID}',
                         '-F', f'caption=<{capf}', '-F', f'video=@{final}',
                         f'https://api.telegram.org/bot{TOKEN}/sendVideo'],
                        capture_output=True, text=True, timeout=950)
    return 'message_id' in (pr.stdout or '')

# --- main ------------------------------------------------------------------------
def main():
    if not TOKEN:
        log("TELEGRAM_BOT_TOKEN not set"); return 0
    videos = fetch_videos()
    if not videos:
        log("no new videos"); return 0
    done_today = len(get_processed())
    made = 0
    for v in videos:
        if v['key'] in get_processed():
            continue
        if made >= UPLIMIT:
            log(f"daily limit {UPLIMIT} reached"); break
        msg = f"video {v['msg_id']} ({v['duration']}s)"
        log("processing " + msg)
        try:
            dest = RAW_DIR / f"tg_{v['key'][:12] or v['msg_id']}.mp4"
            if dest.exists() and dest.stat().st_size < 100000:
                dest.unlink()
            dpath, err = download(v['file_id'], dest)
            if err:
                log("download failed: " + err); continue
            log("downloaded " + str(dest.stat().st_size))
            # skip tiny/non-video
            if dest.stat().st_size < 200000:
                log("file too small, skip"); continue
            sys.argv = ['make_short.py', str(dest)]
            try:
                MS.main()
            except SystemExit:
                pass
            final = OUT_DIR / (dest.stem + '_short.mp4')
            thumb = OUT_DIR / (dest.stem + '_thumb.jpg')
            if not final.exists() or final.stat().st_size < 100000:
                log("FINAL MISSING"); continue
            vid, uerr = upload_short(final, thumb, "آیه آرامش")
            if uerr:
                log("upload error: " + uerr)
                if 'quota' in uerr.lower() or '429' in uerr:
                    break
                continue
            log("uploaded https://youtu.be/" + vid)
            cap = f"🎙 تلاوة قرآن — ياسر الدوسري\n\n👉 https://youtu.be/{vid}\n\n#القرآن #تلاوة #Shorts"
            ok = post_channel(final, cap)
            log("channel post " + ("OK" if ok else "FAILED"))
            if ok:
                mark_processed(v['key'])
                made += 1
        except Exception as e:
            log("error: " + repr(e)[:250])
    log(f"done, made {made}")
    return 0

if __name__ == '__main__':
    import urllib.parse
    sys.exit(main())
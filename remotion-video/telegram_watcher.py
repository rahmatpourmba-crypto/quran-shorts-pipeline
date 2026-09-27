# -*- coding: utf-8 -*-
"""Telegram watcher: takes videos posted to the channel / sent to the bot,
turns each one into a 55s Short (Al-Dosari tilaawah voice + Arabic text),
uploads to YouTube (Arabic) and posts the link back to the channel.

- Custom thumbnail: if the user sends a PHOTO right before a video, it is
  used as the YouTube thumbnail (else a beautiful auto thumbnail is made).
- Persistent state lives OUTSIDE the Git workspace (TG_WORK) so GitHub
  Actions checkouts never wipe it.

Run: python -X utf8 telegram_watcher.py
Env:  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TG_WORK, RECOVER_CHANNEL_MSGS
"""
import json, os, subprocess, sys, time, importlib.util, urllib.parse, urllib.request
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-1004354666671")
UPLIMIT = int(os.getenv("TG_DAILY_LIMIT", "3"))
THUMB_WINDOW = int(os.getenv("TG_THUMB_WINDOW", "2400"))   # seconds a pending thumb stays fresh

ROOT = Path(__file__).resolve().parent
WORKROOT = Path(os.getenv("TG_WORK", str(Path.home() / "tg_work")))
RAW_DIR = WORKROOT / "raw"
WORK_DIR = WORKROOT / "work"
OUT_DIR = WORKROOT / "out"
for d in (RAW_DIR, WORK_DIR, OUT_DIR):
    d.mkdir(parents=True, exist_ok=True)
CURL = r'C:\Windows\System32\curl.exe'

_spec = importlib.util.spec_from_file_location('make_short', str(ROOT / 'make_short.py'))
MS = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MS)

def log(m): print(f"[watcher] {m}", flush=True)

# --- telegram helpers ---------------------------------------------------------
def tg(url_extra, timeout=60):
    with urllib.request.urlopen('https://api.telegram.org/bot' + TOKEN + url_extra, timeout=timeout) as r:
        return json.loads(r.read())

def tg_post(url_extra, data, timeout=120):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request('https://api.telegram.org/bot' + TOKEN + url_extra, data=body)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def download(fid, dest, size_hint=0):
    r = tg('/getFile?file_id=' + fid)
    if not r.get('ok'):
        return None, 'getFile error'
    path = r['result']['file_path']
    if size_hint:
        need = size_hint.get('need', 0)
    url = 'https://api.telegram.org/file/bot' + TOKEN + '/' + path
    pr = subprocess.run([CURL, '-L', '--fail', '-C', '-', '--retry', '3', '--retry-delay', '5',
                        '--max-time', '1100', '-o', str(dest), url],
                        capture_output=True, text=True, timeout=1300)
    if pr.returncode != 0 or not dest.exists() or dest.stat().st_size < 1000:
        return None, (pr.stderr or '')[-200:]
    return dest, None

# --- state ----------------------------------------------------------------------
def load_json(p, dflt):
    try:
        if p.exists():
            return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        pass
    return dflt

def save_json(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=True), encoding='utf-8')

def get_offset():
    return load_json(WORK_DIR / 'offset.json', 0)

def set_offset(off):
    save_json(WORK_DIR / 'offset.json', off)

def get_processed():
    return set(load_json(WORK_DIR / 'processed.json', []))

def mark_processed(key):
    p = get_processed(); p.add(key)
    save_json(WORK_DIR / 'processed.json', sorted(p))

def pending_thumb():
    pt = load_json(WORK_DIR / 'pending_thumb.json', None)
    if pt and isinstance(pt, dict):
        fid = pt.get('file_id')
        ts = pt.get('ts', 0)
        if fid and (time.time() - ts) < THUMB_WINDOW:
            return fid
    return None

def set_pending_thumb(fid):
    save_json(WORK_DIR / 'pending_thumb.json', {'file_id': fid, 'ts': time.time()})

# --- fetch -----------------------------------------------------------------------
def fetch_events():
    """Return (videos, lasted_photo). Consumes getUpdates queue + updates pending thumb."""
    off = get_offset()
    q = '/getUpdates?timeout=5&allowed_updates=message,channel_post'
    if off:
        q += f'&offset={off}'
    upd = tg(q)
    videos, max_id, pending_photo = [], off, None
    for u in upd.get('result', []):
        max_id = max(max_id, u['update_id'])
        m = u.get('channel_post') or u.get('message') or {}
        ph = m.get('photo')
        if ph:
            top = ph[-1]  # largest size
            pending_photo = top['file_id']
            set_pending_thumb(top['file_id'])
        v = m.get('video')
        if not v:
            continue
        chat = m.get('chat', {})
        videos.append({
            'key': v.get('file_unique_id', '') or str(m.get('message_id')),
            'file_id': v['file_id'],
            'msg_id': m.get('message_id'),
            'chat_id': chat.get('id'),
            'duration': v.get('duration', 0),
            'caption': m.get('caption', '') or '',
        })
    if max_id > off:
        set_offset(max_id)
    return videos, pending_photo

def recover_message(msid):
    """Fetch an OLD channel message (already consumed from the queue) via forwardMessage."""
    try:
        c = tg_post('/forwardMessage', {'chat_id': CHAT_ID, 'from_chat_id': CHAT_ID, 'message_id': msid})
        if not c.get('ok'):
            return None
        msg = c['result']
        v = msg.get('video')
        newid = msg.get('message_id')
        if not v:
            return None
        got = {'key': v.get('file_unique_id', f'r{msid}'), 'file_id': v['file_id'],
               'msg_id': msid, 'duration': v.get('duration', 0), 'caption': ''}
        try:
            tg_post('/deleteMessage', {'chat_id': CHAT_ID, 'message_id': newid}, timeout=20)
        except Exception:
            pass
        return got
    except Exception as e:
        log(f"recover {msid} failed: {repr(e)[:150]}")
        return None

# --- upload + post ----------------------------------------------------------------
def verify_reachable(yt):
    try:
        yt.channels().list(part="contentDetails", mine=True).execute()
        return True
    except Exception:
        return False

def recent_upload_desc(yt, limit=15):
    import time as _t
    r = yt.channels().list(part="contentDetails", mine=True).execute()
    pl = r["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    for _ in range(2):
        p = yt.playlistItems().list(part="contentDetails", playlistId=pl,
                                    maxResults=50, pageToken=page).execute()
        ids += [i["contentDetails"]["videoId"] for i in p.get("items", [])]
        page = p.get("nextPageToken")
        if not page:
            break
        _t.sleep(0.2)
    ids = ids[:limit]
    out = {}
    if ids:
        vv = yt.videos().list(part="snippet,status", id=",".join(ids)).execute()
        for v in vv.get("items", []):
            if v["status"].get("uploadStatus") == "processed":
                out[v["id"]] = v["snippet"].get("description", "")
    return out

def upload_short(final, thumb, src_marker):
    sys.path.insert(0, str(ROOT.parent / 'trend-video-maker'))
    from upload_yt import auth, upload
    yt = auth(str(ROOT.parent / 'trend-video-maker' / 'token_aya.pickle'))
    if not verify_reachable(yt):
        return None, "youtube unreachable"
    title = "🎙 تلاوة قرآن | آیه آرامش — ياسر الدوسري 🌙"
    desc = ("🌙 تلاوة آيات من القرآن الكريم\n🎙 بصوت الشيخ ياسر الدوسري\n\n"
            "src_id: " + src_marker + "\n\n"
            "#القرآن_الكريم #quran #تلاوة #yasseraldossary #Shorts #الجزائر #مصري #العراق")
    try:
        for vid, d in recent_upload_desc(yt).items():
            if src_marker and f"src_id: {src_marker}" in d:
                log("already uploaded (src_marker match), reuse " + vid)
                return vid, None
    except Exception:
        pass
    try:
        vid = upload(yt, final, thumb if thumb and Path(thumb).exists() else None, title, desc,
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

# --- one video -------------------------------------------------------------------
def process_one(v, custom_thumb=None):
    log(f"processing video {v['msg_id']} ({v['duration'] or '?'}s)")
    dest = RAW_DIR / f"tg_{v['key'][:12] or v['msg_id']}.mp4"
    dpath, err = download(v['file_id'], dest, {'need': v.get('size', 0)})
    if err:
        log("download failed: " + err)
        return False
    if dest.stat().st_size < 200000:
        log("file too small, skip")
        return False
    sys.argv = ['make_short.py', str(dest)]
    try:
        MS.main()
    except SystemExit:
        pass
    base = dest.stem
    final = OUT_DIR / f'{base}_short.mp4'
    thumb = OUT_DIR / f'{base}_thumb.jpg'
    if not final.exists() or final.stat().st_size < 100000:
        log("FINAL MISSING")
        return False
    vid, uerr = upload_short(final, custom_thumb or thumb, v['key'])
    if uerr:
        log("upload error: " + uerr)
        return 'quota' in uerr.lower() or '429' in uerr   # True => stop today

    ok = False
    if vid:
        cap = (f"🎙 تلاوة قرآن — ياسر الدوسري\n{v.get('caption','')}\n\n"
               f"👉 https://youtu.be/{vid}\n\n#القرآن #تلاوة #Shorts")
        ok = post_channel(final, cap)
        log("channel post " + ("OK" if ok else "FAILED"))
    if ok:
        mark_processed(v['key'])
    return False

# --- main ---------------------------------------------------------------------------
def main():
    if not TOKEN:
        log("TELEGRAM_BOT_TOKEN not set")
        return 0

    recv_ids = [x.strip() for x in os.getenv("RECOVER_CHANNEL_MSGS", "").split(",") if x.strip()]
    backlog = [recover_message(int(x)) for x in recv_ids]
    backlog = [x for x in backlog if x]

    events, _ = fetch_events()
    videos = []
    seen = set()
    for v in backlog + events:
        if v['key'] not in seen:
            seen.add(v['key'])
            videos.append(v)

    if not videos:
        log("no new videos")
        return 0

    custom_thumb = pending_thumb()
    made = 0
    for v in videos:
        if v['key'] in get_processed():
            continue
        if made >= UPLIMIT:
            log(f"daily limit {UPLIMIT} reached")
            break
        cthumb = custom_thumb if made == 0 else None
        try:
            stop_now = process_one(v, cthumb)
        except Exception as e:
            log("error: " + repr(e)[:250])
            stop_now = False
        if cthumb:
            save_json(WORK_DIR / 'pending_thumb.json', {})   # consumed
        if stop_now:
            log("quota hit, stopping")
            break
        made += 1
    log(f"done, made {made}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
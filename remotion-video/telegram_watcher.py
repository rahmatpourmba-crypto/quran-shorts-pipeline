# -*- coding: utf-8 -*-
"""Telegram watcher: takes videos posted to the channel / sent to the bot,
turns each one into a 55s Short (Al-Dosari tilaawah voice + Arabic text),
uploads to YouTube (Arabic) and posts the link back to the channel.

- Custom thumbnail: any PHOTO the user sends right before a video is
  downloaded, cover-cropped to 9:16 and styled with a surah-topic Arabic
  phrase (gold typography) — that becomes the YouTube thumbnail.
  Else a beautiful auto thumbnail is made from the video itself.
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
UPLIMIT = int(os.getenv("TG_DAILY_LIMIT", "1"))
THUMB_WINDOW = int(os.getenv("TG_THUMB_WINDOW", "604800"))   # seconds a pending thumb stays fresh (7d backlog)

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
def tg(url_extra, timeout=60, tries=4):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen('https://api.telegram.org/bot' + TOKEN + url_extra, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:
            last = e
            log(f"tg retry {i + 1}/{tries}: {type(e).__name__} {e}")
            time.sleep(4 * (i + 1))
    raise last

def tg_post(url_extra, data, timeout=120, tries=4):
    body = urllib.parse.urlencode(data).encode()
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request('https://api.telegram.org/bot' + TOKEN + url_extra, data=body)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:
            last = e
            log(f"tg_post retry {i + 1}/{tries}: {type(e).__name__} {e}")
            time.sleep(4 * (i + 1))
    raise last

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

def quota_until():
    q = load_json(WORK_DIR / 'quota_until.json', {})
    return float(q.get('until', 0)) if isinstance(q, dict) else 0.0

def set_quota_wait(hours=20):
    save_json(WORK_DIR / 'quota_until.json', {'until': time.time() + hours * 3600})
    log(f"youtube quota cooldown set (+{hours}h)")

def in_publish_window():
    """Gate daily publishing to the audience's golden evening hours (machine local time).
    Off unless TG_ENFORCE_WINDOW=1 (production). Supports overnight spans (e.g. 19.5-24 or 22-2)."""
    if os.getenv("TG_ENFORCE_WINDOW") != "1":
        return True
    now = time.localtime()
    cur = now.tm_hour + now.tm_min / 60.0
    start = float(os.getenv("TG_PUB_START", "19.5"))
    end = float(os.getenv("TG_PUB_END", "24.0"))
    if end < start:
        return cur >= start or cur < end
    return start <= cur < end

def get_offset():
    return load_json(WORK_DIR / 'offset.json', 0)

def set_offset(off):
    save_json(WORK_DIR / 'offset.json', off)

def get_processed():
    return set(load_json(WORK_DIR / 'processed.json', []))

def mark_processed(key):
    p = get_processed(); p.add(key)
    save_json(WORK_DIR / 'processed.json', sorted(p))

def get_inbox():
    il = load_json(WORK_DIR / 'inbox.json', [])
    return il if isinstance(il, list) else []

def save_inbox(il):
    save_json(WORK_DIR / 'inbox.json', il)

def dayfile():
    return WORK_DIR / ('day_' + time.strftime('%Y-%m-%d') + '.json')

def published_today():
    d = load_json(dayfile(), 0)
    return int(d) if isinstance(d, (int, float)) else 0

def inc_published():
    save_json(dayfile(), published_today() + 1)

def pending_thumb():
    return pop_thumb()

def push_thumb(fid, maxq=12):
    """Append a user-photo file_id to the thumbnail queue (dedup, newest only)."""
    pt = load_json(WORK_DIR / 'pending_thumb.json', {})
    if not isinstance(pt, dict):
        pt = {}
    q = pt.get('queue', [])
    if not isinstance(q, list):
        q = []
    if not any((e.get('file_id') if isinstance(e, dict) else e) == fid for e in q) and len(q) < maxq:
        q.append({'file_id': fid, 'ts': time.time()})
    save_json(WORK_DIR / 'pending_thumb.json', {'queue': q})

def pop_thumb():
    """Pop the oldest fresh queued user-photo file_id (one per video)."""
    pt = load_json(WORK_DIR / 'pending_thumb.json', {})
    if not isinstance(pt, dict):
        pt = {}
    q = pt.get('queue', [])
    if not isinstance(q, list):
        q = []
    now = time.time()

    def age(e):
        return now - (e.get('ts', 0) if isinstance(e, dict) else 0)

    fresh = [e for e in q if age(e) < THUMB_WINDOW]
    if not fresh and pt.get('file_id') and age({'ts': pt.get('ts', 0)}) < THUMB_WINDOW:
        fresh = [pt['file_id']]                        # migrate old single format
    if not fresh:
        return None
    fid = fresh[0]['file_id'] if isinstance(fresh[0], dict) else fresh[0]
    save_json(WORK_DIR / 'pending_thumb.json', {'queue': fresh[1:]})
    return fid

def peek_thumb():
    """Peek the oldest fresh queued photo without consuming it."""
    pt = load_json(WORK_DIR / 'pending_thumb.json', {})
    if not isinstance(pt, dict):
        pt = {}
    q = pt.get('queue', [])
    if not isinstance(q, list):
        q = []
    now = time.time()

    def age(e):
        return now - (e.get('ts', 0) if isinstance(e, dict) else 0)

    for e in q:
        if age(e) < THUMB_WINDOW:
            return e['file_id'] if isinstance(e, dict) else e
    if pt.get('file_id') and age({'ts': pt.get('ts', 0)}) < THUMB_WINDOW:
        return pt['file_id']
    return None

# --- fetch -----------------------------------------------------------------------
def fetch_events():
    """Consume getUpdates; append unseen videos to the durable inbox (so daily limits
    never drop videos) and queue user photos as thumbnails. Returns count of updates."""
    off = get_offset()
    q = '/getUpdates?timeout=5&allowed_updates=message,channel_post'
    if off:
        q += f'&offset={off}'
    upd = tg(q)
    max_id = off
    inbox = get_inbox()
    keys = {v['key'] for v in inbox} | get_processed()
    for u in upd.get('result', []):
        max_id = max(max_id, u['update_id'])
        m = u.get('channel_post') or u.get('message') or {}
        ph = m.get('photo')
        if ph:
            top = ph[-1]  # largest size
            push_thumb(top['file_id'])
        v = m.get('video')
        if not v:
            continue
        chat = m.get('chat', {})
        key = v.get('file_unique_id', '') or str(m.get('message_id'))
        if key in keys:
            continue
        inbox.append({
            'key': key,
            'file_id': v['file_id'],
            'msg_id': m.get('message_id'),
            'chat_id': chat.get('id'),
            'duration': v.get('duration', 0),
            'caption': m.get('caption', '') or '',
            'attempts': 0,
        })
        keys.add(key)
    if max_id > off:
        set_offset(max_id)
    save_inbox(inbox)
    return len(upd.get('result', []))

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
    for i in range(3):
        try:
            yt.channels().list(part="contentDetails", mine=True).execute()
            return True
        except Exception as e:
            log(f"yt verify retry {i + 1}/3: {type(e).__name__} {e}")
            time.sleep(6 * (i + 1))
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

PY_MAKER = Path(os.getenv('TG_PYMAKER', str(ROOT.parent / 'trend-video-maker')))

def _auth_yt():
    """OAuth auth with an explicit, actionable message if the token died."""
    sys.path.insert(0, str(PY_MAKER))
    from upload_yt import auth
    try:
        return auth(str(PY_MAKER / 'token_aya.pickle'))
    except Exception as e:
        msg = repr(e)
        if 'invalid_grant' in msg or 'revoked' in msg or 'Token has been expired' in msg:
            log("YOUTUBE AUTH EXPIRED/REVOKED — uploads blocked. Re-authorize: "
                "python -X utf8 reauth.py  (videos stay queued, nothing is lost)")
        else:
            log("youtube auth error: " + msg[:200])
        raise

def upload_short(final, thumb, src_marker, theme=None, ref=None):
    from upload_yt import upload, post_pinned_comment, create_or_get_playlist, add_to_playlist
    yt = _auth_yt()
    if not verify_reachable(yt):
        return None, "youtube unreachable"
    t = theme or "تلاوةٌ مِنَ الْقُرآنِ الْكَريم"
    title = f"«{t}» 🌙 تلاوة تجد فيها راحة القلب | ياسر الدوسري"
    desc = (f"🌙 {t}\n🎙 تلاوة القرآن بصوت الشيخ ياسر الدوسري"
            + (f"\n📖 {ref}" if ref else "")
            + "\n\nsrc_id: " + src_marker + "\n\n"
              "#القرآن_الكريم #quran #تلاوة #ياسر_الدوسري #trending #Shorts")
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
    except Exception as e:
        return None, repr(e)[:300]
    if vid:
        # convert views -> subscribers: ask + bookmark the tilaawah
        try:
            post_pinned_comment(yt, vid,
                f"🤍 سبسكرايب وفعّل الجرس 🔔 ليصلك القرآن الكريم كل يوم\n"
                f"📖 {ref} — {t}\n\n#القرآن_الكريم #ياسر_الدوسري")
        except Exception as e:
            log("pinned comment skipped: " + repr(e)[:120])
        try:
            pl = create_or_get_playlist(yt, "تلاوة قرآن | ياسر الدوسري",
                description="تلاوة مرئية فاخرة للقرآن الكريم بصوت الشيخ ياسر الدوسري", privacy="public")
            add_to_playlist(yt, pl, vid)
        except Exception as e:
            log("playlist add skipped: " + repr(e)[:120])
    return vid, None

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
def process_one(v, custom_fid=None):
    log(f"processing video {v['msg_id']} ({v['duration'] or '?'}s)")
    base = f"tg_{v['key'][:12] or v['msg_id']}"
    dest = RAW_DIR / f"{base}.mp4"
    final = OUT_DIR / f"{base}_short.mp4"
    pinned = load_json(WORK_DIR / 'pinned_blocks.json', {})
    if not isinstance(pinned, dict):
        pinned = {}
    codes = pinned.get(v['key'])
    cached = bool(codes) and final.exists() and final.stat().st_size >= 100000
    if not cached:
        dpath, err = download(v['file_id'], dest, {'need': v.get('size', 0)})
        if err:
            log("download failed: " + err)
            return (False, None)
        if dest.stat().st_size < 200000:
            log("file too small, skip")
            return (False, None)
        sys.argv = ['make_short.py', str(dest)] + ([','.join(codes)] if codes else [])
        try:
            MS.main()
        except SystemExit:
            pass
        last = load_json(MS.WORK() / 'last_block.json', None)
        if last and isinstance(last, dict) and last.get('block'):
            if v['key'] not in pinned:                 # freeze block so re-renders & theme stay identical
                pinned[v['key']] = last['block']
                save_json(WORK_DIR / 'pinned_blocks.json', pinned)
                codes = last['block']
    cust_base = cust_thumb = None
    if custom_fid:
        cust_base = OUT_DIR / f"{base}_user.jpg"
        _, cerr = download(custom_fid, cust_base)
        if cerr or not cust_base.exists() or cust_base.stat().st_size < 2000:
            log("custom photo download failed, fallback auto thumb")
            cust_base = None
    thumb = OUT_DIR / f"{base}_thumb.jpg"
    if cust_base:
        try:
            last = load_json(MS.WORK() / 'last_block.json', None)
            block = (last.get('block') if last else None) or codes
            theme, ref = MS.theme_for_block(block)
            cust_thumb = OUT_DIR / f"{base}_custom_thumb.jpg"
            MS.make_thumb_from_photo(cust_base, cust_thumb, theme, ref, block)
            thumb = cust_thumb
        except Exception as e:
            log("custom thumb build failed: " + repr(e)[:200])
    elif not thumb.exists() and final.exists():
        try:
            last = load_json(MS.WORK() / 'last_block.json', None)
            block = (last.get('block') if last else None) or codes
            ff = MS.get_ffmpeg()
            MS.make_thumb(ff, final, thumb, MS.build_texts(block), *MS.theme_for_block(block), block)
        except Exception as e:
            log("auto thumb rebuild failed: " + repr(e)[:200])
    if not final.exists() or final.stat().st_size < 100000:
        log("FINAL MISSING")
        return (False, None)
    block_for_theme = codes or (load_json(MS.WORK() / 'last_block.json', None) or {}).get('block')
    theme, ref = MS.theme_for_block(block_for_theme)
    if quota_until() > time.time():
        log("youtube quota cooldown active — upload skipped, video stays queued")
        return (True, None)
    vid, uerr = upload_short(final, thumb, v['key'], theme, ref)
    if uerr:
        log("upload error: " + uerr)
        u = uerr.lower()
        if 'quota' in u or '429' in u or 'exceeded' in u:
            set_quota_wait()
            return (True, None)               # stop today; retry after cooldown
        return (False, None)

    ok = False
    if vid:
        cap = (f"🎙 تلاوة قرآن — ياسر الدوسري\n{v.get('caption','')}\n\n"
               f"👉 https://youtu.be/{vid}\n\n#القرآن #تلاوة #Shorts")
        ok = post_channel(final, cap)
        log("channel post " + ("OK" if ok else "FAILED"))
    if ok:
        mark_processed(v['key'])
    return (False, vid)

# --- main ---------------------------------------------------------------------------
def main():
    if not TOKEN:
        log("TELEGRAM_BOT_TOKEN not set")
        return 0
    lock = WORK_DIR / 'watcher.lock'
    if lock.exists() and time.time() - lock.stat().st_mtime < 7200:
        log("another watcher instance alive recently — skip this run")
        return 0
    lock.write_text(str(time.time()))
    try:
        return _run()
    finally:
        try:
            lock.unlink()
        except Exception:
            pass

def _run():

    recv_ids = [x.strip() for x in os.getenv("RECOVER_CHANNEL_MSGS", "").split(",") if x.strip()]
    backlog = [recover_message(int(x)) for x in recv_ids]
    backlog = [x for x in backlog if x]

    try:
        fetch_events()
    except Exception as e:
        log("fetch_events failed (new messages will be caught next run): " + repr(e)[:150])

    if published_today() >= UPLIMIT:
        log(f"today's publish limit ({UPLIMIT}) already reached — nothing to do")
        return 0

    if not in_publish_window():
        log("outside publish window (evening peak active only) — waiting")
        return 0

    processed = get_processed()
    made = 0
    guard = 0
    while True:
        guard += 1
        if guard > 40:
            log("iteration guard hit, stopping")
            break
        inbox = get_inbox()
        pend = [v for v in inbox if v['key'] not in processed]
        if not pend:
            log("no new videos")
            break
        if made >= UPLIMIT:
            log(f"daily limit {UPLIMIT} reached ({len(pend)} remain in inbox)")
            break
        if quota_until() > time.time():
            log("youtube quota cooldown active — video stays queued")
            break
        v = pend[0]
        custom_fid = peek_thumb()   # one queued user photo per video, in order
        try:
            stop_now, vid = process_one(v, custom_fid)
        except Exception as e:
            log("error: " + repr(e)[:250])
            stop_now, vid = False, None
        if custom_fid is not None and vid:
            pop_thumb()             # photo only consumed once its video is live
        if vid:
            # success: drop from inbox + pin processed + count today
            save_inbox([x for x in get_inbox() if x['key'] != v['key']])
            processed = processed | {v['key']}
            mark_processed(v['key'])
            inc_published()
            made += 1
        elif stop_now:
            log("stopped (daily cap / quota) — video stays queued, retry next run")
            break
        else:
            # transient failure: keep forever, but rotate to the back after
            # 3 attempts so a stuck item never blocks the rest of the queue
            v['attempts'] = v.get('attempts', 0) + 1
            rest = [x for x in get_inbox() if x['key'] != v['key']]
            if v['attempts'] >= 3:
                v['attempts'] = 0
                rest.append(v)
                log(f"video {v['msg_id']} moved to back of queue (3 failed attempts)")
            else:
                rest.insert(0, v)
            save_inbox(rest)
            if made <= 0:
                break   # avoid a retry storm inside a single run
    log(f"done, made {made}")
    return 0

if __name__ == '__main__':
    sys.exit(main())
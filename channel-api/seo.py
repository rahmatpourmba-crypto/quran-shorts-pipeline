# -*- coding: utf-8 -*-
"""SEO scoring (mirrors extension), keyword difficulty, title/desc/tags generator."""
import re

import core


def score_title(title, tags):
    s = 0
    if not title:
        return 0
    n = len(title)
    if 40 <= n <= 60:
        s += 10
    elif 30 <= n <= 70:
        s += 7
    elif 20 <= n <= 80:
        s += 4
    else:
        s += 1
    if tags:
        tl = title.lower()
        if any(t.lower() in tl for t in tags):
            s += 8
    if re.search(r"[A-Z]", title) and re.search(r"[a-z]", title):
        s += 2
    if re.search(r"\d", title):
        s += 2
    if re.search(r"[!?؟]", title):
        s += 1
    if re.search(r"[|\-–]", title):
        s += 1
    return min(s, 25)


def score_description(desc):
    s = 0
    if not desc:
        return 0
    n = len(desc)
    if n >= 500:
        s += 10
    elif n >= 200:
        s += 7
    elif n >= 100:
        s += 4
    else:
        s += 1
    if re.search(r"https?://", desc):
        s += 3
    if re.search(r"\d+:\d+", desc):
        s += 3
    if desc.count("\n") >= 5:
        s += 2
    if re.search(r"#[\w\u0600-\u06FF]+", desc):
        s += 2
    return min(s, 20)


def score_tags(tags):
    s = 0
    if not tags:
        return 0
    if len(tags) >= 10:
        s += 8
    elif len(tags) >= 5:
        s += 5
    elif len(tags) >= 1:
        s += 2
    s += 4 if len(tags) <= 30 else 2
    if tags:
        avg = sum(len(t) for t in tags) / len(tags)
        if 3 <= avg <= 25:
            s += 4
    if any(len(t.split()) >= 2 for t in tags):
        s += 4
    return min(s, 20)


def score_thumbnail(thumb):
    s = 0
    if not thumb:
        return 0
    s += 8
    if "maxresdefault" in thumb or "sddefault" in thumb:
        s += 4
    elif "hqdefault" in thumb:
        s += 3
    elif "mqdefault" in thumb:
        s += 1
    if "ytimg.com" in thumb:
        s += 3
    return min(s, 15)


def score_engagement(views):
    s = 0
    if not views:
        return 0
    if views > 1_000_000:
        s += 8
    elif views > 100_000:
        s += 6
    elif views > 10_000:
        s += 4
    elif views > 1_000:
        s += 2
    else:
        s += 1
    return min(s, 20)


def analyze(video):
    t = score_title(video.get("title"), video.get("tags"))
    d = score_description(video.get("description"))
    g = score_tags(video.get("tags"))
    th = score_thumbnail(video.get("thumbnail"))
    e = score_engagement(video.get("views"))
    total = t + d + g + th + e
    grade = ("A+" if total >= 80 else "A" if total >= 70 else "B+" if total >= 60 else
             "B" if total >= 50 else "C+" if total >= 40 else "C" if total >= 30 else
             "D" if total >= 20 else "F")
    tips = []
    if t < 15:
        tips.append("عنوان 50-60 کاراکتری با کلمه کلیدی اصلی داخل عبارت")
    if d < 10:
        tips.append("توضیحات ≥500 کاراکتر با لینک، تایم‌استمپ و هشتگ‌ها")
    if g < 10:
        tips.append("۱۰ تا ۱۵ تگ عبارت‌بلند مرتبط اضافه کنید")
    if th < 8:
        tips.append("تامبنیل maxresdefault با متن واضح روی تصویر")
    if e < 10:
        tips.append("CTA برای لایک/اشتراک و نگه‌داشتن مخاطب بگذارید")
    return {
        "score": total, "maxScore": 100, "grade": grade,
        "breakdown": {
            "title": {"score": t, "max": 25, "label": "عنوان"},
            "description": {"score": d, "max": 20, "label": "توضیحات"},
            "tags": {"score": g, "max": 20, "label": "تگ‌ها"},
            "thumbnail": {"score": th, "max": 15, "label": "تامبنیل"},
            "engagement": {"score": e, "max": 20, "label": "تعامل"},
        },
        "tips": tips,
    }


def keyword_difficulty(yt, keyword):
    try:
        r = yt.search().list(part="snippet", q=keyword, type="video",
                             relevanceLanguage="ar", maxResults=5).execute()
        items = r.get("items", [])
        if not items:
            return None
        ids = ",".join(i["id"]["videoId"] for i in items)
        vr = yt.videos().list(part="statistics", id=ids).execute()
        views = [int(v["statistics"].get("viewCount", 0)) for v in vr.get("items", [])]
        if not views:
            return None
        import statistics
        med = statistics.median(views)
        dif = min(100.0, max(5.0, (med / 1_000_000) * 100))
        return round(dif, 1)
    except Exception:
        return None


def keywords_with_difficulty(profile, q, limit=15):
    suggestions = core.suggest_keywords(q)
    yt = core.cli_for(profile, "youtube")
    out = []
    for kw in suggestions[:limit]:
        d = keyword_difficulty(yt, kw)
        score = 100 - d if d is not None else 50
        out.append({"keyword": kw, "difficulty": d, "opportunity": round(score, 1)})
    return out


FALLBACK_TAGS = [
    "القرآن الكريم", "تلاوة", "quran", "القران الكريم", "تلاوة خاشعة",
    "ياسر الدوسري", "سكينة", "راحة نفسية", "طمأنينة", "القرآن للقلب",
    "القرآن للدراسة", "القرآن للنوم", "تلاوة هادئة", "القرآن الكريم كامل",
    "آيات السكينة", "ذكر الله", "قرآن للراحة النفسية", "القرآن الكريم mp3",
    "تلاوة مؤثرة", "خشوع",
]

HASHTAGS = [
    "#القرآن_الكريم", "#تلاوة", "#quran", "#القران_الكريم", "#تلاوة_خاشعة",
    "#راحة_نفسية", "#سكينة", "#ياسر_الدوسري", "#القران", "#القرآن_للقلب",
]


def optimize(profile, keywords, title=None, niche="تلاوة"):
    kw = (keywords or [])[:3]
    kws = " | ".join(kw) if kw else niche
    titles = []
    if title:
        titles.append(title)
    names = {
        "الرحمن": "سورة الرحمن", "الملك": "سورة الملك", "يس": "سورة يس"
    }
    if kw:
        main = kw[0]
        hits = [v for k, v in names.items() if k.lower() in main.lower()]
        if hits:
            sl = hits[0]
            titles.append(f"{sl} كاملة | تلاوة خاشعة تهدئ القلب 🕌")
            titles.append(f"{sl} كاملة بصوت خاشع للسكينة والنوم 🕌 1 ساعة")
            titles.append(f"{sl} | قرآن للراحة النفسية والتركيز {kws}")
    if len(titles) < 3:
        titles.append(f"{kws} | تلاوة خاشعة للراحة النفسية 🕌")
        titles.append(f"{kws} | قرآن كريم للنوم والدراسة بدون اعلانات")
        titles.append(f"{kws} بصوت ياسر الدوسري | أجمل تلاوة 🕌")
    seen = []
    for t in titles[:6]:
        if t not in seen and len(t) <= 100:
            seen.append(t)
    desc = (
        (f"{kws} 🕌\n" if kw else "") +
        "تلاوة خاشعة تبعث السكينة والراحة النفسية في قلبك.\n"
        "﴿أَلَا بِذِكْرِ اللَّهِ تَطْمَئِنُّ الْقُلُوبُ﴾\n\n"
        "مناسبة للاستماع أثناء النوم، الدراسة، العمل والتركيز.\n"
        "اللَّهُمَّ صَلِّ وَسَلِّمْ عَلَى نَبِيِّنَا مُحَمَّد ﷺ\n\n"
        "🎧 اترك الجهاز يعمل واستمتع بتلاوة هادئة بدون انقطاع.\n"
        "🔔 ساعدنا بالاشتراك وتفعيل الجرس ليصلك كل جديد.\n"
        "👍 اترك لايك ونظرك للحبيب ﷺ.\n\n"
        + " ".join(HASHTAGS)
    )
    tags = list(kw)
    for t in FALLBACK_TAGS:
        if t not in tags:
            tags.append(t)
        if len(tags) >= 12:
            break
    return {"titles": seen, "description": desc, "tags": tags,
            "keywords": list(dict.fromkeys(kw))}


def apply_metadata(profile, video_ids, title=None, description=None, tags=None):
    yt = core.cli_for(profile, "youtube")
    results = []
    for vid in video_ids:
        try:
            res = yt.videos().list(part="snippet,status", id=vid).execute()
            if not res.get("items"):
                results.append({"videoId": vid, "ok": False, "error": "not found"})
                continue
            sn = res["items"][0]["snippet"]
            status = res["items"][0]["status"]
            safe = {"categoryId": sn.get("categoryId", "22"),
                    "defaultLanguage": sn.get("defaultLanguage"),
                    "defaultAudioLanguage": sn.get("defaultAudioLanguage"),
                    "title": title or sn.get("title", ""),
                    "description": description if description is not None else sn.get("description", ""),
                    "tags": tags if tags is not None else sn.get("tags", []),
                    "publishedAt": sn.get("publishedAt")}
            body = {"id": vid, "snippet": safe, "status": status}
            yt.videos().update(part="snippet,status", body=body).execute()
            results.append({"videoId": vid, "ok": True})
        except Exception as e:
            results.append({"videoId": vid, "ok": False, "error": str(e)[:160]})
    return results
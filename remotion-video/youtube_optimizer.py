# -*- coding: utf-8 -*-
"""youtube_optimizer - SEO title / tags / description for آیه آرامش.

Optimized for the primary audience: Egypt 🇪🇬 · Algeria 🇩🇿 · Iraq 🇮🇶
(the same Arabic dialect-family + the Egyptian dialect that dominates
MENA discovery).  Every ar-variant title/tag carries the regional
keywords so Shorts surface in Egyptian, Algerian and Iraqi search.
"""
import os as _os

RECITER_NAME = _os.environ.get("QURAN_RECITER_NAME", "Yasser Al-Dosari")
CHANNEL_TITLE = "آیه آرامش — تلاوة القرآن الكريم"
CHANNEL_DESC = (
    "تلاوة القرآن الكريم بصوت الطالب "
    f"{RECITER_NAME} 🌙 — آيات تهدئة للنوم والتأمل. "
    "قرآن للمصريين 🇪🇬 · الجزائريين 🇩🇿 · العراقيين 🇮🇶 · وكل مسلم. "
    "محتوى إسلامي هادئ يومي — قرآن، دعا، تلاوة، تسبيح. "
    "اشتراك لتلاوة كل يوم 🤲"
)
CHANNEL_KEYWORDS = [
    "quran", "Quran recitation", "تلاوة", "تلاوة القرآن", "quran for sleep",
    "قرآن", "القرآن الكريم", "تلاوة القرآن", "آيات", "تلاوة للنبی",
    "مسلم", "إسلام", "دعاء", "تسبيح", "أذان", "الله",
    # Egypt / Algeria / Iraq focus
    "مصري", "المصريين", "الجزائر", "الجزائريين", "العراق", "العراقيين",
    "مسلمات", "دين", "إسلامي", "هادئ", "نوم", "relaxation", "sleep quran",
    RECITER_NAME.lower().replace(" ", ""),
]

def _ar_tags() -> str:
    base = ("#القرآن_الكريم #quran #اكسبلور #الرحمن #القران #تلاوة #quranrecitation "
            "#whatsappstatus #islamicstatus #مصري #الجزائر #العراق #مسلمات #ياسر_الدوسري")
    return base

def _fa_tags() -> str:
    return ("#قرآن #تلاوت_قرآن #آیه_آرامش #یاسر_الدوسری #آرامش_قلب "
            "#whatsappstatus #islamicstatus")

def _en_tags() -> str:
    return ("#quran #quranrecitation #sleep #islam #calm #dua #quranforsleep "
            "#whatsappstatus #islamicstatus #yaseraldossary")

def _ku_tags() -> str:
    return "#قورئان #quran #ئارامی #خۆڕاستی #dua #islam #کوردی #whatsappstatus #islamicstatus"

def _zh_tags() -> str:
    return ("#古兰经 #古蘭經 #quran #tilaawah #islam #sleep #quranrecitation "
            "#whatsappstatus #islamicstatus")

def _hi_tags() -> str:
    return ("#क़ुरआन #कुरान #quran #tilaawah #islam #sukoon #quranrecitation "
            "#whatsappstatus #islamicstatus")

TAG_MAP = {"ar": _ar_tags, "fa": _fa_tags, "en": _en_tags,
           "ku": _ku_tags, "zh": _zh_tags, "hi": _hi_tags}

def make_seo_tags(lang: str = "ar") -> str:
    return TAG_MAP.get(lang, _ar_tags())()

def make_seo_title(lang: str, surah: str, ayah_num: int, hook: str) -> str:
    ar_surah = surah
    if lang == "ar":
        return f"{hook} | {ar_surah} آیهٔ {ayah_num} — تلاوة {RECITER_NAME}"[:95]
    if lang == "fa":
        return f"{hook} | سوره {ar_surah} آیه {ayah_num} — تلاوه {RECITER_NAME}"[:95]
    return f"{hook} | {ar_surah} ayah {ayah_num} — {RECITER_NAME} recitation"[:95]

def make_seo_desc(lang: str, title: str, surah: str) -> str:
    if lang == "ar":
        return (
            f"{title}\n"
            f"تلاوة القرآن الكريم بصوت الطالب {RECITER_NAME} 🌙\n"
            f"سوره {surah} — محتوى إسلامي هادئ يومي للمصريين 🇪🇬 "
            f"والجزائريين 🇩🇿 والعراقيين 🇮🇶.\n"
            "تلاوة للساعة الذهبية · تهدئة للنوم · ذكر للقلب 🤲\n"
            f"Recited by {RECITER_NAME}."
        )
    if lang == "fa":
        return (
            f"{title}\n"
            f"تلاوت قرآن کریم به صدای {RECITER_NAME} 🌙\n"
            f"سوره {surah} — محتوای اسلامی روزانه برای مسلمانان.\n"
            f"Recited by {RECITER_NAME}."
        )
    return (
        f"{title}\n"
        f"Peaceful Quran recitation by {RECITER_NAME} 🌙\n"
        f"Surah {surah} — daily Islamic content for sleep & reflection.\n"
        f"Recited by {RECITER_NAME}."
    )
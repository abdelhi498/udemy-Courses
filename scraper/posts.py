"""Read course details from the text of a Telegram post.

Many coupon channels use the same layout, e.g.:

    Mastering Social Media Management and Marketing | Udemy
    Equip Yourself with the Skills, Strategies and Tools ...

    1.5 hours • 24 lectures • 7 quizzes.

    ⏳ 39 coupon uses left ⚠️
    📶 Rating: 4.7 ⭐️ (248 reviews)
    📅 Last updated: 09/26
    🎓 Instructor: Growth School

    #social_media_marketing
"""

import re

PLATFORM_SUFFIX = re.compile(r"\s*\|\s*(Udemy|Coursera|edX|Eduonix|Skillshare)\s*$", re.I)


def _search(pattern, text, cast=str):
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    try:
        return cast(m.group(1).replace(",", "").strip())
    except ValueError:
        return None


def parse_post(text):
    """Return whatever details can be found; missing ones are simply left out."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    info = {}
    if lines and PLATFORM_SUFFIX.search(lines[0]):
        info["title"] = PLATFORM_SUFFIX.sub("", lines[0])[:160]
        if len(lines) > 1 and not re.search(r"\d+(\.\d+)?\s*(hours?|mins?|questions)", lines[1], re.I):
            info["subtitle"] = lines[1][:300]
    duration = re.search(r"^.*\b(\d+(?:\.\d+)?\s*(?:total\s+)?(?:hours?|mins?|minutes?|questions))\b.*$", text, re.I | re.M)
    if duration:
        info["duration"] = re.sub(r"\.$", "", duration.group(0).strip())
    info["uses_left"] = _search(r"(\d[\d,]*)\s*coupon uses left", text, int)
    info["rating"] = _search(r"Rating:\s*([\d.]+)", text, float)
    info["reviews"] = _search(r"\(([\d,]+)\s*reviews?\)", text, int)
    info["instructor"] = _search(r"Instructor:\s*(.+)", text)
    info["updated"] = _search(r"Last updated:\s*([\d/]+)", text)
    tag = re.search(r"#([A-Za-z]\w+)", text)
    if tag:
        info["category"] = tag.group(1).replace("_", " ").title()
    return {k: v for k, v in info.items() if v not in (None, "")}

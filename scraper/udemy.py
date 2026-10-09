"""Optional checks against Udemy: is the coupon still 100% off? Fetch title/image too.

Udemy sometimes blocks automated requests (Cloudflare). Every function here is
best-effort: on any error it returns None and the course is kept as "unknown".
"""

import re
from urllib.parse import quote

from . import http

COURSE_ID_RE = re.compile(r'data-clp-course-id="(\d+)"|"course_id"\s*:\s*(\d+)')
OG_TITLE_RE = re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"')
OG_IMAGE_RE = re.compile(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"')


def course_info(slug):
    """Return {id, title, image} from the public course page, or None."""
    try:
        _, html = http.fetch(f"https://www.udemy.com/course/{slug}/", retries=0, timeout=12)
    except Exception:  # noqa: BLE001
        return None
    m = COURSE_ID_RE.search(html)
    if not m:
        return None
    title = OG_TITLE_RE.search(html)
    image = OG_IMAGE_RE.search(html)
    return {
        "id": int(m.group(1) or m.group(2)),
        "title": title.group(1).replace(" | Udemy", "") if title else None,
        "image": image.group(1) if image else None,
    }


def coupon_status(course_id, coupon):
    """'free' if the coupon makes the course cost 0, 'expired' if not, None if unknown."""
    url = (
        f"https://www.udemy.com/api-2.0/course-landing-components/{course_id}/me/"
        f"?couponCode={quote(coupon)}&components=purchase"
    )
    try:
        data = http.fetch_json(url, retries=0, timeout=12)
        price = data["purchase"]["data"]["pricing_result"]["price"]["amount"]
    except Exception:  # noqa: BLE001
        return None
    return "free" if float(price) == 0 else "expired"

"""Source: real.discount — a public list of free (100% off) Udemy coupons.

Each item already holds the direct Udemy link with the coupon, so no extra page
has to be opened. Example item:
  {"id": 79501, "name": "...", "price": 84.99, "sale_price": 0, "sale_start": "2026-10-09 05:16:19",
   "lectures": 6, "rating": 4.61, "image": "https://img-c.udemycdn.com/...jpg",
   "url": "https://www.udemy.com/course/<slug>/?couponCode=...", "store": "Udemy",
   "type": "external", "category": "Marketing", "subcategory": "Affiliate Marketing", "language": "English"}
Items with "type": "ad" are their sponsored posts and are skipped.
"""

import json
from datetime import datetime, timezone

from . import http, links

API = ("https://cdn.real.discount/api/courses?page={page}&limit={limit}"
       "&sortBy=sale_start&store=Udemy&freeOnly=true")
NAME = "real.discount"


def _posted_at(item):
    try:
        d = datetime.strptime(item["sale_start"], "%Y-%m-%d %H:%M:%S")
        return d.replace(tzinfo=timezone.utc).isoformat(timespec="seconds")
    except (KeyError, TypeError, ValueError):
        return None


def course_from_item(item):
    """Turn one API item into our course dict, or None if it isn't a free Udemy coupon."""
    if item.get("type") != "external" or item.get("store") != "Udemy":
        return None
    if item.get("sale_price") not in (0, "0", 0.0):
        return None
    norm = links.normalise_udemy(item.get("url") or "")
    posted = _posted_at(item)
    if not norm or not posted:
        return None
    category = item.get("subcategory") or item.get("category")
    course = {
        "id": f"rd:{item['id']}",
        "provider": "Udemy",
        "slug": norm["slug"],
        "page_slug": norm["slug"],
        "coupon": norm["coupon"],
        "url": norm["url"],
        "title": (item.get("name") or norm["slug"].replace("-", " ").title()).strip()[:160],
        "image": item.get("image"),
        "source": None,
        "channel": NAME,
        "posted_at": posted,
        "status": "unknown",
        "category": category,
        "language": item.get("language"),
        "lectures": item.get("lectures") or None,
        "rating": round(float(item["rating"]), 1) if item.get("rating") else None,
        "price": float(item["price"]) if item.get("price") else None,
    }
    return {k: v for k, v in course.items() if v is not None}


def fetch(cutoff_iso, pages=3, limit=100, log=print, errors=None):
    """Newest free Udemy coupons, stopping at `pages` pages or when older than the cutoff."""
    out = []
    for page in range(1, pages + 1):
        try:
            _, body = http.fetch(API.format(page=page, limit=limit), retries=1, timeout=30)
            items = json.loads(body).get("items") or []
        except Exception as e:  # noqa: BLE001
            log(f"  ! {NAME}: {e}")
            if errors is not None:
                errors.append(str(e))
            break
        if not items:
            break
        page_courses = [c for c in map(course_from_item, items) if c]
        out.extend(c for c in page_courses if c["posted_at"] >= cutoff_iso)
        if page_courses and min(c["posted_at"] for c in page_courses) < cutoff_iso:
            break
    return out

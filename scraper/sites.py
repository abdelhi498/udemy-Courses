"""Coupon websites that lead to direct Udemy coupon links.

Each source returns a list of course dicts in the same shape as the other sources.
They are all best-effort: a site that changes its layout just yields nothing (and an
error in the dashboard's source list), it never stops the run.
"""

import html as htmllib
import json
import re
from datetime import datetime, timezone

from . import http, links

NOW = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")  # noqa: E731


def _course(source_id, name, norm, title, **extra):
    c = {
        "id": f"{source_id}:{norm['slug']}",
        "provider": "Udemy",
        "slug": norm["slug"],
        "page_slug": norm["slug"],
        "coupon": norm["coupon"],
        "url": norm["url"],
        "title": (title or norm["slug"].replace("-", " ").title()).strip()[:160],
        "source": None,
        "channel": name,
        "posted_at": NOW(),
        "status": "unknown",
    }
    c.update(extra)
    return {k: v for k, v in c.items() if v not in (None, "")}


# ---------------------------------------------------------------- tutorialbar
# A Next.js site: the course data sits in `self.__next_f.push([1,"..."])` script chunks.
NEXT_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
FIELD = r'"{}":"((?:[^"\\]|\\.)*)"'
NUM_FIELD = r'"{}":([\d.]+)'


def _field(obj, name):
    m = re.search(FIELD.format(name), obj)
    if not m:
        return None
    try:
        return json.loads(f'"{m.group(1)}"')
    except ValueError:
        return m.group(1)


def _num(obj, name):
    m = re.search(NUM_FIELD.format(name), obj)
    return float(m.group(1)) if m else None


def parse_tutorialbar(page):
    text = "".join(json.loads(f'"{chunk}"') for chunk in NEXT_CHUNK.findall(page))
    out, seen = [], set()
    for m in re.finditer(r'"couponUrl":"(https://www\.udemy\.com/[^"]+)"', text):
        start = text.rfind('"course":{', 0, m.start())
        obj = text[start if start >= 0 else max(0, m.start() - 6000): m.end() + 800]
        norm = links.normalise_udemy(m.group(1))
        if not norm or norm["slug"] in seen or "true" not in (re.search(r'"is100PercentOff":(\w+)', obj) or [0, "true"])[1]:
            continue
        seen.add(norm["slug"])
        price = (_field(obj, "originalPrice") or "").replace("$", "")
        out.append(_course(
            "tb", "tutorialbar", norm, _field(obj, "title"),
            subtitle=_field(obj, "headline"),
            instructor=_field(obj, "instructorName"),
            rating=round(_num(obj, "rating"), 1) if _num(obj, "rating") else None,
            reviews=int(_num(obj, "ratingCount")) if _num(obj, "ratingCount") else None,
            students=int(_num(obj, "studentsCount")) if _num(obj, "studentsCount") else None,
            language=_field(obj, "language"),
            category=_field(obj, "category"),
            image=_field(obj, "imageUrl"),
            price=float(price) if re.fullmatch(r"[\d.]+", price) else None,
        ))
    return out


def fetch_tutorialbar(log=print, errors=None, **_):
    try:
        _, page = http.fetch("https://www.tutorialbar.com/", retries=1, timeout=30)
    except Exception as e:  # noqa: BLE001
        return _fail("tutorialbar", e, log, errors)
    found = parse_tutorialbar(page)
    if not found and errors is not None:
        errors.append("لم نجد كورسات في الصفحة (ربما تغيّر تصميم الموقع)")
    return found


# ------------------------------------------------- discudemy / udemyfreebies
# Listing page -> one link per course -> a "go"/"out" link that leads to Udemy.

def _listing(url, pattern):
    """[(slug, title)] from a listing page, using the link text as the title."""
    _, page = http.fetch(url, retries=1, timeout=30)
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="' + pattern + r'"[^>]*>(.*?)</a>', page, re.S):
        slug, title = m.group(1), htmllib.unescape(re.sub(r"<[^>]+>", " ", m.group(2))).strip()
        title = re.sub(r"\s+", " ", title)
        if slug in seen or len(title) < 4:
            continue
        seen.add(slug)
        out.append((slug, title))
    return out


def _follow(go_url, cache):
    """Udemy link behind a go/out link: a redirect, or a link inside the page."""
    if go_url in cache:
        return cache[go_url]
    target = http.redirect_target(go_url, timeout=20)
    if not (target and links.normalise_udemy(target)):
        _, page = http.fetch(go_url, retries=0, timeout=20)
        m = links.UDEMY_COUPON_RE.search(page.replace("&amp;", "&"))
        target = m.group(0) if m else None
    cache[go_url] = target
    return target


def _from_listing(name, source_id, list_url, pattern, go_url, cache, log, errors, max_new=30):
    try:
        items = _listing(list_url, pattern)
    except Exception as e:  # noqa: BLE001
        return _fail(name, e, log, errors)
    out, new = [], 0
    for slug, title in items:
        url = go_url.format(slug=slug)
        if url not in cache:
            if new >= max_new:
                continue
            new += 1
        try:
            target = _follow(url, cache)
        except Exception as e:  # noqa: BLE001
            log(f"  ! {name} {slug}: {e}")
            continue
        norm = links.normalise_udemy(target) if target else None
        if norm:
            out.append(_course(source_id, name, norm, title))
    if not out and errors is not None:
        errors.append("لم نجد روابط يوديمي (ربما تغيّر تصميم الموقع)")
    return out


def fetch_discudemy(cache, log=print, errors=None, **_):
    return _from_listing(
        "discudemy", "du", "https://www.discudemy.com/all/1",
        r"https://www\.(?:couponami|discudemy)\.com/(?!category/|go/|giveaway/)[\w\-]+/([\w\-]+)",
        "https://www.couponami.com/go/{slug}", cache, log, errors)


def fetch_udemyfreebies(cache, log=print, errors=None, **_):
    return _from_listing(
        "udemyfreebies", "uf", "https://www.udemyfreebies.com/free-udemy-courses/1",
        r"https://www\.udemyfreebies\.com/free-udemy-course/([\w\-]+)",
        "https://www.udemyfreebies.com/out/{slug}", cache, log, errors)


def _fail(name, error, log, errors):
    log(f"  ! {name}: {error}")
    if errors is not None:
        errors.append(str(error))
    return []


SOURCES = {
    "tutorialbar": fetch_tutorialbar,
    "discudemy": fetch_discudemy,
    "udemyfreebies": fetch_udemyfreebies,
}

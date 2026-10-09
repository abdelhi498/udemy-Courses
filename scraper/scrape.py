"""Collect free (100% off) course coupons from public Telegram channels.

Run from the repository root:   python -m scraper.scrape
Sources come from data/settings.json (edited from the admin dashboard).
Output: data/courses.json  (turned into the website by scraper/build.py)
"""

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import links, posts, realdiscount, settings as settings_mod, sites, telegram, udemy

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "scraper" / "config.json"
DATA_PATH = ROOT / "data" / "courses.json"
SETTINGS_PATH = ROOT / "data" / "settings.json"
ARCHIVE_PATH = ROOT / "data" / "archive.json"
ARCHIVE_DAYS = 60
CACHE_PATH = ROOT / "data" / ".cache.json"

FREE_WORDS = re.compile(r"100\s*%|free|مجان|كوبون|coupon", re.I)


def now_utc():
    return datetime.now(timezone.utc)


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def title_from_message(text, slug):
    """First meaningful line of the post, falling back to the URL slug."""
    for line in text.splitlines():
        line = re.sub(r"https?://\S+", "", line).strip(" -–—•*:|#‏‎")
        line = re.sub(r"^[^\w؀-ۿ]+", "", line).strip()  # drop leading emoji
        if len(line) >= 8 and not re.fullmatch(r"(?i)(free|100% off|coupon|enroll now).*", line):
            return line[:160]
    return slug.replace("-", " ").title()


def _try_resolve(url, msg, resolve_budget, cache, cfg, log, require_free_words=True):
    """Look inside an intermediate page for the real Udemy coupon link (within budget)."""
    if not cfg["resolve_redirects"]:
        return None
    if require_free_words and not FREE_WORDS.search(msg["text"]):
        return None
    if url not in cache:
        if resolve_budget[0] <= 0 or time.monotonic() > resolve_budget[1]:
            return None
        resolve_budget[0] -= 1
    target = links.resolve(url, cache, log, timeout=cfg["resolve_timeout"])
    return links.normalise_udemy(target) if target else None


def courses_from_message(msg, resolve_budget, cache, cfg, log):
    """Yield course dicts found in one Telegram message."""
    found = []
    for url in links.candidate_links(msg):
        if links.is_ignored(url):
            continue
        provider = links.provider_for(url)
        if provider == "Udemy":
            norm = links.normalise_udemy(url)  # None for instructor/profile links
            if norm:
                found.append(("Udemy", norm))
            continue
        if provider:
            found.append((provider, {"slug": url, "coupon": None, "url": url}))
            continue
        agg = links.aggregator_slug(url)
        if agg:
            # A coupon site (e.g. courson.xyz). Prefer the real Udemy link inside it;
            # if that page can't be read, still list the course and link to the page.
            site, slug = agg
            clean = url.split("?", 1)[0]
            norm = _try_resolve(clean, msg, resolve_budget, cache, cfg, log, require_free_words=False)
            found.append(("Udemy", norm or {"slug": slug, "coupon": None, "url": clean, "via": site}))
            continue
        # Unknown site: maybe a redirect / blog page wrapping a Udemy coupon.
        norm = _try_resolve(url, msg, resolve_budget, cache, cfg, log)
        if norm:
            found.append(("Udemy", norm))

    unique = list({(p, n["url"]): (p, n) for p, n in found}.values())
    details = posts.parse_post(msg["text"]) if len(unique) == 1 else {}
    for i, (provider, norm) in enumerate(unique):
        # A post listing several courses has one caption; use each link's slug instead.
        if details.get("title"):
            title = details["title"]
        elif len(unique) == 1:
            title = title_from_message(msg["text"], norm["slug"])
        else:
            title = title_from_message("", norm["slug"].rstrip("/").rsplit("/", 1)[-1])
        if msg.get("post"):
            cid = f"tg:{msg['post']}" + (f":{i}" if len(unique) > 1 else "")
        else:
            cid = f"manual:{norm['slug']}:{norm['coupon'] or ''}"
        course = {
            "id": cid,
            "provider": provider,
            "slug": norm["slug"],
            "page_slug": norm["slug"],
            "coupon": norm["coupon"],
            "url": norm["url"],
            "via": norm.get("via"),
            "title": title,
            "image": msg.get("photo"),
            "source": f"https://t.me/{msg['post']}" if msg.get("post") else None,
            "channel": msg["channel"],
            "posted_at": msg["date"],
            "status": "unknown",
        }
        course.update({k: v for k, v in details.items() if k != "title"})
        yield {k: v for k, v in course.items() if v is not None}


def merge_with_previous(course, old):
    """Keep what earlier runs learned (resolved link, Udemy check, stable page URL)."""
    course["posted_at"] = min(old["posted_at"], course["posted_at"])
    course["page_slug"] = old.get("page_slug") or old["slug"]
    if not course.get("coupon") and old.get("coupon"):
        for k in ("slug", "coupon", "url"):
            course[k] = old[k]
        course.pop("via", None)
    if course.get("coupon") == old.get("coupon"):
        for k in ("status", "checked_at"):
            if old.get(k):
                course[k] = old[k]
    for k in ("title", "image"):
        if old.get(k) and old.get("checked_at"):  # title/image confirmed by Udemy
            course[k] = old[k]
    return course


def enrich_with_udemy(courses, cfg, cache, log):
    """Check coupon status and fill title/image from Udemy (best-effort)."""
    budget = cfg["max_validations"]
    info_cache = cache.setdefault("_udemy_info", {})
    recheck_before = now_utc() - timedelta(hours=6)
    deadline = time.monotonic() + cfg["max_validation_seconds"]
    failures_in_a_row = 0
    for c in courses:
        if c["provider"] != "Udemy" or not c.get("coupon") or budget <= 0 or time.monotonic() > deadline:
            continue
        # Coupons run out, so re-check a "free" course every few hours.
        if c.get("checked_at") and datetime.fromisoformat(c["checked_at"]) > recheck_before:
            continue
        budget -= 1
        info = info_cache.get(c["slug"])
        if info is None:
            info = udemy.course_info(c["slug"]) or {}
            if info:
                info_cache[c["slug"]] = info
                failures_in_a_row = 0
            else:
                failures_in_a_row += 1
                if failures_in_a_row >= 5:
                    log("  Udemy is not answering (probably blocking bots); skipping checks this run")
                    break
        if info.get("title"):
            c["title"] = info["title"]
        if info.get("image"):
            c["image"] = info["image"]
        if info.get("id"):
            status = udemy.coupon_status(info["id"], c["coupon"])
            if status:
                c["status"] = status
        c["checked_at"] = now_utc().isoformat(timespec="seconds")
        log(f"  {c['status']:8} {c['slug']}")


def _title_key(title):
    return re.sub(r"[^a-z0-9]+", "", (title or "").lower())


def link_coupon_site_courses(fresh, log=print):
    """Give courses that only have a coupon-site link (e.g. courson.xyz) the direct
    Udemy link, when another source lists the same course; then drop the duplicate."""
    direct = [c for c in fresh.values() if c.get("coupon") and c["provider"] == "Udemy"]
    by_slug = {c["slug"]: c for c in direct}
    by_title = {_title_key(c["title"]): c for c in direct}
    upgraded = 0
    for c in list(fresh.values()):
        if not c.get("via"):
            continue
        match = by_slug.get(c["slug"]) or by_title.get(_title_key(c["title"]))
        if not match or match["id"] not in fresh:
            continue
        for k in ("slug", "coupon", "url"):
            c[k] = match[k]
        c.pop("via", None)
        for k in ("image", "price", "language", "lectures", "status", "checked_at"):
            if match.get(k):
                c[k] = match[k]  # Udemy's own image is better than the Telegram copy
        del fresh[match["id"]]
        upgraded += 1
    # Same Udemy course from two sources: keep one (the Telegram post has more details).
    best = {}
    for c in sorted(fresh.values(), key=lambda c: c["id"].startswith("rd:")):
        if c.get("coupon") and c["provider"] == "Udemy":
            if c["slug"] in best:
                del fresh[c["id"]]
            else:
                best[c["slug"]] = c
    if upgraded:
        log(f"- linked {upgraded} coupon-site courses to direct Udemy links")


def probe_sites(debug):
    """Debug only: try one link per coupon site and record how it answers."""
    import urllib.request
    report = {}
    for msgs in list(debug.values()):
        for m in msgs:
            for url in m.get("links") or []:
                agg = links.aggregator_slug(url)
                if not agg or agg[0] in report:
                    continue
                attempts = []
                for name, headers in (("browser", None), ("plain", {"User-Agent": "curl/8.5.0"})):
                    t0 = time.monotonic()
                    try:
                        if headers is None:
                            final, body = __import__("scraper.http", fromlist=["fetch"]).fetch(url, retries=0, timeout=40)
                            status = 200
                        else:
                            req = urllib.request.Request(url, headers=headers)
                            with urllib.request.urlopen(req, timeout=40) as r:
                                final, status = r.geturl(), r.status
                                body = r.read().decode("utf-8", "replace")
                        found = links.UDEMY_COUPON_RE.findall(body.replace("&amp;", "&"))
                        attempts.append({"mode": name, "status": status, "final": final,
                                         "seconds": round(time.monotonic() - t0, 1),
                                         "udemy_links": found[:3], "length": len(body),
                                         "snippet": re.sub(r"\s+", " ", body)[:1500]})
                    except Exception as e:  # noqa: BLE001
                        attempts.append({"mode": name, "error": repr(e)[:300],
                                         "seconds": round(time.monotonic() - t0, 1)})
                report[agg[0]] = {"url": url, "attempts": attempts}
    return report


def update_archive(previous, current, now):
    """Remember courses that just left the list, so their page can say "expired"
    for a while instead of disappearing (people still arrive from Google and shares)."""
    archive = load_json(ARCHIVE_PATH, {})
    live = {c["id"] for c in current}
    for cid, c in previous.items():
        if cid not in live and cid not in archive:
            keep = {k: c.get(k) for k in ("id", "provider", "slug", "page_slug", "url", "title", "image", "category",
                                           "subtitle", "instructor", "language", "rating", "reviews", "price",
                                           "channel", "posted_at") if c.get(k) is not None}
            keep.update(coupon=None, status="expired", removed_at=now.isoformat(timespec="seconds"))
            archive[cid] = keep
    for cid in list(archive):
        if cid in live or now - datetime.fromisoformat(archive[cid]["removed_at"]) > timedelta(days=ARCHIVE_DAYS):
            del archive[cid]
    ARCHIVE_PATH.write_text(json.dumps(archive, ensure_ascii=False, indent=1), encoding="utf-8")


def run(log=print):
    cfg = load_json(CONFIG_PATH, {})
    cfg.setdefault("telegram_channels", [])
    cfg.setdefault("pages_per_channel", 2)
    cfg.setdefault("max_age_days", 7)
    cfg.setdefault("resolve_redirects", True)
    cfg.setdefault("max_redirect_lookups", 60)
    cfg.setdefault("validate_udemy", False)
    cfg.setdefault("max_validations", 80)
    cfg.setdefault("max_redirect_seconds", 180)
    cfg.setdefault("resolve_timeout", 25)
    cfg.setdefault("max_validation_seconds", 300)

    settings = settings_mod.normalise(load_json(SETTINGS_PATH, {}))
    cfg["max_age_days"] = int(settings["content"].get("max_age_days") or cfg["max_age_days"])
    cache = load_json(CACHE_PATH, {})
    previous = {c["id"]: c for c in load_json(DATA_PATH, {}).get("courses", [])}
    cutoff = now_utc() - timedelta(days=cfg["max_age_days"])
    # [lookups left, monotonic deadline] — keeps one slow site from stalling the run.
    resolve_budget = [cfg["max_redirect_lookups"], time.monotonic() + cfg["max_redirect_seconds"]]

    enabled = [src for src in settings.get("sources", []) if src.get("enabled", True)]
    channels = [src["name"] for src in enabled if src.get("type") == "telegram"]
    channels += cfg.get("telegram_channels", [])  # legacy option

    fresh = {}
    stats = {}

    def add(course):
        old = fresh.get(course["id"]) or previous.get(course["id"])
        if old:
            course = merge_with_previous(course, old)
        fresh[course["id"]] = course

    debug = {}
    for channel in channels:
        errors = []
        messages = telegram.fetch_channel(channel, cfg["pages_per_channel"], log, errors)
        if os.environ.get("SCRAPER_DEBUG"):
            debug[channel] = [{k: m.get(k) for k in ("post", "date", "text", "links", "photo")}
                              for m in messages[-8:]]
        found_in_channel = 0
        for msg in messages:
            if not msg["date"] or datetime.fromisoformat(msg["date"]) < cutoff:
                continue
            for course in courses_from_message(msg, resolve_budget, cache, cfg, log):
                found_in_channel += 1
                add(course)
        stats[channel] = {"messages": len(messages), "courses": found_in_channel,
                          "error": errors[0] if errors else None}
        log(f"- {channel}: {len(messages)} messages, {found_in_channel} course links")

    # Coupon websites (direct Udemy links).
    for src in enabled:
        kind = src.get("type")
        if kind not in sites.SOURCES and kind != "realdiscount":
            continue
        errors = []
        if kind == "realdiscount":
            found = realdiscount.fetch(cutoff.isoformat(timespec="seconds"), pages=int(src.get("pages") or 3),
                                       log=log, errors=errors)
        else:
            found = sites.SOURCES[kind](cache=cache, log=log, errors=errors)
        for course in found:
            add(course)
        stats[src["name"]] = {"messages": len(found), "courses": len(found),
                              "error": errors[0] if errors else None}
        log(f"- {src['name']}: {len(found)} courses")

    if debug:
        debug["_probe"] = probe_sites(debug)
        (ROOT / "data" / "debug-messages.json").write_text(
            json.dumps(debug, ensure_ascii=False, indent=1), encoding="utf-8")

    # Courses added by hand from the dashboard.
    for item in settings.get("manual_courses", []):
        msg = {"text": item.get("title") or "", "links": [item["url"]], "post": None,
               "channel": "يدوي", "photo": item.get("image") or None,
               "date": item.get("added_at") or now_utc().isoformat(timespec="seconds")}
        if datetime.fromisoformat(msg["date"]) < cutoff:
            continue
        for course in courses_from_message(msg, [0, 0], cache, cfg, log):
            if item.get("title"):
                course["title"] = item["title"]
            add(course)

    # Keep still-recent courses from earlier runs that scrolled out of the channel pages.
    for cid, old in previous.items():
        if cid not in fresh and datetime.fromisoformat(old["posted_at"]) >= cutoff:
            fresh[cid] = old

    link_coupon_site_courses(fresh, log)
    courses = sorted(fresh.values(), key=lambda c: c["posted_at"], reverse=True)
    if cfg["validate_udemy"]:
        enrich_with_udemy(courses, cfg, cache, log)
    courses = [c for c in courses if c["status"] != "expired"]

    update_archive(previous, courses, now_utc())

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(
        json.dumps(
            {"updated_at": now_utc().isoformat(timespec="seconds"),
             "count": len(courses), "sources": stats, "courses": courses},
            ensure_ascii=False, indent=1,
        ),
        encoding="utf-8",
    )
    # Drop cached redirect lookups that are no longer needed, to keep the file small.
    if len(cache) > 3000:
        cache = {"_udemy_info": cache.get("_udemy_info", {})}
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    log(f"Saved {len(courses)} courses -> {DATA_PATH.relative_to(ROOT)}")
    return courses


if __name__ == "__main__":
    run()

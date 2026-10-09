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

from . import links, telegram, udemy

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "scraper" / "config.json"
DATA_PATH = ROOT / "data" / "courses.json"
SETTINGS_PATH = ROOT / "data" / "settings.json"
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


def courses_from_message(msg, resolve_budget, cache, cfg, log):
    """Yield course dicts found in one Telegram message."""
    found = []
    for url in links.candidate_links(msg):
        if links.is_ignored(url):
            continue
        provider = links.provider_for(url)
        if provider == "Udemy":
            norm = links.normalise_udemy(url)
            if norm:
                found.append(("Udemy", norm))
            continue
        if provider:
            found.append((provider, {"slug": url, "coupon": None, "url": url}))
            continue
        # Unknown site: maybe a redirect / blog page wrapping a Udemy coupon.
        if cfg["resolve_redirects"] and FREE_WORDS.search(msg["text"]) and (
            url in cache or (resolve_budget[0] > 0 and time.monotonic() < resolve_budget[1])
        ):
            if url not in cache:
                resolve_budget[0] -= 1
            target = links.resolve(url, cache, log)
            norm = links.normalise_udemy(target) if target else None
            if norm:
                found.append(("Udemy", norm))

    unique = list({(p, n["url"]): (p, n) for p, n in found}.values())
    for provider, norm in unique:
        # A post listing several courses has one caption; use each link's slug instead.
        title = (title_from_message(msg["text"], norm["slug"]) if len(unique) == 1
                 else title_from_message("", norm["slug"].rstrip("/").rsplit("/", 1)[-1]))
        yield {
            "id": f"{provider.lower()}:{norm['slug']}:{norm['coupon'] or ''}",
            "provider": provider,
            "slug": norm["slug"],
            "coupon": norm["coupon"],
            "url": norm["url"],
            "title": title,
            "image": msg.get("photo"),
            "description": msg["text"][:400],
            "source": f"https://t.me/{msg['post']}" if msg.get("post") else None,
            "channel": msg["channel"],
            "posted_at": msg["date"],
            "status": "unknown",
        }


def enrich_with_udemy(courses, cfg, cache, log):
    """Check coupon status and fill title/image from Udemy (best-effort)."""
    budget = cfg["max_validations"]
    info_cache = cache.setdefault("_udemy_info", {})
    recheck_before = now_utc() - timedelta(hours=6)
    deadline = time.monotonic() + cfg["max_validation_seconds"]
    failures_in_a_row = 0
    for c in courses:
        if c["provider"] != "Udemy" or budget <= 0 or time.monotonic() > deadline:
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
    cfg.setdefault("max_validation_seconds", 300)

    cache = load_json(CACHE_PATH, {})
    previous = {c["id"]: c for c in load_json(DATA_PATH, {}).get("courses", [])}
    cutoff = now_utc() - timedelta(days=cfg["max_age_days"])
    # [lookups left, monotonic deadline] — keeps one slow site from stalling the run.
    resolve_budget = [cfg["max_redirect_lookups"], time.monotonic() + cfg["max_redirect_seconds"]]

    settings = load_json(SETTINGS_PATH, {})
    channels = [src["name"] for src in settings.get("sources", [])
                if src.get("type") == "telegram" and src.get("enabled", True)]
    channels += cfg.get("telegram_channels", [])  # legacy option

    fresh = {}
    stats = {}

    def add(course):
        old = fresh.get(course["id"]) or previous.get(course["id"])
        if old:
            # Keep earliest post time and anything already checked.
            course["posted_at"] = min(old["posted_at"], course["posted_at"])
            for k in ("status", "checked_at", "title", "image"):
                if old.get(k) and (k != "image" or not course.get("image")):
                    course[k] = old[k]
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

    if debug:
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

    courses = sorted(fresh.values(), key=lambda c: c["posted_at"], reverse=True)
    if cfg["validate_udemy"]:
        enrich_with_udemy(courses, cfg, cache, log)
    courses = [c for c in courses if c["status"] != "expired"]

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

"""Build the static website into _site/ from site/ templates + data/*.json.

Run from the repository root:   python -m scraper.build
Preview locally:                python -m http.server -d _site

What it produces (all good for search engines):
  index.html                 home page with the course cards already in the HTML
  course/<slug>/index.html   one page per course (title, description, JSON-LD, ad + countdown)
  sitemap.xml, robots.txt    so Google finds every page
  ads.txt, CNAME             only when set in the dashboard
  data/courses.json          what the page's JavaScript uses for search and filters
"""

import base64
import html
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE_SRC = ROOT / "site"
DATA_DIR = ROOT / "data"
OUT = ROOT / "_site"

INITIAL_CARDS = 24
RELATED_COUNT = 6
SLOT_NAMES = ("header", "in_feed", "countdown", "course_bottom", "footer")

esc = html.escape


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def render(template, **ctx):
    """Replace {{name}} placeholders. Values must already be escaped where needed."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(ctx.get(m.group(1), "")), template)


def page_slug(course):
    """URL-safe slug for the course page (stable across coupon changes)."""
    base = course.get("page_slug") or (course["slug"] if course["provider"] == "Udemy" else course["url"])
    return re.sub(r"[^a-z0-9\-]+", "-", base.lower()).strip("-")[:80] or "course"


def ad(settings, name):
    slot = settings["ads"]["slots"].get(name) or {}
    if not slot.get("enabled") or not slot.get("html", "").strip():
        return ""
    return f'<div class="ad ad-{name}">{slot["html"]}</div>'


def fmt_date(iso):
    d = datetime.fromisoformat(iso)
    return d.strftime("%Y-%m-%d")


def b64(text):
    return base64.b64encode(text.encode()).decode()


def facts_html(c):
    """Small facts line under a card title: rating, coupons left, duration."""
    out = []
    if c.get("rating"):
        out.append(f'⭐ {c["rating"]:.1f}' + (f' ({c["reviews"]:,})' if c.get("reviews") else ""))
    if c.get("uses_left"):
        out.append(f'⏳ {c["uses_left"]} كوبون متبقي')
    return " • ".join(out)


def card_html(c, prefix):
    """Server-side version of the card that site/app.js renders (keep them in sync)."""
    img = (f'<img src="{esc(c["image"])}" alt="{esc(c["title"])}" loading="lazy" '
           f'onerror="this.remove()">' if c.get("image") else "")
    status = '<span class="badge ok">✓ مجاني مؤكد</span>' if c["status"] == "free" else ""
    pin = '<span class="badge pin">📌 مميز</span>' if c.get("pinned") else ""
    age = datetime.now(timezone.utc) - datetime.fromisoformat(c["posted_at"])
    new = '<span class="badge new">جديد</span>' if age.total_seconds() < 12 * 3600 else ""
    cat = f'<span class="badge">{esc(c["category"])}</span>' if c.get("category") else ""
    facts = facts_html(c)
    href = f'{prefix}course/{c["page"]}/'
    return (
        f'<article class="card"><a class="thumb" href="{href}">{img}<span class="ph">{esc(c["provider"])}</span></a>'
        f'<div class="body"><div class="meta"><span class="badge provider">{esc(c["provider"])}</span>{pin}{new}{status}{cat}</div>'
        f'<h3 class="title"><a href="{href}">{esc(c["title"])}</a></h3>'
        + (f'<p class="facts">{esc(facts)}</p>' if facts else "") +
        f'<p class="time"><time datetime="{esc(c["posted_at"])}">{fmt_date(c["posted_at"])}</time> • {esc(c["channel"])}</p>'
        f'<div class="actions"><a class="btn primary go" href="{href}" data-unlock data-target="{b64(c["url"])}" '
        f'data-title="{esc(c["title"])}" data-coupon="{esc(c.get("coupon") or "")}">احصل عليه مجاناً</a></div></div></article>'
    )


def prepare_courses(courses, settings):
    hidden = set(settings.get("hidden", []))
    pinned = settings.get("pinned", [])
    out, used = [], set()
    for c in courses:
        if c["id"] in hidden:
            continue
        c = dict(c)
        c["page"] = page_slug(c)
        # Same course posted with two coupons: keep the newest one only.
        if c["page"] in used:
            continue
        used.add(c["page"])
        c["pinned"] = c["id"] in pinned
        c.pop("description", None)  # raw Telegram text; not shown on the site
        out.append(c)
    pins = sorted((c for c in out if c["pinned"]), key=lambda c: pinned.index(c["id"]))
    rest = [c for c in out if not c["pinned"]]  # already newest first
    return pins + rest


def common_ctx(settings, prefix):
    s = settings["site"]
    return {
        "site_name": esc(s["name"]),
        "tagline": esc(s.get("tagline", "")),
        "head_code": s.get("head_code", ""),
        "prefix": prefix,
        "facebook": esc(s.get("facebook") or ""),
        "facebook_hidden": "" if s.get("facebook") else "hidden",
        "telegram": esc(s.get("telegram") or ""),
        "telegram_hidden": "" if s.get("telegram") else "hidden",
        "ad_header": ad(settings, "header"),
        "ad_countdown": ad(settings, "countdown"),
        "seconds": max(0, min(120, int(settings["ads"].get("countdown_seconds") or 0))),
        "ad_footer": ad(settings, "footer"),
        "year": datetime.now(timezone.utc).year,
    }


def site_url(settings):
    s = settings["site"]
    if s.get("custom_domain"):
        return f'https://{s["custom_domain"].strip().strip("/")}/'
    return s["url"].rstrip("/") + "/"


def build_index(courses, data, settings, base_url):
    tpl = (SITE_SRC / "index.html").read_text(encoding="utf-8")
    every = max(2, int(settings["ads"].get("in_feed_every") or 6))
    in_feed = ad(settings, "in_feed")
    cards = []
    for i, c in enumerate(courses[:INITIAL_CARDS], 1):
        cards.append(card_html(c, ""))
        if in_feed and i % every == 0:
            cards.append(in_feed)
    item_list = {
        "@context": "https://schema.org",
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "url": f'{base_url}course/{c["page"]}/', "name": c["title"]}
            for i, c in enumerate(courses[:50], 1)
        ],
    }
    ctx = common_ctx(settings, "")
    ctx.update(
        title=esc(f'{settings["site"]["name"]} | كوبونات يوديمي مجانية 100%'),
        description=esc(settings["site"]["description"]),
        canonical=base_url,
        og_image="",
        jsonld=json.dumps(item_list, ensure_ascii=False).replace("</", "<\\/"),
        count=len(courses),
        updated=esc(data.get("updated_at") or ""),
        cards="".join(cards),
        in_feed_template=in_feed,
        in_feed_every=every,
    )
    (OUT / "index.html").write_text(render(tpl, **ctx), encoding="utf-8")


def build_course_pages(courses, settings, base_url):
    tpl = (SITE_SRC / "course.html").read_text(encoding="utf-8")
    for i, c in enumerate(courses):
        prefix = "../../"
        url = f'{base_url}course/{c["page"]}/'
        title = c["title"]
        desc = (f'احصل على كورس "{title}" على {c["provider"]} مجاناً بخصم 100%.'
                + (f' {c["subtitle"]}' if c.get("subtitle") else "")
                + " الكوبون محدود العدد والمدة، فسارع بالتسجيل.")
        details = [
            ("المدة", c.get("duration")),
            ("التقييم", f'⭐ {c["rating"]:.1f}' + (f' ({c["reviews"]:,} تقييم)' if c.get("reviews") else "") if c.get("rating") else None),
            ("الكوبونات المتبقية", f'⏳ {c["uses_left"]}' if c.get("uses_left") else None),
            ("المدرّب", c.get("instructor")),
            ("التصنيف", c.get("category")),
            ("آخر تحديث للكورس", c.get("updated")),
        ]
        details_html = "".join(f"<dt>{k}</dt><dd>{esc(str(v))}</dd>" for k, v in details if v)
        related = [r for r in courses if r is not c][:RELATED_COUNT]
        jsonld = {
            "@context": "https://schema.org",
            "@type": "Course",
            "name": title,
            "description": desc,
            "url": url,
            "provider": {"@type": "Organization", "name": c["provider"]},
            "offers": {"@type": "Offer", "category": "Free", "price": 0, "priceCurrency": "USD",
                       "url": url, "availability": "https://schema.org/LimitedAvailability"},
        }
        if c.get("image"):
            jsonld["image"] = c["image"]
        if c.get("instructor"):
            jsonld["instructor"] = {"@type": "Person", "name": c["instructor"]}
        if c.get("rating") and c.get("reviews"):
            jsonld["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": c["rating"],
                                         "ratingCount": c["reviews"], "bestRating": 5}
        ctx = common_ctx(settings, prefix)
        ctx.update(
            title=esc(f"{title} — مجاناً بكوبون 100% | {settings['site']['name']}"),
            description=esc(desc),
            canonical=url,
            og_image=esc(c.get("image") or ""),
            jsonld=json.dumps(jsonld, ensure_ascii=False).replace("</", "<\\/"),
            course_title=esc(title),
            course_desc=esc(c.get("subtitle") or desc),
            details=f'<dl class="details">{details_html}</dl>' if details_html else "",
            provider=esc(c["provider"]),
            image=(f'<img src="{esc(c["image"])}" alt="{esc(title)}" onerror="this.remove()">'
                   if c.get("image") else ""),
            status=('<span class="badge ok">✓ مجاني مؤكد</span>' if c["status"] == "free" else "")
            + (f'<span class="badge">{esc(c["category"])}</span>' if c.get("category") else ""),
            posted=esc(c["posted_at"]),
            posted_date=fmt_date(c["posted_at"]),
            channel=esc(c["channel"]),
            source=esc(c.get("source") or ""),
            source_hidden="" if c.get("source") else "hidden",
            # Encoded so the link is not sitting in plain text before the countdown ends.
            target=b64(c["url"]),
            coupon=esc(c.get("coupon") or ""),
            ad_course_bottom=ad(settings, "course_bottom"),
            related="".join(card_html(r, prefix) for r in related),
        )
        page_dir = OUT / "course" / c["page"]
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(render(tpl, **ctx), encoding="utf-8")


def build_seo_files(courses, data, settings, base_url):
    today = (data.get("updated_at") or datetime.now(timezone.utc).isoformat())[:10]
    urls = [f"  <url><loc>{base_url}</loc><lastmod>{today}</lastmod><changefreq>hourly</changefreq><priority>1.0</priority></url>"]
    for c in courses:
        urls.append(f'  <url><loc>{esc(base_url)}course/{c["page"]}/</loc><lastmod>{c["posted_at"][:10]}</lastmod></url>')
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>\n",
        encoding="utf-8")
    (OUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nDisallow: /admin/\n\nSitemap: {base_url}sitemap.xml\n", encoding="utf-8")
    ads_txt = settings["ads"].get("ads_txt", "").strip()
    if ads_txt:
        (OUT / "ads.txt").write_text(ads_txt + "\n", encoding="utf-8")
    domain = settings["site"].get("custom_domain", "").strip().strip("/")
    if domain:
        (OUT / "CNAME").write_text(domain + "\n", encoding="utf-8")


def build_404(settings, base_url):
    # Served for any unknown path, so links must be absolute.
    ctx = common_ctx(settings, base_url)
    tpl = (SITE_SRC / "404.html").read_text(encoding="utf-8")
    (OUT / "404.html").write_text(render(tpl, **ctx), encoding="utf-8")


def default_settings():
    return load(DATA_DIR / "settings.json", {})


def normalise_settings(settings):
    settings.setdefault("site", {})
    s = settings["site"]
    s.setdefault("name", "كورسات مجانية")
    s.setdefault("description", "")
    s.setdefault("url", "https://example.github.io/")
    settings.setdefault("ads", {})
    settings["ads"].setdefault("slots", {})
    for name in SLOT_NAMES:
        settings["ads"]["slots"].setdefault(name, {"enabled": False, "html": ""})
    return settings


def run(log=print):
    settings = normalise_settings(default_settings())
    data = load(DATA_DIR / "courses.json", {"courses": []})
    courses = prepare_courses(data.get("courses", []), settings)
    base_url = site_url(settings)

    if OUT.exists():
        shutil.rmtree(OUT)
    templates = {"index.html", "course.html", "404.html"}  # rendered below, only at the top level
    shutil.copytree(SITE_SRC, OUT, ignore=lambda d, names: templates & set(names) if Path(d) == SITE_SRC else ())
    (OUT / "data").mkdir(exist_ok=True)

    public = {
        "updated_at": data.get("updated_at"),
        "count": len(courses),
        "courses": courses,
    }
    (OUT / "data" / "courses.json").write_text(json.dumps(public, ensure_ascii=False), encoding="utf-8")
    # The dashboard needs to know which repository to talk to.
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    (OUT / "admin").mkdir(exist_ok=True)
    (OUT / "admin" / "repo.js").write_text(f"window.SITE_REPO = {json.dumps(repo)};\n", encoding="utf-8")

    build_index(courses, data, settings, base_url)
    build_course_pages(courses, settings, base_url)
    build_seo_files(courses, data, settings, base_url)
    build_404(settings, base_url)
    log(f"Built {len(courses)} course pages -> {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    run()

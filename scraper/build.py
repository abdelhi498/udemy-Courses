"""Build the static website into _site/ from site/ templates + data/*.json.

Run from the repository root:   python -m scraper.build
Preview locally:                python -m http.server -d _site

Everything that can be changed from the dashboard lives in data/settings.json
(see scraper/settings.py for the defaults). Output:
  index.html                   home page, first cards already in the HTML
  course/<slug>/               one page per course (+ "expired" pages kept for a while)
  category/<slug>/             one page per category
  p/<slug>/                    static pages (about, privacy, contact…)
  sitemap.xml, robots.txt, feed.xml, manifest.webmanifest, ads.txt, CNAME, IndexNow key
  data/courses.json            what the page's JavaScript uses for search and filters
"""

import base64
import html
import json
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from . import settings as settings_mod

ROOT = Path(__file__).resolve().parent.parent
SITE_SRC = ROOT / "site"
DATA_DIR = ROOT / "data"
OUT = ROOT / "_site"

RELATED_COUNT = 8
TEMPLATES = {"index.html", "course.html", "404.html", "category.html", "page.html"}

esc = html.escape


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def render(template, **ctx):
    """Replace {{name}} placeholders. Values must already be escaped where needed."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: str(ctx.get(m.group(1), "")), template)


def fill(pattern, **values):
    """'{title} | {site}' style text from the SEO settings (values are escaped later)."""
    return re.sub(r"\{(\w+)\}", lambda m: str(values.get(m.group(1), m.group(0))), pattern or "")


def slugify(text):
    return re.sub(r"[^\w]+", "-", (text or "").lower()).strip("-")[:80] or "x"


def page_slug(course):
    """URL-safe slug for the course page (stable across coupon changes)."""
    base = course.get("page_slug") or (course["slug"] if course["provider"] == "Udemy" else course["url"])
    return re.sub(r"[^a-z0-9\-]+", "-", base.lower()).strip("-")[:80] or "course"


def fmt_date(iso):
    return datetime.fromisoformat(iso).strftime("%Y-%m-%d")


def b64(text):
    return base64.b64encode(text.encode()).decode()


def jsonld(obj):
    return ('<script type="application/ld+json">'
            + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>")


LANG_AR = {"English": "الإنجليزية", "Arabic": "العربية", "Spanish": "الإسبانية", "French": "الفرنسية",
           "Portuguese": "البرتغالية", "German": "الألمانية", "Turkish": "التركية", "Italian": "الإيطالية",
           "Hindi": "الهندية", "Japanese": "اليابانية", "Indonesian": "الإندونيسية", "Russian": "الروسية",
           "Vietnamese": "الفيتنامية", "Polish": "البولندية", "Urdu": "الأردية", "Chinese": "الصينية",
           "Korean": "الكورية"}


def lang_ar(lang):
    return LANG_AR.get(lang, lang)


# ------------------------------------------------------------------ markdown
def markdown(text):
    """Small Markdown subset for static pages: headings, lists, bold, links, paragraphs."""
    def inline(s):
        s = esc(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+|/[^)\s]*|mailto:[^)\s]+)\)",
                   r'<a href="\2" rel="noopener">\1</a>', s)
        return s

    out, para, items, kind = [], [], [], None

    def flush():
        nonlocal para, items, kind
        if para:
            out.append("<p>" + "<br>".join(inline(p) for p in para) + "</p>")
        if items:
            out.append(f"<{kind}>" + "".join(f"<li>{inline(i)}</li>" for i in items) + f"</{kind}>")
        para, items, kind = [], [], None

    for line in (text or "").splitlines():
        line = line.rstrip()
        h = re.match(r"^(#{1,4})\s+(.*)", line)
        ul = re.match(r"^\s*[-*]\s+(.*)", line)
        ol = re.match(r"^\s*\d+[.)]\s+(.*)", line)
        if not line.strip():
            flush()
        elif h:
            flush()
            level = min(len(h.group(1)) + 1, 4)  # the page title is the h1
            out.append(f"<h{level}>{inline(h.group(2))}</h{level}>")
        elif ul or ol:
            new_kind = "ul" if ul else "ol"
            if para or (kind and kind != new_kind):
                flush()
            kind = new_kind
            items.append((ul or ol).group(1))
        else:
            if items:
                flush()
            para.append(line)
    flush()
    return "\n".join(out)


# ------------------------------------------------------------------ courses
def prepare_courses(courses, s):
    """Apply dashboard rules: hidden, pinned, overrides, blocked words, languages, rating."""
    hidden = set(s["hidden"])
    pinned = s["pinned"]
    content = s["content"]
    blocked = [w.strip().lower() for w in content.get("blocked_words", []) if w.strip()]
    langs = set(content.get("allowed_languages") or [])
    min_rating = float(content.get("min_rating") or 0)
    overrides = content.get("overrides", {})
    out, used = [], set()
    for c in courses:
        if c["id"] in hidden:
            continue
        if c.get("via") and not s["show_indirect_links"]:
            continue  # no direct Udemy link (yet)
        c = dict(c)
        for k, v in (overrides.get(c["id"]) or {}).items():
            if v not in (None, ""):
                c[k] = v
        text = f'{c["title"]} {c.get("category", "")}'.lower()
        if any(w in text for w in blocked):
            continue
        if langs and c.get("language") and c["language"] not in langs:
            continue
        if min_rating and c.get("rating") and c["rating"] < min_rating:
            continue
        c["page"] = page_slug(c)
        if c["page"] in used:  # same course from two sources or two coupons: keep the newest
            continue
        used.add(c["page"])
        c["pinned"] = c["id"] in pinned
        c.pop("description", None)
        out.append(c)
    pins = sorted((c for c in out if c["pinned"]), key=lambda c: pinned.index(c["id"]))
    rest = [c for c in out if not c["pinned"]]
    return pins + rest


def categories_of(courses):
    counts = {}
    for c in courses:
        if c.get("category"):
            counts[c["category"]] = counts.get(c["category"], 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])


# ------------------------------------------------------------------ layout pieces
class Layout:
    """Header, footer, <head> and other parts shared by every page."""

    def __init__(self, s, base_url, courses):
        self.s = s
        self.base = base_url
        self.cats = categories_of(courses)
        # Category pages only where there is enough content (thin pages hurt SEO).
        self.cat_pages = [(n, k) for n, k in self.cats if k >= 3] if s["seo"]["category_pages"] else []

    def cat_href(self, prefix, name):
        if any(n == name for n, _ in self.cat_pages):
            return f"{prefix}category/{quote(slugify(name))}/"
        return None

    # -- helpers
    def ad(self, name):
        slot = self.s["ads"]["slots"].get(name) or {}
        if not slot.get("enabled") or not slot.get("html", "").strip():
            return ""
        return f'<div class="ad ad-{name}">{slot["html"]}</div>'

    def logo(self, prefix):
        ap = self.s["appearance"]
        mark = (f'<img src="{esc(ap["logo_url"])}" alt="">' if ap.get("logo_url")
                else esc(ap.get("logo_emoji") or "🎓"))
        return f'<a class="brand" href="{prefix}"><span class="brand-logo">{mark}</span><span>{esc(self.s["site"]["name"])}</span></a>'

    def socials(self):
        icons = {"facebook": "فيسبوك", "telegram": "تيليجرام", "whatsapp": "واتساب", "youtube": "يوتيوب",
                 "instagram": "إنستجرام", "x": "X", "tiktok": "تيك توك"}
        return [(icons[k], v) for k, v in self.s["site"]["social"].items() if v and k in icons]

    def nav_links(self, prefix):
        links = [(n["label"], n["url"]) for n in self.s["nav"] if n.get("label") and n.get("url")]
        links += [(p["title"], f'{prefix}p/{p["slug"]}/') for p in self.s["pages"] if p.get("in_nav")]
        return links

    # -- pieces
    def head(self, prefix, title, description, canonical, og_image="", extra_ld=(), robots=None, og_type="website"):
        s, seo, ap = self.s, self.s["seo"], self.s["appearance"]
        site = s["site"]
        if seo.get("noindex"):
            robots = "noindex, nofollow"
        icon = (esc(ap["favicon_url"]) if ap.get("favicon_url") else
                "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>"
                + esc(ap.get("logo_emoji") or "🎓") + "</text></svg>")
        og_image = og_image or seo.get("og_image") or ""
        metas = [
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{esc(title)}</title>",
            f'<meta name="description" content="{esc(description)}">',
            f'<link rel="canonical" href="{esc(canonical)}">',
            f'<meta name="robots" content="{robots}">' if robots else "",
            f'<meta property="og:type" content="{og_type}">',
            f'<meta property="og:site_name" content="{esc(site["name"])}">',
            f'<meta property="og:title" content="{esc(title)}">',
            f'<meta property="og:description" content="{esc(description)}">',
            f'<meta property="og:url" content="{esc(canonical)}">',
            '<meta property="og:locale" content="ar_AR">',
            f'<meta property="og:image" content="{esc(og_image)}">' if og_image else "",
            '<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:site" content="{esc(seo["twitter"])}">' if seo.get("twitter") else "",
            f'<meta name="theme-color" content="{esc(ap["accent"])}">',
            f'<meta name="google-site-verification" content="{esc(seo["google_verification"])}">' if seo.get("google_verification") else "",
            f'<meta name="msvalidate.01" content="{esc(seo["bing_verification"])}">' if seo.get("bing_verification") else "",
            f'<meta name="yandex-verification" content="{esc(seo["yandex_verification"])}">' if seo.get("yandex_verification") else "",
            f'<link rel="icon" href="{icon}">',
            f'<link rel="manifest" href="{prefix}manifest.webmanifest">',
            f'<link rel="alternate" type="application/rss+xml" title="{esc(site["name"])}" href="{prefix}feed.xml">' if seo.get("rss") else "",
            '<link rel="preconnect" href="https://fonts.googleapis.com">',
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
            '<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap" rel="stylesheet">',
            f'<link rel="stylesheet" href="{prefix}style.css">',
            self.theme_style(),
            # Saved or default theme, before first paint.
            "<script>try{var t=localStorage.getItem('theme')||" + json.dumps(
                ap["default_theme"] if ap["default_theme"] in ("light", "dark") else "") +
            ";if(t)document.documentElement.dataset.theme=t}catch(e){}</script>",
        ]
        if seo.get("ga_id"):
            gid = esc(seo["ga_id"].strip())
            metas.append(f'<script async src="https://www.googletagmanager.com/gtag/js?id={gid}"></script>'
                         f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}"
                         f"gtag('js',new Date());gtag('config','{gid}');</script>")
        metas += [jsonld(x) for x in extra_ld]
        metas.append(site.get("head_code") or "")
        return "\n  ".join(m for m in metas if m)

    def theme_style(self):
        ap = self.s["appearance"]
        color = re.compile(r"^#[0-9a-fA-F]{3,8}$")
        c = {k: ap[k] for k in ("accent", "accent2", "hero_from", "hero_to") if color.match(str(ap.get(k, "")))}
        radius = max(0, min(32, int(ap.get("radius") or 16)))
        css = [":root,:root:not([data-theme=\"light\"]),:root[data-theme=\"dark\"]{"
               + (f"--accent:{c['accent']};--accent-text:#fff;" if "accent" in c else "")
               + (f"--accent-2:{c['accent2']};" if "accent2" in c else "")
               + f"--radius:{radius}px}}"]
        if "hero_from" in c and "hero_to" in c:
            css.append(".hero{background:radial-gradient(900px 400px at 85% -10%,rgb(255 255 255/.18),transparent 60%),"
                       f"linear-gradient(135deg,{c['hero_from']},{c['hero_to']})}}")
        custom = (ap.get("custom_css") or "").replace("</", "<\\/")
        return "<style>" + "".join(css) + custom + "</style>"

    def announcement(self):
        a = self.s["announcement"]
        if not a.get("enabled") or not a.get("text"):
            return ""
        text = esc(a["text"])
        inner = f'<a href="{esc(a["link"])}">{text}</a>' if a.get("link") else text
        bg = a["color"] if re.match(r"^#[0-9a-fA-F]{3,8}$", a.get("color", "")) else "#f59e0b"
        return f'<div class="announce" style="background:{bg}">{inner}</div>'

    def topnav(self, prefix, back=False):
        links = "".join(f'<a href="{esc(url)}">{esc(label)}</a>' for label, url in self.nav_links(prefix))
        toggle = ('<button id="theme" class="icon-btn" type="button" aria-label="تبديل الوضع الليلي">🌙</button>'
                  if self.s["appearance"]["sections"].get("theme_toggle", True) else "")
        backlink = f'<a class="back" href="{prefix}">كل الكورسات ←</a>' if back else ""
        return (f'{self.announcement()}<nav class="topnav"><div class="wrap topbar">{self.logo(prefix)}'
                f'<div class="nav-links">{links}</div><div class="nav-actions">{backlink}{toggle}</div></div></nav>')

    def footer(self, prefix):
        s = self.s
        pages = "".join(f'<li><a href="{prefix}p/{p["slug"]}/">{esc(p["title"])}</a></li>'
                        for p in s["pages"] if p.get("in_footer"))
        cats = ""
        if s["appearance"]["sections"].get("footer_categories", True):
            cats = "".join(f'<li><a href="{self.cat_href(prefix, name)}">{esc(name)}</a></li>'
                           for name, _ in self.cat_pages[:8])
        social = "".join(f'<a href="{esc(url)}" target="_blank" rel="noopener">{label}</a>' for label, url in self.socials())
        cols = [f'<div class="f-brand">{self.logo(prefix)}<p>{esc(s["texts"]["footer_text"])}</p>'
                f'<div class="social">{social}</div></div>']
        if cats:
            cols.append(f'<div><h4>التصنيفات</h4><ul>{cats}</ul></div>')
        if pages:
            cols.append(f'<div><h4>روابط</h4><ul>{pages}</ul></div>')
        year = datetime.now(timezone.utc).year
        return (f'<footer class="footer"><div class="wrap"><div class="footer-cols">{"".join(cols)}</div>'
                f'<p class="copy">© {year} {esc(s["site"]["name"])}</p></div></footer>')

    def body_end(self, prefix, page_script=""):
        t = self.s["texts"]
        texts = {k: t[k] for k in ("popup_title", "popup_message", "popup_go", "popup_close", "card_button")}
        texts_js = json.dumps(texts, ensure_ascii=False).replace("</", "<\\/")
        return (f'<template id="ad-countdown">{self.ad("countdown")}</template>'
                f"<script>window.SITE_TEXTS={texts_js};</script>"
                f'<script src="{prefix}unlock.js"></script>'
                f'<script src="{prefix}common.js"></script>{page_script}')

    def ctx(self, prefix):
        s = self.s
        return {
            "prefix": prefix,
            "site_name": esc(s["site"]["name"]),
            "topnav": self.topnav(prefix),
            "footer": self.footer(prefix),
            "body_end": self.body_end(prefix),
            "seconds": max(0, min(120, int(s["ads"].get("countdown_seconds") or 0))),
            "ad_header": self.ad("header"),
            "ad_footer": self.ad("footer"),
        }


def card_html(c, prefix, texts):
    """Server-side version of the card that site/app.js renders (keep them in sync)."""
    href = f'{prefix}course/{c["page"]}/'
    img = (f'<img src="{esc(c["image"])}" alt="{esc(c["title"])}" loading="lazy" onerror="this.remove()">'
           if c.get("image") else "")
    old = f'<span class="old-price">${c["price"]:g}</span>' if c.get("price") else ""
    age = datetime.now(timezone.utc) - datetime.fromisoformat(c["posted_at"])
    badges = "".join([
        f'<span class="badge cat">{esc(c["category"])}</span>' if c.get("category") else "",
        '<span class="badge pin">📌 مميز</span>' if c.get("pinned") else "",
        '<span class="badge new">جديد</span>' if age.total_seconds() < 12 * 3600 else "",
        '<span class="badge ok">✓ مؤكد</span>' if c["status"] == "free" else "",
    ])
    facts = "".join([
        f'<span class="rate">{c["rating"]:.1f}' + (f' ({c["reviews"]:,})' if c.get("reviews") else "") + "</span>"
        if c.get("rating") else "",
        f'<span class="left">⏳ باقي {c["uses_left"]} كوبون</span>' if c.get("uses_left") else "",
        f'<span>🌐 {esc(lang_ar(c["language"]))}</span>' if c.get("language") else "",
    ])
    by = f'<p class="by">👤 {esc(c["instructor"])}</p>' if c.get("instructor") else ""
    return (
        f'<article class="card"><a class="thumb" href="{href}" tabindex="-1">{img}'
        f'<span class="ph">{esc(c["provider"])}</span><span class="ribbon">مجاناً</span>{old}</a>'
        f'<div class="body"><div class="meta">{badges}</div>'
        f'<h3 class="title"><a href="{href}">{esc(c["title"])}</a></h3>{by}'
        + (f'<p class="facts">{facts}</p>' if facts else "") +
        f'<div class="card-foot"><p class="time"><time datetime="{esc(c["posted_at"])}">{fmt_date(c["posted_at"])}</time></p>'
        f'<a class="btn primary go" href="{href}" data-unlock data-target="{b64(c["url"])}" '
        f'data-title="{esc(c["title"])}" data-coupon="{esc(c.get("coupon") or "")}">{esc(texts["card_button"])}</a></div></div></article>'
    )


def breadcrumb_ld(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i, "name": n, "item": u}
                                for i, (n, u) in enumerate(items, 1)]}


# ------------------------------------------------------------------ pages
def build_index(courses, data, s, L):
    tpl = (SITE_SRC / "index.html").read_text(encoding="utf-8")
    ap, texts = s["appearance"], s["texts"]
    per_page = max(6, min(96, int(ap.get("cards_per_page") or 24)))
    every = max(2, int(s["ads"].get("in_feed_every") or 6))
    in_feed = L.ad("in_feed")
    cards = []
    for i, c in enumerate(courses[:per_page], 1):
        cards.append(card_html(c, "", texts))
        if in_feed and i % every == 0:
            cards.append(in_feed)
    name = s["site"]["name"]
    website = {"@context": "https://schema.org", "@type": "WebSite", "name": name, "url": L.base,
               "inLanguage": "ar",
               "potentialAction": {"@type": "SearchAction", "target": f"{L.base}?q={{search_term_string}}",
                                   "query-input": "required name=search_term_string"}}
    org = {"@context": "https://schema.org", "@type": "Organization", "name": name, "url": L.base,
           "sameAs": [u for _, u in L.socials()]}
    if s["appearance"].get("logo_url"):
        org["logo"] = s["appearance"]["logo_url"]
    item_list = {"@context": "https://schema.org", "@type": "ItemList",
                 "itemListElement": [{"@type": "ListItem", "position": i, "url": f'{L.base}course/{c["page"]}/',
                                      "name": c["title"]} for i, c in enumerate(courses[:30], 1)]}
    title = fill(s["seo"]["title_home"], site=name)
    ctx = L.ctx("")
    sections = ap["sections"]
    ctx.update(
        head=L.head("", title, s["seo"]["description"], L.base, extra_ld=(website, org, item_list)),
        eyebrow=esc(texts["eyebrow"]), tagline=esc(texts["tagline"]), lead=esc(texts["lead"]),
        search_placeholder=esc(texts["search_placeholder"]),
        stats_hidden="" if sections.get("stats", True) else "hidden",
        filters_hidden="" if sections.get("filters", True) else "hidden",
        cats_hidden="" if sections.get("categories", True) else "hidden",
        count=len(courses),
        updated=esc(data.get("updated_at") or ""),
        cards="".join(cards),
        in_feed_template=in_feed,
        in_feed_every=every,
        per_page=per_page,
        default_sort=esc(ap.get("default_sort") or "new"),
        body_end=L.body_end("", '<script src="app.js"></script>'),
    )
    (OUT / "index.html").write_text(render(tpl, **ctx), encoding="utf-8")


def course_details(c):
    details = [
        ("السعر الأصلي", f'${c["price"]:g} ← مجاناً' if c.get("price") else None),
        ("المدة", c.get("duration") or (f'{c["lectures"]} محاضرة' if c.get("lectures") else None)),
        ("اللغة", lang_ar(c["language"]) if c.get("language") else None),
        ("التقييم", f'⭐ {c["rating"]:.1f}' + (f' ({c["reviews"]:,} تقييم)' if c.get("reviews") else "")
         if c.get("rating") else None),
        ("الكوبونات المتبقية", f'⏳ {c["uses_left"]}' if c.get("uses_left") else None),
        ("عدد الطلاب", f'{c["students"]:,}' if c.get("students") else None),
        ("المدرّب", c.get("instructor")),
        ("التصنيف", c.get("category")),
        ("آخر تحديث للكورس", c.get("updated")),
    ]
    rows = "".join(f"<div><dt>{k}</dt><dd>{esc(str(v))}</dd></div>" for k, v in details if v)
    return f'<dl class="details">{rows}</dl>' if rows else ""


def build_course_page(c, courses, s, L, expired=False):
    tpl = (SITE_SRC / "course.html").read_text(encoding="utf-8")
    prefix = "../../"
    url = f'{L.base}course/{c["page"]}/'
    title = c["title"]
    texts = s["texts"]
    desc = (f'احصل على كورس "{title}" على {c["provider"]} مجاناً بخصم 100%.'
            + (f' {c["subtitle"]}' if c.get("subtitle") else "")
            + " الكوبون محدود العدد والمدة، فسارع بالتسجيل.")
    if s["appearance"]["sections"].get("related", True) or expired:
        same = [r for r in courses if r is not c and r.get("category") == c.get("category")]
        others = [r for r in courses if r is not c and r not in same]
        related = (same + others)[:RELATED_COUNT]
    else:
        related = []
    crumbs = [("الرئيسية", L.base)]
    cat_link = ""
    if c.get("category"):
        href = L.cat_href(prefix, c["category"])
        if href:
            crumbs.append((c["category"], L.cat_href(L.base, c["category"])))
            cat_link = f'<a href="{href}">{esc(c["category"])}</a> › '
        else:
            cat_link = f'<span>{esc(c["category"])}</span> › '
    crumbs.append((title, url))
    course_ld = {
        "@context": "https://schema.org", "@type": "Course", "name": title, "description": desc, "url": url,
        "inLanguage": c.get("language") or "",
        "provider": {"@type": "Organization", "name": c["provider"], "sameAs": "https://www.udemy.com"},
        "offers": {"@type": "Offer", "category": "Free", "price": 0, "priceCurrency": "USD", "url": url,
                   "availability": "https://schema.org/SoldOut" if expired else "https://schema.org/LimitedAvailability"},
        "hasCourseInstance": {"@type": "CourseInstance", "courseMode": "Online", "courseWorkload": "PT1H"},
    }
    if c.get("image"):
        course_ld["image"] = c["image"]
    if c.get("instructor"):
        course_ld["instructor"] = {"@type": "Person", "name": c["instructor"]}
    if c.get("rating") and c.get("reviews"):
        course_ld["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": c["rating"],
                                        "ratingCount": c["reviews"], "bestRating": 5}
    page_title = fill(s["seo"]["title_course"], title=title, site=s["site"]["name"], category=c.get("category", ""))
    ctx = L.ctx(prefix)
    ctx.update(
        head=L.head(prefix, page_title, desc, url, og_image=c.get("image") or "", og_type="article",
                    extra_ld=(course_ld, breadcrumb_ld(crumbs)), robots="noindex, follow" if expired else None),
        topnav=L.topnav(prefix, back=True),
        course_title=esc(title),
        course_desc=esc(c.get("subtitle") or desc),
        details=course_details(c),
        provider=esc(c["provider"]),
        image=(f'<img src="{esc(c["image"])}" alt="{esc(title)}" onerror="this.remove()">' if c.get("image") else ""),
        status=(f'<span class="badge cat">{esc(c["category"])}</span>' if c.get("category") else "")
        + ('<span class="badge ok">✓ مجاني مؤكد</span>' if c["status"] == "free" and not expired else "")
        + ('<span class="badge unknown">⌛ انتهى الكوبون</span>' if expired else ""),
        category_crumb=cat_link,
        price_old=(f'<span class="price-old">${c["price"]:g}</span><span class="price-off">-100%</span>'
                   if c.get("price") else ""),
        posted=esc(c["posted_at"]),
        posted_date=fmt_date(c["posted_at"]),
        channel=esc(c["channel"]),
        source=esc(c.get("source") or ""),
        source_hidden="" if c.get("source") else "hidden",
        target=b64(c["url"]),
        coupon=esc(c.get("coupon") or ""),
        course_button=esc(texts["course_button"]),
        course_hint=esc(texts["course_hint"]),
        expired_notice=(f'<div class="expired">{esc(texts["expired_notice"])}</div>' if expired else ""),
        buy_hidden="hidden" if expired else "",
        ad_course_bottom=L.ad("course_bottom"),
        related_hidden="" if related else "hidden",
        related="".join(card_html(r, prefix, texts) for r in related),
    )
    page_dir = OUT / "course" / c["page"]
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "index.html").write_text(render(tpl, **ctx), encoding="utf-8")


def build_category_pages(courses, s, L):
    tpl = (SITE_SRC / "category.html").read_text(encoding="utf-8")
    prefix = "../../"
    made = []
    for name, count in L.cat_pages:
        slug = slugify(name)
        url = f"{L.base}category/{quote(slug)}/"
        items = [c for c in courses if c.get("category") == name]
        title = fill(s["seo"]["title_category"], category=name, site=s["site"]["name"])
        desc = f"{count} كورس {name} مجاني على يوديمي بكوبون خصم 100% — قائمة تتحدث تلقائياً كل ساعة."
        item_list = {"@context": "https://schema.org", "@type": "ItemList",
                     "itemListElement": [{"@type": "ListItem", "position": i, "url": f'{L.base}course/{c["page"]}/',
                                          "name": c["title"]} for i, c in enumerate(items[:50], 1)]}
        ctx = L.ctx(prefix)
        ctx.update(
            head=L.head(prefix, title, desc, url,
                        extra_ld=(item_list, breadcrumb_ld([("الرئيسية", L.base), (name, url)]))),
            topnav=L.topnav(prefix, back=True),
            category=esc(name), count=count, description=esc(desc),
            cards="".join(card_html(c, prefix, s["texts"]) for c in items),
            other_cats="".join(f'<a class="chip" href="{prefix}category/{quote(slugify(n))}/">{esc(n)} <small>{k}</small></a>'
                               for n, k in L.cat_pages if n != name),
        )
        page_dir = OUT / "category" / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(render(tpl, **ctx), encoding="utf-8")
        made.append(url)
    return made


def build_static_pages(s, L):
    tpl = (SITE_SRC / "page.html").read_text(encoding="utf-8")
    prefix = "../../"
    made = []
    for p in s["pages"]:
        slug = slugify(p.get("slug") or p.get("title"))
        p["slug"] = slug
        url = f"{L.base}p/{slug}/"
        body = p.get("body", "")
        html_body = body if p.get("html") else markdown(body)
        plain = re.sub(r"<[^>]+>|[#*\[\]()]", " ", html_body if p.get("html") else body)
        desc = p.get("description") or re.sub(r"\s+", " ", plain).strip()[:155]
        ctx = L.ctx(prefix)
        ctx.update(
            head=L.head(prefix, f'{p["title"]} | {s["site"]["name"]}', desc, url,
                        extra_ld=(breadcrumb_ld([("الرئيسية", L.base), (p["title"], url)]),)),
            topnav=L.topnav(prefix, back=True),
            page_title=esc(p["title"]), page_body=html_body,
        )
        page_dir = OUT / "p" / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(render(tpl, **ctx), encoding="utf-8")
        made.append(url)
    return made


def build_404(s, L):
    tpl = (SITE_SRC / "404.html").read_text(encoding="utf-8")
    ctx = L.ctx(L.base)  # served for any path, so links must be absolute
    ctx["head"] = L.head(L.base, f'الصفحة غير موجودة | {s["site"]["name"]}', s["seo"]["description"],
                         L.base, robots="noindex")
    (OUT / "404.html").write_text(render(tpl, **ctx), encoding="utf-8")


def build_seo_files(courses, data, s, L, extra_urls):
    base, seo = L.base, s["seo"]
    today = (data.get("updated_at") or datetime.now(timezone.utc).isoformat())[:10]
    urls = [f"  <url><loc>{base}</loc><lastmod>{today}</lastmod><changefreq>hourly</changefreq><priority>1.0</priority></url>"]
    urls += [f"  <url><loc>{esc(u)}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>" for u in extra_urls]
    urls += [f'  <url><loc>{esc(base)}course/{c["page"]}/</loc><lastmod>{c["posted_at"][:10]}</lastmod></url>'
             for c in courses]
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls) + "\n</urlset>\n", encoding="utf-8")
    robots = ("User-agent: *\nDisallow: /\n" if seo.get("noindex") else
              f"User-agent: *\nAllow: /\nDisallow: /admin/\n\nSitemap: {base}sitemap.xml\n")
    (OUT / "robots.txt").write_text(robots, encoding="utf-8")
    if seo.get("rss"):
        items = "".join(
            f"<item><title>{esc(c['title'])}</title><link>{base}course/{c['page']}/</link>"
            f"<guid>{base}course/{c['page']}/</guid>"
            f"<pubDate>{datetime.fromisoformat(c['posted_at']).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>"
            + (f"<category>{esc(c['category'])}</category>" if c.get("category") else "")
            + (f'<enclosure url="{esc(c["image"])}" type="image/jpeg" length="0"/>' if c.get("image") else "")
            + f"<description>{esc(c.get('subtitle') or c['title'])}</description></item>"
            for c in sorted(courses, key=lambda c: c["posted_at"], reverse=True)[:50])
        (OUT / "feed.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            f"<title>{esc(s['site']['name'])}</title><link>{base}</link>"
            f"<description>{esc(seo['description'])}</description><language>ar</language>{items}</channel></rss>",
            encoding="utf-8")
    manifest = {"name": s["site"]["name"], "short_name": s["site"]["name"][:12], "lang": "ar", "dir": "rtl",
                "start_url": "./", "display": "standalone", "background_color": "#ffffff",
                "theme_color": s["appearance"]["accent"]}
    if s["appearance"].get("logo_url"):
        manifest["icons"] = [{"src": s["appearance"]["logo_url"], "sizes": "512x512"}]
    (OUT / "manifest.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    ads_txt = s["ads"].get("ads_txt", "").strip()
    if ads_txt:
        (OUT / "ads.txt").write_text(ads_txt + "\n", encoding="utf-8")
    domain = s["site"].get("custom_domain", "").strip().strip("/")
    if domain:
        (OUT / "CNAME").write_text(domain + "\n", encoding="utf-8")
    key = re.sub(r"[^A-Za-z0-9\-]", "", seo.get("indexnow_key") or "")
    if seo.get("indexnow") and len(key) >= 8:
        (OUT / f"{key}.txt").write_text(key, encoding="utf-8")


def site_url(s):
    if s["site"].get("custom_domain"):
        return f'https://{s["site"]["custom_domain"].strip().strip("/")}/'
    return s["site"]["url"].rstrip("/") + "/"


def run(log=print):
    s = settings_mod.normalise(load(DATA_DIR / "settings.json", {}))
    data = load(DATA_DIR / "courses.json", {"courses": []})
    courses = prepare_courses(data.get("courses", []), s)
    base_url = site_url(s)
    L = Layout(s, base_url, courses)

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE_SRC, OUT, ignore=lambda d, names: TEMPLATES & set(names) if Path(d) == SITE_SRC else ())
    (OUT / "data").mkdir(exist_ok=True)
    (OUT / "data" / "courses.json").write_text(
        json.dumps({"updated_at": data.get("updated_at"), "count": len(courses), "courses": courses},
                   ensure_ascii=False), encoding="utf-8")
    repo = os.environ.get("GITHUB_REPOSITORY", "")  # the dashboard needs to know which repository to use
    (OUT / "admin").mkdir(exist_ok=True)
    (OUT / "admin" / "repo.js").write_text(f"window.SITE_REPO = {json.dumps(repo)};\n", encoding="utf-8")
    # Defaults, roles and section permissions shared with the dashboard (single source of truth).
    (OUT / "admin" / "defaults.js").write_text(
        "window.SETTINGS_DEFAULTS = " + json.dumps(settings_mod.DEFAULTS, ensure_ascii=False) + ";\n"
        + "window.SETTINGS_ROLES = " + json.dumps(settings_mod.ROLES) + ";\n"
        + "window.SECTION_PERMISSION = " + json.dumps(settings_mod.SECTION_PERMISSION) + ";\n",
        encoding="utf-8")

    build_index(courses, data, s, L)
    for c in courses:
        build_course_page(c, courses, s, L)
    # Courses whose coupon ended keep their page for a while (people may still arrive from Google/shares).
    keep = timedelta(days=int(s["seo"].get("keep_expired_days") or 0))
    live = {c["page"] for c in courses}
    expired = 0
    for c in load(DATA_DIR / "archive.json", {}).values():
        c = dict(c, page=page_slug(c))
        removed = datetime.fromisoformat(c.get("removed_at") or c["posted_at"])
        if c["page"] not in live and datetime.now(timezone.utc) - removed <= keep:
            build_course_page(c, courses, s, L, expired=True)
            expired += 1
    extra = build_category_pages(courses, s, L) + build_static_pages(s, L)
    build_seo_files(courses, data, s, L, extra)
    build_404(s, L)
    log(f"Built {len(courses)} course pages, {expired} expired pages, {len(extra)} other pages -> {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    run()

"""Find course coupon links in message text/links and normalise them."""

import re
from urllib.parse import parse_qs, urlencode, urlparse

from . import http

# Platforms we recognise. Udemy needs a coupon code to count as a "free" offer;
# the others are kept when a channel posts them (they are usually free promos).
PROVIDERS = {
    "udemy.com": "Udemy",
    "eduonix.com": "Eduonix",
    "coursera.org": "Coursera",
    "edx.org": "edX",
    "skillshare.com": "Skillshare",
    "linkedin.com/learning": "LinkedIn Learning",
    "packtpub.com": "Packt",
    "stackskills.com": "StackSkills",
}

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
UDEMY_COUPON_RE = re.compile(
    r"https?://(?:www\.)?udemy\.com/course/[\w\-]+/?\?[^\s<>\"']*couponCode=[\w\-\.]+",
    re.I,
)
# Domains that never lead to a course (social, Telegram itself, shorteners we can't read…).
IGNORED_HOSTS = ("t.me", "telegram.me", "telegram.org", "youtube.com", "youtu.be",
                 "facebook.com", "instagram.com", "twitter.com", "x.com", "whatsapp.com")


def provider_for(url):
    p = urlparse(url)
    host = p.netloc.lower().removeprefix("www.")
    for domain, name in PROVIDERS.items():
        d_host, _, d_path = domain.partition("/")
        if (host == d_host or host.endswith("." + d_host)) and p.path.startswith("/" + d_path if d_path else "/"):
            return name
    return None


def normalise_udemy(url):
    """Return {slug, coupon, url} for a Udemy coupon link, else None."""
    p = urlparse(url)
    m = re.match(r"/course/([\w\-]+)", p.path)
    coupon = (parse_qs(p.query).get("couponCode") or [None])[0]
    if not m or not coupon:
        return None
    slug = m.group(1)
    return {
        "slug": slug,
        "coupon": coupon,
        "url": f"https://www.udemy.com/course/{slug}/?" + urlencode({"couponCode": coupon}),
    }


def candidate_links(message):
    """All distinct http(s) links of a message (anchors first, then bare text URLs)."""
    seen, out = set(), []
    for url in message.get("links", []) + URL_RE.findall(message.get("text", "")):
        url = url.rstrip(".,;")
        if url.startswith("http") and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def is_ignored(url):
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return any(host == h or host.endswith("." + h) for h in IGNORED_HOSTS)


def resolve(url, cache, log=print):
    """Follow a redirect/landing page and return the Udemy coupon URL it points to.

    Many channels link to their own site (or a shortener) instead of Udemy directly.
    Results are cached (including misses) so each link is fetched only once.
    """
    if url in cache:
        return cache[url]
    result = None
    try:
        final_url, body = http.fetch(url, retries=0, timeout=15)
        if normalise_udemy(final_url):
            result = final_url
        else:
            m = UDEMY_COUPON_RE.search(body.replace("&amp;", "&"))
            result = m.group(0) if m else None
    except Exception as e:  # noqa: BLE001
        log(f"  ! resolve {url}: {e}")
    cache[url] = result
    return result

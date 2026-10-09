"""One-off diagnostic: which coupon sites can GitHub's servers read, and do they expose
direct Udemy coupon links? Run by .github/workflows/probe.yml; prints a JSON report.
"""

import json
import re
import sys
import time

from . import http

UDEMY = re.compile(r"https?://(?:www\.)?udemy\.com/course/[\w\-]+/?\?[^\s<>\"'\\]*couponCode=[\w\-\.]+", re.I)

PAGES = {
    "courson_home": "https://courson.xyz/",
    "courson_list": "https://courson.xyz/coupons",
    "courson_coupon": "https://courson.xyz/coupon/scrum-master-certification-aec",
    "realdiscount_api_cdn": "https://cdn.real.discount/api/courses?page=1&limit=20&sortBy=sale_start&store=Udemy&freeOnly=true",
    "realdiscount_api_web": "https://www.real.discount/api-web/all-courses/?store=Udemy&page=1&per_page=20&orderby=date&free=1",
    "discudemy_list": "https://www.discudemy.com/all/1",
    "udemyfreebies_list": "https://www.udemyfreebies.com/free-udemy-courses/1",
    "coursevania_list": "https://coursevania.com/courses/",
    "idownloadcoupon_list": "https://idownloadcoupon.com/product-category/udemy-2/",
    "tutorialbar_list": "https://www.tutorialbar.com/all-courses/",
    "coursejoiner_list": "https://www.coursejoiner.com/category/free-udemy/",
}


def summarise(name, url, final, body, seconds, mode):
    links = sorted(set(UDEMY.findall(body.replace("&amp;", "&").replace("\\/", "/"))))
    hrefs = re.findall(r'href="([^"]+)"', body)
    return {
        "name": name, "mode": mode, "url": url, "final": final, "seconds": seconds,
        "length": len(body), "udemy_coupon_links": len(links), "sample_links": links[:3],
        "sample_hrefs": [h for h in hrefs if h.startswith("http") and "udemy" not in h][:25],
        "title": (re.search(r"<title>(.*?)</title>", body, re.S) or [None, ""])[1].strip()[:120],
        "head": re.sub(r"\s+", " ", body[:1200]),
    }


def plain():
    out = []
    for name, url in PAGES.items():
        t0 = time.monotonic()
        try:
            final, body = http.fetch(url, retries=0, timeout=30)
            out.append(summarise(name, url, final, body, round(time.monotonic() - t0, 1), "http"))
        except Exception as e:  # noqa: BLE001
            out.append({"name": name, "mode": "http", "url": url, "error": repr(e)[:200],
                        "seconds": round(time.monotonic() - t0, 1)})
    return out


def browser():
    out = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [{"error": "playwright not installed"}]
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(user_agent=http.USER_AGENT, locale="en-US")
        for name, url in PAGES.items():
            if not name.startswith(("courson", "discudemy", "udemyfreebies")):
                continue
            t0 = time.monotonic()
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(6000)  # let any challenge / JS finish
                body = page.content()
                r = summarise(name, url, page.url, body, round(time.monotonic() - t0, 1), "browser")
                r["status"] = resp.status if resp else None
                out.append(r)
            except Exception as e:  # noqa: BLE001
                out.append({"name": name, "mode": "browser", "url": url, "error": repr(e)[:300],
                            "seconds": round(time.monotonic() - t0, 1)})
        b.close()
    return out


if __name__ == "__main__":
    report = plain() + (browser() if "--browser" in sys.argv else [])
    print("PROBE_REPORT_START")
    print(json.dumps(report, ensure_ascii=False))
    print("PROBE_REPORT_END")

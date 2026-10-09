"""One-off diagnostic: find coupon sites whose pages (or RSS feeds) lead to direct Udemy
coupon links when read from GitHub's servers. Run by .github/workflows/probe.yml.
"""

import json
import re
import time
from urllib.parse import urljoin, urlparse

from . import http

UDEMY = re.compile(r"https?://(?:www\.)?udemy\.com/course/[\w\-]+/?\?[^\s<>\"'\\]*couponCode=[\w\-\.]+", re.I)

# name: (start url, regex for detail-page links on that start page or None)
SITES = {
    "tutorialbar": ("https://www.tutorialbar.com/", None),
    "coursevania_feed": ("https://coursevania.com/feed/", None),
    "coursevania_list": ("https://coursevania.com/courses/", r"https://coursevania\.com/courses/[\w\-]+/$"),
    "idownloadcoupon_feed": ("https://idownloadcoupon.com/feed/", None),
    "idownloadcoupon_home": ("https://idownloadcoupon.com/", r"https://idownloadcoupon\.com/udemy/[\w\-]+/?$"),
    "discudemy": ("https://www.discudemy.com/all/1", r"https://www\.(?:couponami|discudemy)\.com/(?!category)[\w\-]+/[\w\-]+$"),
    "udemyfreebies": ("https://www.udemyfreebies.com/free-udemy-courses/1", r"https://www\.udemyfreebies\.com/free-udemy-course/[\w\-]+"),
    "onlinecourses_ooo_feed": ("https://www.onlinecourses.ooo/feed/", None),
    "couponscorpion_feed": ("https://couponscorpion.com/feed/", None),
    "freewebcart_feed": ("https://www.freewebcart.com/feed", None),
    "easylearn_feed": ("https://www.easylearn.ing/feed", None),
    "infognu_feed": ("https://infognu.com/feed/", None),
}


def links_in(body, base):
    return [urljoin(base, h.replace("&amp;", "&")) for h in re.findall(r'href=["\']([^"\']+)["\']', body)]


def udemy_in(body):
    return sorted(set(UDEMY.findall(body.replace("&amp;", "&").replace("\\/", "/").replace("\\u0026", "&"))))


def get(url):
    t0 = time.monotonic()
    try:
        final, body = http.fetch(url, retries=0, timeout=25)
        return {"ok": True, "final": final, "body": body, "s": round(time.monotonic() - t0, 1)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": repr(e)[:160], "s": round(time.monotonic() - t0, 1)}


def probe(name, url, detail_re):
    r = get(url)
    out = {"name": name, "url": url, "seconds": r["s"]}
    if not r["ok"]:
        out["error"] = r["error"]
        return out
    body = r["body"]
    found = udemy_in(body)
    out.update(final=r["final"], length=len(body), udemy_links=len(found), sample=found[:2])
    if found:
        i = body.replace("&amp;", "&").find(found[0].split("?")[0].split("udemy.com")[1])
        out["context"] = re.sub(r"\s+", " ", body[max(0, i - 1500):i + 300])
    out["has_next_data"] = "__NEXT_DATA__" in body
    out["has_rsc"] = "self.__next_f" in body
    if detail_re and not found:
        details = []
        for link in dict.fromkeys(l for l in links_in(body, r["final"]) if re.match(detail_re, l)):
            details.append(link)
            if len(details) == 2:
                break
        out["details"] = []
        for d in details:
            dr = get(d)
            info = {"url": d, "ok": dr["ok"]}
            if dr["ok"]:
                dfound = udemy_in(dr["body"])
                info["udemy_links"] = dfound[:2]
                if not dfound:
                    hops = [l for l in links_in(dr["body"], d)
                            if re.search(r"/(go|out|redirect|link|visit)/", l) and urlparse(l).netloc == urlparse(d).netloc]
                    info["hop_candidates"] = hops[:3]
                    if hops:
                        hr = get(hops[0])
                        info["hop"] = {"url": hops[0], "ok": hr["ok"], "final": hr.get("final"),
                                       "udemy_links": udemy_in(hr.get("body", ""))[:2]}
            else:
                info["error"] = dr["error"]
            out["details"].append(info)
    return out


if __name__ == "__main__":
    report = [probe(n, u, d) for n, (u, d) in SITES.items()]
    print("PROBE_REPORT_START")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    print("PROBE_REPORT_END")

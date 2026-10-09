"""Tell search engines (Bing, Yandex, Seznam… via IndexNow) about new pages right away.

Runs after each deploy when "IndexNow" is on in the dashboard (SEO tab). The key file
is published at the site root by scraper/build.py.
"""

import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from . import build, settings as settings_mod


def run(log=print):
    s = settings_mod.normalise(build.load(build.DATA_DIR / "settings.json", {}))
    key = re.sub(r"[^A-Za-z0-9\-]", "", s["seo"].get("indexnow_key") or "")
    if not s["seo"].get("indexnow") or len(key) < 8 or s["seo"].get("noindex"):
        log("IndexNow is off")
        return
    base = build.site_url(s)
    courses = build.prepare_courses(build.load(build.DATA_DIR / "courses.json", {}).get("courses", []), s)
    since = datetime.now(timezone.utc) - timedelta(hours=2)
    urls = [base] + [f'{base}course/{c["page"]}/' for c in courses if datetime.fromisoformat(c["posted_at"]) >= since]
    body = json.dumps({"host": urlparse(base).netloc, "key": key, "keyLocation": f"{base}{key}.txt",
                       "urlList": urls[:10000]}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            log(f"IndexNow: sent {len(urls)} URLs ({r.status})")
    except Exception as e:  # noqa: BLE001 - never fail the deploy for this
        log(f"IndexNow failed: {e}")


if __name__ == "__main__":
    run()

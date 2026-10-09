"""Tiny HTTP helper built on the standard library (no dependencies)."""

import gzip
import json
import time
import urllib.error
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def fetch(url, timeout=20, retries=2, accept="text/html,application/json"):
    """Return (final_url, body_text). Raises on final failure."""
    last_error = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": accept,
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.geturl(), raw.decode(charset, errors="replace")
        except urllib.error.HTTPError as e:
            # 4xx won't get better with a retry.
            if 400 <= e.code < 500 and e.code != 429:
                raise
            last_error = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_error = e
        time.sleep(1.5 * (attempt + 1))
    raise last_error


def fetch_json(url, **kwargs):
    _, body = fetch(url, accept="application/json", **kwargs)
    return json.loads(body)

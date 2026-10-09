"""Read public Telegram channels through their web preview (https://t.me/s/<channel>).

No API key or Telegram account is needed, but it only works for *public* channels.
"""

import re
from html.parser import HTMLParser

from . import http

BG_IMAGE_RE = re.compile(r"background-image:\s*url\(['\"]?([^'\")]+)['\"]?\)")


class _ChannelPageParser(HTMLParser):
    """Collects every message on a t.me/s page: id, date, text, links, photo."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.messages = []
        self._msg = None
        self._msg_depth = 0      # div nesting depth inside the current message
        self._text_depth = 0     # div nesting depth inside the message text block

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()

        if tag == "div" and "tgme_widget_message" in classes and a.get("data-post"):
            self._msg = {"post": a["data-post"], "text": [], "links": [], "date": None, "photo": None}
            self._msg_depth = 1
            self._text_depth = 0
            return
        if self._msg is None:
            return

        if tag == "div":
            self._msg_depth += 1
            if self._text_depth:
                self._text_depth += 1
            elif "tgme_widget_message_text" in classes:
                self._text_depth = 1
        if tag == "br" and self._text_depth:
            self._msg["text"].append("\n")
        if tag == "a" and a.get("href"):
            self._msg["links"].append(a["href"])
        if tag == "time" and a.get("datetime") and not self._msg["date"]:
            self._msg["date"] = a["datetime"]
        if "tgme_widget_message_photo_wrap" in classes and not self._msg["photo"]:
            m = BG_IMAGE_RE.search(a.get("style") or "")
            if m:
                self._msg["photo"] = m.group(1)

    def handle_endtag(self, tag):
        if self._msg is None or tag != "div":
            return
        if self._text_depth:
            self._text_depth -= 1
        self._msg_depth -= 1
        if self._msg_depth == 0:
            self._msg["text"] = "".join(self._msg["text"]).strip()
            self.messages.append(self._msg)
            self._msg = None

    def handle_data(self, data):
        if self._msg is not None and self._text_depth:
            self._msg["text"].append(data)


def parse_channel_page(html):
    parser = _ChannelPageParser()
    parser.feed(html)
    for m in parser.messages:
        m["id"] = int(m["post"].rsplit("/", 1)[-1])
    return parser.messages


def fetch_channel(channel, pages=1, log=print):
    """Fetch the latest `pages` pages of a public channel (≈20 messages per page)."""
    messages = []
    before = None
    for _ in range(pages):
        url = f"https://t.me/s/{channel}" + (f"?before={before}" if before else "")
        try:
            _, html = http.fetch(url)
        except Exception as e:  # noqa: BLE001 - one bad channel must not stop the run
            log(f"  ! {channel}: {e}")
            break
        page = parse_channel_page(html)
        if not page:
            break
        messages.extend(page)
        before = min(m["id"] for m in page)
    for m in messages:
        m["channel"] = channel
    return messages

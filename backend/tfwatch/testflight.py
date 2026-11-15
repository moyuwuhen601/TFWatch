import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx

HOST = "testflight.apple.com"
STATUSES = ("open", "full", "closed", "unknown")
INVITE_PATH = re.compile(r"/join/([A-Za-z0-9]{8})/?")


def invite_code(value):
    parsed = urlsplit(value.strip())
    match = INVITE_PATH.fullmatch(parsed.path)
    if parsed.scheme != "https" or parsed.netloc.lower() != HOST or not match:
        raise ValueError("请输入有效的 TestFlight 公开邀请链接")
    return match[1]


def invite_url(code):
    return f"https://{HOST}/join/{code}"


@dataclass(frozen=True)
class Observation:
    status: str
    name: str = ""
    icon: str = ""


class ApplePage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.status_depth = 0
        self.status_text = []
        self.meta = {}
        self.join_links = set()

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "div":
            if self.status_depth:
                self.status_depth += 1
            elif "beta-status" in (attrs.get("class") or "").split():
                self.status_depth = 1
        elif tag == "meta":
            self.meta[attrs.get("property")] = attrs.get("content") or ""
        elif tag == "a":
            href = attrs.get("href") or ""
            if href.startswith("itms-beta://"):
                self.join_links.add(href)

    def handle_endtag(self, tag):
        if tag == "div" and self.status_depth:
            self.status_depth -= 1

    def handle_data(self, value):
        if self.status_depth:
            self.status_text.append(value)


def parse_page(code, status_code, body):
    # A bare HTTP error can come from an edge or proxy, so it supplies no beta status.
    if status_code != 200:
        return Observation("unknown")

    page = ApplePage()
    page.feed(body)
    message = " ".join(" ".join(page.status_text).split()).casefold().replace("’", "'")
    if message == "this beta is full.":
        status = "full"
    elif message in {
        "this beta isn't accepting any new testers right now.",
        "this beta isn't accepting any new testers.",
        "this beta is no longer accepting new testers.",
        "this beta is no longer available.",
    }:
        status = "closed"
    elif (message.startswith("to join the ") and "after you install testflight." in message
          and f"itms-beta://{HOST}/join/{code}" in page.join_links):
        status = "open"
    else:
        return Observation("unknown")

    title = re.fullmatch(r"Join the (.+) beta", page.meta.get("og:title", ""), re.IGNORECASE)
    icon = page.meta.get("og:image", "")
    if not re.fullmatch(r"https://[\w-]+\.mzstatic\.com/[\w%./~@+-]+", icon) or len(icon) > 1000:
        icon = ""
    name = " ".join(title[1].split())[:180] if title else ""
    return Observation(status, name, icon)


def check(client, code):
    try:
        started = time.monotonic()
        with client.stream("GET", invite_url(code)) as response:
            if response.status_code != 200 or "text/html" not in response.headers.get("content-type", ""):
                return Observation("unknown")
            body = bytearray()
            for chunk in response.iter_bytes(chunk_size=16384):
                body.extend(chunk)
                if len(body) > 1024 * 1024 or time.monotonic() - started > 18:
                    return Observation("unknown")
            return parse_page(code, response.status_code, body.decode("utf-8", errors="replace"))
    except (httpx.HTTPError, ValueError, AssertionError):
        return Observation("unknown")

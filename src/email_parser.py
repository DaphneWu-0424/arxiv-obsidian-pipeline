from __future__ import annotations

import re
from typing import List, Set
from urllib.parse import urlparse
from bs4 import BeautifulSoup

ARXIV_ABS_RE = re.compile(r"https?://arxiv\.org/abs/([a-z\-]+/\d{7}|\d{4}\.\d{4,5})(v\d+)?", re.I)
ARXIV_PDF_RE = re.compile(r"https?://arxiv\.org/pdf/([a-z\-]+/\d{7}|\d{4}\.\d{4,5})(v\d+)?(?:\.pdf)?", re.I)

def extract_urls_from_text(text: str) -> List[str]:
    if not text:
        return []

    url_re = re.compile(r"https?://[^\s<>\"]+")
    return url_re.findall(text)

def extract_urls_from_html(html: str) -> List[str]:
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    urls = []

    for a in soup.find_all("a", href=True):
        urls.append(a["href"])

    # 有些邮件正文其实是纯文本混在 HTML 里，再补扫一次文本
    urls.extend(extract_urls_from_text(soup.get_text("\n")))

    return urls

def extract_arxiv_id(url: str) -> str | None:
    if not url:
        return None

    m = ARXIV_ABS_RE.search(url)
    if m:
        return m.group(1)

    m = ARXIV_PDF_RE.search(url)
    if m:
        return m.group(1)

    return None


def normalize_arxiv_url(url: str) -> str | None:
    arxiv_id = extract_arxiv_id(url)
    if not arxiv_id:
        return None
    return f"https://arxiv.org/abs/{arxiv_id}"


def extract_arxiv_ids_from_content(content: str) -> List[str]:
    urls = extract_urls_from_text(content)
    ids: Set[str] = set()

    for url in urls:
        arxiv_id = extract_arxiv_id(url)
        if arxiv_id:
            ids.add(arxiv_id)

    return sorted(ids)
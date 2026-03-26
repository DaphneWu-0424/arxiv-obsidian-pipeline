from __future__ import annotations

from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup


USER_AGENT = "arxiv-obsidian-pipeline/0.1 (+local knowledge base)"


class FullTextFetcher:
    def __init__(self, pdf_cache_dir: str = "data/pdfs", html_cache_dir: str = "data/html", timeout: int = 30):
        self.pdf_cache_dir = Path(pdf_cache_dir)
        self.html_cache_dir = Path(html_cache_dir)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.pdf_cache_dir.mkdir(parents=True, exist_ok=True)
        self.html_cache_dir.mkdir(parents=True, exist_ok=True)

    def enrich_paper_assets(self, paper: dict) -> dict:
        paper = dict(paper)
        arxiv_id = paper.get("arxiv_id", "").strip()
        if not arxiv_id:
            return paper

        abs_url = paper.get("abs_url") or f"https://arxiv.org/abs/{arxiv_id}"
        pdf_url = paper.get("pdf_url") or f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        html_url = self.discover_html_url(abs_url)
        local_pdf_path = self.download_pdf(arxiv_id, pdf_url)
        local_html_path = self.download_html(arxiv_id, html_url) if html_url else ""

        paper["abs_url"] = abs_url
        paper["pdf_url"] = pdf_url
        paper["html_url"] = html_url or ""
        paper["local_pdf_path"] = local_pdf_path
        paper["local_html_path"] = local_html_path
        return paper

    def discover_html_url(self, abs_url: str) -> str:
        try:
            resp = self.session.get(abs_url, timeout=self.timeout)
            resp.raise_for_status()
        except Exception:
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            text = anchor.get_text(" ", strip=True).lower()
            if "/html/" in href or text == "html" or "html (experimental)" in text:
                if href.startswith("http://") or href.startswith("https://"):
                    return href
                if href.startswith("/"):
                    return f"https://arxiv.org{href}"
        return ""

    def download_pdf(self, arxiv_id: str, pdf_url: str) -> str:
        output_path = self.pdf_cache_dir / f"{arxiv_id}.pdf"
        if output_path.exists() and output_path.stat().st_size > 0:
            return str(output_path)

        with self.session.get(pdf_url, stream=True, timeout=self.timeout) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return str(output_path)

    def download_html(self, arxiv_id: str, html_url: str) -> str:
        if not html_url:
            return ""

        output_path = self.html_cache_dir / f"{arxiv_id}.html"
        if output_path.exists() and output_path.stat().st_size > 0:
            return str(output_path)

        resp = self.session.get(html_url, timeout=self.timeout)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "html" not in content_type.lower() and "<html" not in resp.text[:500].lower():
            return ""

        output_path.write_text(resp.text, encoding="utf-8")
        return str(output_path)


_FETCHER: Optional[FullTextFetcher] = None


def get_fetcher(settings: dict) -> FullTextFetcher:
    global _FETCHER
    if _FETCHER is None:
        _FETCHER = FullTextFetcher(
            pdf_cache_dir=settings.get("pdf_cache_dir", "data/pdfs"),
            html_cache_dir=settings.get("html_cache_dir", "data/html"),
            timeout=int(settings.get("http_timeout", 30)),
        )
    return _FETCHER


def fetch_fulltext_assets(paper: dict, settings: dict) -> dict:
    fetcher = get_fetcher(settings)
    return fetcher.enrich_paper_assets(paper)

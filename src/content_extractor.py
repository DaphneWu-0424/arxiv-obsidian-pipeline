from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from pypdf import PdfReader


SECTION_NAMES = [
    "abstract",
    "introduction",
    "background",
    "related work",
    "method",
    "methods",
    "approach",
    "experiment",
    "experiments",
    "results",
    "discussion",
    "conclusion",
    "limitations",
]


def _clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _take_excerpt(text: str, limit: int) -> str:
    text = _clean_text(text)
    return text[:limit].strip()


def _extract_sections_by_heading(text: str) -> dict:
    lowered = text.lower()
    positions = []
    for section_name in SECTION_NAMES:
        pattern = re.compile(rf"(?:^|\n)\s*{re.escape(section_name)}\s*(?:\n|$)", re.IGNORECASE)
        match = pattern.search(lowered)
        if match:
            positions.append((match.start(), section_name))

    if not positions:
        return {}

    positions.sort()
    sections: dict[str, str] = {}
    for i, (start_pos, section_name) in enumerate(positions):
        end_pos = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        chunk = text[start_pos:end_pos].strip()
        sections[section_name] = _take_excerpt(chunk, 5000)
    return sections


def extract_from_html_file(html_path: str, max_chars: int = 120000) -> dict:
    raw_html = Path(html_path).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text("\n", strip=True)

    figure_captions = []
    for node in soup.find_all(["figcaption", "figure"]):
        caption = _clean_text(node.get_text(" ", strip=True))
        if caption:
            figure_captions.append(caption)

    references = []
    for node in soup.find_all(attrs={"class": re.compile(r"ref|reference", re.I)}):
        ref_text = _clean_text(node.get_text(" ", strip=True))
        if ref_text:
            references.append(ref_text)

    excerpt = _take_excerpt(text, max_chars)
    return {
        "source_type": "html",
        "raw_text": excerpt,
        "sections": _extract_sections_by_heading(excerpt),
        "figures": figure_captions[:20],
        "references": references[:30],
    }


def extract_from_pdf_file(pdf_path: str, max_pages: int = 20, max_chars: int = 120000) -> dict:
    reader = PdfReader(pdf_path)
    pages_text = []

    for page in reader.pages[:max_pages]:
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages_text.append(page_text)

    full_text = "\n\n".join(pages_text)
    excerpt = _take_excerpt(full_text, max_chars)
    return {
        "source_type": "pdf",
        "raw_text": excerpt,
        "sections": _extract_sections_by_heading(excerpt),
        "figures": [],
        "references": [],
    }


def extract_best_content(paper: dict, settings: dict) -> dict:
    max_chars = int(settings.get("max_fulltext_chars", 120000))
    max_pages = int(settings.get("max_pdf_pages_for_extract", 20))
    use_html_first = bool(settings.get("use_html_first", True))

    html_path = paper.get("local_html_path") or ""
    pdf_path = paper.get("local_pdf_path") or ""

    if use_html_first and html_path and Path(html_path).exists():
        try:
            return extract_from_html_file(html_path, max_chars=max_chars)
        except Exception:
            pass

    if pdf_path and Path(pdf_path).exists():
        try:
            return extract_from_pdf_file(pdf_path, max_pages=max_pages, max_chars=max_chars)
        except Exception:
            pass

    if html_path and Path(html_path).exists():
        try:
            return extract_from_html_file(html_path, max_chars=max_chars)
        except Exception:
            pass

    abstract = (paper.get("abstract") or paper.get("summary") or "").strip()
    return {
        "source_type": "abstract",
        "raw_text": abstract,
        "sections": {"abstract": abstract} if abstract else {},
        "figures": [],
        "references": [],
    }

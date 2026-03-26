from __future__ import annotations

import traceback

from content_extractor import extract_best_content
from fulltext_fetcher import fetch_fulltext_assets
from summarizer import enrich_from_fulltext


EMPTY_ENRICHMENT = {
    "tldr": "",
    "problem": "",
    "core_idea": "",
    "method": "",
    "experiments": "",
    "results": "",
    "limitations": "",
    "reading_advice": "",
    "relevance": "",
    "tags": [],
}


def enrich_paper_detail(paper: dict, settings: dict) -> tuple[dict, dict]:
    paper_with_assets = fetch_fulltext_assets(paper, settings)
    content = extract_best_content(paper_with_assets, settings)

    if not settings.get("enable_paper_enrichment", True):
        return paper_with_assets, EMPTY_ENRICHMENT.copy()

    try:
        enrichment = enrich_from_fulltext(paper_with_assets, content)
    except Exception:
        traceback.print_exc()
        enrichment = EMPTY_ENRICHMENT.copy()

    enrichment["source_type"] = content.get("source_type", "unknown")
    enrichment["raw_text_chars"] = len(content.get("raw_text", "") or "")
    return paper_with_assets, enrichment

from __future__ import annotations

from typing import List, Dict, Any
import requests
import feedparser


ARXIV_API_URL = "http://export.arxiv.org/api/query"

def fetch_batch_metadata(arxiv_ids: List[str]) -> List[Dict[str, Any]]:
    if not arxiv_ids:
        return []

    id_list = ",".join(arxiv_ids)
    params = {
        "id_list": id_list,
        "max_results": len(arxiv_ids),
    }

    resp = requests.get(ARXIV_API_URL, params=params, timeout=30)
    resp.raise_for_status() # 检查HTTP状态码

    feed = feedparser.parse(resp.text)
    papers = []

    for entry in feed.entries:
        arxiv_id = entry.id.split("/abs/")[-1]
        authors = [author.name for author in entry.authors] if hasattr(entry, "authors") else []
        categories = [tag["term"] for tag in entry.tags] if hasattr(entry, "tags") else []

        papers.append({
            "arxiv_id": arxiv_id,
            "title": entry.title.replace("\n", " ").strip(),
            "authors": authors,
            "summary": entry.summary.replace("\n", " ").strip(),
            "categories": categories,
            "published": entry.published,
            "updated": entry.updated,
            "abs_url": entry.id,
            "pdf_url": entry.id.replace("/abs/", "/pdf/") + ".pdf",
        })

    return papers

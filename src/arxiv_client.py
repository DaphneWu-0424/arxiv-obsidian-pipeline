from __future__ import annotations

from typing import List, Dict, Any
import requests
import feedparser
import re


ARXIV_API_URL = "http://export.arxiv.org/api/query"

def split_arxiv_id_version(arxiv_id: str) -> tuple[str, str | None]:
    m = re.match(r"^(.*?)(v\d+)?$", arxiv_id)
    if not m:
        return arxiv_id, None
    return m.group(1), m.group(2)


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
        full_id = entry.id.split("/abs/")[-1]
        base_id, version = split_arxiv_id_version(full_id)

        authors = [author.name for author in entry.authors] if hasattr(entry, "authors") else []
        categories = [tag["term"] for tag in entry.tags] if hasattr(entry, "tags") else []

        papers.append({
            "arxiv_id": base_id, # 不带版本，后面做文件名/去重用
            "arxiv_version": version,
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

from __future__ import annotations

import re
import time
import threading
import xml.etree.ElementTree as ET
from typing import Iterable

import requests


ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


class ArxivClient:
    """
    目标：
    1. 优先用 id_list 批量取元数据
    2. 避免对每个 miss 再单独打一条 search_query=id:...
    3. 按 arXiv API 的老接口节奏做限速，降低 429 风险
    """

    _rate_lock = threading.Lock()
    _last_request_ts = 0.0

    def __init__(
        self,
        timeout: int = 20,
        min_interval_seconds: float = 3.2,
        batch_size: int = 100,
        max_retries: int = 3,
        backoff_seconds: float = 6.0,
    ):
        self.timeout = timeout
        self.min_interval_seconds = min_interval_seconds
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.session = requests.Session()

    # ---------- public API ----------

    def fetch_metadata_by_id(self, arxiv_id: str) -> dict:
        """
        单篇接口保留，但内部仍然走 id_list，避免 search_query=id:...
        """
        papers = self.fetch_batch_metadata([arxiv_id])
        return papers[0] if papers else {}

    def fetch_batch_metadata(self, arxiv_ids: Iterable[str]) -> list[dict]:
        requested_ids = [self.normalize_arxiv_id(x) for x in arxiv_ids if x and str(x).strip()]
        if not requested_ids:
            return []

        # 去重但保序
        deduped_ids = list(dict.fromkeys(requested_ids))

        all_papers: list[dict] = []
        for chunk in self._chunked(deduped_ids, self.batch_size):
            papers = self._fetch_batch_chunk(chunk)
            all_papers.extend(papers)

        # 用“去版本号后的 id”做匹配，避免 2603.20235 和 2603.20235v1 对不上
        by_base_id: dict[str, dict] = {}
        for paper in all_papers:
            paper_id = paper.get("arxiv_id", "")
            base_id = self.base_arxiv_id(paper_id)
            if base_id and base_id not in by_base_id:
                by_base_id[base_id] = paper

        ordered_results: list[dict] = []
        missing_ids: list[str] = []

        for requested_id in requested_ids:
            base_id = self.base_arxiv_id(requested_id)
            paper = by_base_id.get(base_id)
            if paper:
                ordered_results.append(paper)
            else:
                missing_ids.append(requested_id)

        if missing_ids:
            preview = ", ".join(missing_ids[:10])
            suffix = " ..." if len(missing_ids) > 10 else ""
            print(
                f"[arxiv_client] 批量请求后有 {len(missing_ids)} 个 ID 未匹配到，"
                f"已跳过，不做逐个 fallback：{preview}{suffix}"
            )

        return ordered_results

    # ---------- core request ----------

    def _fetch_batch_chunk(self, arxiv_ids: list[str]) -> list[dict]:
        params = {
            "id_list": ",".join(arxiv_ids),
            "start": 0,
            "max_results": len(arxiv_ids),
        }

        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                self._respect_rate_limit()
                resp = self.session.get(ARXIV_API_URL, params=params, timeout=self.timeout)
                resp.raise_for_status()
                return self._parse_feed(resp.text)

            except requests.HTTPError as e:
                last_error = e
                status = getattr(e.response, "status_code", None)

                # 429 或 5xx：退避重试
                if status == 429 or (status is not None and 500 <= status < 600):
                    sleep_s = self.backoff_seconds * attempt
                    print(
                        f"[arxiv_client] arXiv API 请求失败(status={status})，"
                        f"第 {attempt}/{self.max_retries} 次重试，等待 {sleep_s:.1f}s"
                    )
                    time.sleep(sleep_s)
                    continue

                raise

            except requests.RequestException as e:
                last_error = e
                sleep_s = self.backoff_seconds * attempt
                print(
                    f"[arxiv_client] arXiv API 网络异常，"
                    f"第 {attempt}/{self.max_retries} 次重试，等待 {sleep_s:.1f}s：{e}"
                )
                time.sleep(sleep_s)
                continue

        raise last_error

    def _respect_rate_limit(self) -> None:
        with self._rate_lock:
            now = time.monotonic()
            elapsed = now - self._last_request_ts
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)
            self._last_request_ts = time.monotonic()

    # ---------- parsing ----------

    def _parse_feed(self, xml_text: str) -> list[dict]:
        root = ET.fromstring(xml_text)
        entries = root.findall("atom:entry", ATOM_NS)

        papers: list[dict] = []
        for entry in entries:
            paper = self._parse_entry(entry)
            if paper:
                papers.append(paper)
        return papers

    def _parse_entry(self, entry: ET.Element) -> dict:
        entry_id_url = (entry.findtext("atom:id", default="", namespaces=ATOM_NS) or "").strip()
        raw_arxiv_id = self.extract_arxiv_id_from_entry_url(entry_id_url)
        base_id = self.base_arxiv_id(raw_arxiv_id)

        title = (entry.findtext("atom:title", default="", namespaces=ATOM_NS) or "").strip()
        abstract = (entry.findtext("atom:summary", default="", namespaces=ATOM_NS) or "").strip()

        authors = [
            (a.findtext("atom:name", default="", namespaces=ATOM_NS) or "").strip()
            for a in entry.findall("atom:author", ATOM_NS)
        ]
        authors = [a for a in authors if a]

        categories = [
            c.attrib.get("term", "").strip()
            for c in entry.findall("atom:category", ATOM_NS)
            if c.attrib.get("term", "").strip()
        ]

        abs_url = self.build_abs_url(base_id) if base_id else entry_id_url
        pdf_url = self.build_pdf_url(base_id) if base_id else ""

        return {
            "arxiv_id": base_id,                  # 主流程统一用无版本号 ID
            "arxiv_id_raw": raw_arxiv_id,        # 保留原始 entry id
            "title": title,
            "abstract": abstract,
            "summary": abstract,                 # 兼容你现有 summarizer
            "authors": authors,
            "categories": categories,
            "published": entry.findtext("atom:published", default="", namespaces=ATOM_NS),
            "updated": entry.findtext("atom:updated", default="", namespaces=ATOM_NS),
            "abs_url": abs_url,
            "pdf_url": pdf_url,
        }

    # ---------- helpers ----------

    @staticmethod
    def normalize_arxiv_id(arxiv_id: str) -> str:
        s = str(arxiv_id).strip()
        s = re.sub(r"^arxiv:", "", s, flags=re.IGNORECASE)
        return s

    @staticmethod
    def base_arxiv_id(arxiv_id: str) -> str:
        s = ArxivClient.normalize_arxiv_id(arxiv_id)
        return re.sub(r"v\d+$", "", s)

    @staticmethod
    def extract_arxiv_id_from_entry_url(url: str) -> str:
        """
        例如：
        https://arxiv.org/abs/2603.20235v1 -> 2603.20235v1
        http://arxiv.org/abs/cs/0012017v2 -> cs/0012017v2
        """
        if not url:
            return ""
        m = re.search(r"/abs/([^/?#]+(?:/[^/?#]+)?)", url)
        return m.group(1) if m else url.strip()

    @staticmethod
    def build_abs_url(arxiv_id: str) -> str:
        return f"https://arxiv.org/abs/{arxiv_id}"

    @staticmethod
    def build_pdf_url(arxiv_id: str) -> str:
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    @staticmethod
    def _chunked(items: list[str], size: int) -> list[list[str]]:
        return [items[i:i + size] for i in range(0, len(items), size)]


def fetch_batch_metadata(arxiv_ids: Iterable[str]) -> list[dict]:
    client = ArxivClient()
    return client.fetch_batch_metadata(arxiv_ids)
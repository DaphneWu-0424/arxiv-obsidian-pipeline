from __future__ import annotations

import json
import os
from typing import Any, Dict

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

ABSTRACT_SYSTEM_PROMPT = """
You are a careful academic reading assistant.
Summarize the paper in Chinese.
Only use information explicitly present in the provided metadata and abstract.
Do not invent experiments, claims, or conclusions that are not supported.
Return valid JSON only.
"""

ABSTRACT_USER_PROMPT_TEMPLATE = """
请根据下面这篇 arXiv 论文的信息，输出中文总结。

要求：
1. 只能根据给定信息总结，不要编造。
2. 输出必须是 JSON。
3. 字段必须完整，不能省略。
4. main_content 和 key_points 各给 3 条。
5. tags 给 3 到 6 个英文或中文短标签。

JSON 格式：
{{
  "one_sentence_summary": "...",
  "main_content": ["...", "...", "..."],
  "key_points": ["...", "...", "..."],
  "method": "...",
  "findings": "...",
  "limitations": "...",
  "tags": ["...", "...", "..."]
}}

论文信息：
Title: {title}
Authors: {authors}
Categories: {categories}
Abstract: {abstract}
"""

FULLTEXT_SYSTEM_PROMPT = """
You are a careful academic reading assistant.
Write Chinese research notes based only on the provided metadata and extracted paper content.
Do not invent claims not grounded in the provided text.
Return valid JSON only.
"""

FULLTEXT_USER_PROMPT_TEMPLATE = """
请基于下面的论文元数据和论文正文摘录，输出一个更丰富的中文详情摘要。

要求：
1. 只能根据给定信息总结，不要编造。
2. 输出必须是 JSON。
3. 保持清晰、具体、适合写入 Obsidian 详情页。
4. 如果正文信息不足，就明确写“正文摘录不足以判断”。
5. tags 给 4 到 8 个短标签。

JSON 格式：
{{
  "tldr": "...",
  "problem": "...",
  "core_idea": "...",
  "method": "...",
  "experiments": "...",
  "results": "...",
  "limitations": "...",
  "reading_advice": "...",
  "relevance": "...",
  "tags": ["...", "...", "..."]
}}

论文信息：
Title: {title}
Authors: {authors}
Categories: {categories}
Published: {published}
Updated: {updated}
Abstract:
{abstract}

正文来源: {source_type}
正文摘录:
{content_excerpt}
"""


class OpenAIJSONClient:
    def __init__(self):
        api_key = os.getenv("AI_API_KEY", "").strip()
        base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        model = os.getenv("AI_MODEL", "gpt-4o-mini")
        timeout = float(os.getenv("AI_TIMEOUT", "90"))

        if not api_key:
            raise ValueError("AI_API_KEY 未配置")

        self.model = model
        self.timeout = timeout
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def complete_json(self, *, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> dict:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
            timeout=self.timeout,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)


_CLIENT: OpenAIJSONClient | None = None


def get_llm_client() -> OpenAIJSONClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = OpenAIJSONClient()
    return _CLIENT


def _normalize_summary_result(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "one_sentence_summary": str(data.get("one_sentence_summary", "")).strip(),
        "main_content": [str(x).strip() for x in list(data.get("main_content", []))[:3] if str(x).strip()],
        "key_points": [str(x).strip() for x in list(data.get("key_points", []))[:3] if str(x).strip()],
        "method": str(data.get("method", "")).strip(),
        "findings": str(data.get("findings", "")).strip(),
        "limitations": str(data.get("limitations", "")).strip(),
        "tags": [str(x).strip() for x in list(data.get("tags", []))[:6] if str(x).strip()],
    }


def _normalize_enrichment_result(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tldr": str(data.get("tldr", "")).strip(),
        "problem": str(data.get("problem", "")).strip(),
        "core_idea": str(data.get("core_idea", "")).strip(),
        "method": str(data.get("method", "")).strip(),
        "experiments": str(data.get("experiments", "")).strip(),
        "results": str(data.get("results", "")).strip(),
        "limitations": str(data.get("limitations", "")).strip(),
        "reading_advice": str(data.get("reading_advice", "")).strip(),
        "relevance": str(data.get("relevance", "")).strip(),
        "tags": [str(x).strip() for x in list(data.get("tags", []))[:8] if str(x).strip()],
    }


def summarize_from_abstract(metadata: Dict[str, Any]) -> Dict[str, Any]:
    client = get_llm_client()
    user_prompt = ABSTRACT_USER_PROMPT_TEMPLATE.format(
        title=metadata.get("title", ""),
        authors=", ".join(metadata.get("authors", [])),
        categories=", ".join(metadata.get("categories", [])),
        abstract=metadata.get("abstract") or metadata.get("summary") or "",
    )
    parsed = client.complete_json(
        system_prompt=ABSTRACT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.2,
    )
    return _normalize_summary_result(parsed)


def enrich_from_fulltext(paper: Dict[str, Any], content: Dict[str, Any]) -> Dict[str, Any]:
    client = get_llm_client()
    user_prompt = FULLTEXT_USER_PROMPT_TEMPLATE.format(
        title=paper.get("title", ""),
        authors=", ".join(paper.get("authors", [])),
        categories=", ".join(paper.get("categories", [])),
        published=paper.get("published", ""),
        updated=paper.get("updated", ""),
        abstract=paper.get("abstract") or paper.get("summary") or "",
        source_type=content.get("source_type", "unknown"),
        content_excerpt=(content.get("raw_text", "") or "")[:30000],
    )
    parsed = client.complete_json(
        system_prompt=FULLTEXT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.2,
    )
    return _normalize_enrichment_result(parsed)

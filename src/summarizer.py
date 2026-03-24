from __future__ import annotations

import json
import os
from typing import Dict, Any, List

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """
You are a careful academic reading assistant.
Summarize the paper in Chinese.
Only use information explicitly present in the provided metadata and abstract.
Do not invent experiments, claims, or conclusions that are not supported.
Return valid JSON only.
"""

USER_PROMPT_TEMPLATE = """
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
Abstract: {summary}
"""

def _normalize_summary_result(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "one_sentence_summary": str(data.get("one_sentence_summary", "")).strip(),
        "main_content": list(data.get("main_content", []))[:3],
        "key_points": list(data.get("key_points", []))[:3],
        "method": str(data.get("method", "")).strip(),
        "findings": str(data.get("findings", "")).strip(),
        "limitations": str(data.get("limitations", "")).strip(),
        "tags": list(data.get("tags", []))[:6],
    }

def summarize_from_abstract(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    使用 OpenAI SDK 调用 LLM 进行总结。
    """
    api_key = os.getenv("AI_API_KEY", "").strip()
    base_url = os.getenv("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("AI_MODEL", "gpt-4o-mini")

    if not api_key:
        raise ValueError("AI_API_KEY 未配置")
    
    print(f"AI_BASE_URL={base_url}")
    print(f"AI_MODEL={model}")

    # 初始化 OpenAI 客户端
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,   # 支持自定义 base URL（如第三方代理或本地模型）
    )

    user_prompt = USER_PROMPT_TEMPLATE.format(
        title=metadata["title"],
        authors=", ".join(metadata.get("authors", [])),
        categories=", ".join(metadata.get("categories", [])),
        summary=metadata["summary"],
    )

    # 调用 chat completion
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},  # 确保返回合法 JSON
        timeout=60,
    )

    # 提取并解析响应内容
    content = response.choices[0].message.content
    parsed = json.loads(content)

    return _normalize_summary_result(parsed)
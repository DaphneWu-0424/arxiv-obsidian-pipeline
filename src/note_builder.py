from __future__ import annotations


def _join_lines(items: list[str]) -> str:
    return "\n".join(x for x in items if x).strip()


def _render_list(items: list[str]) -> str:
    if not items:
        return "- 暂无"
    return "\n".join(f"- {item}" for item in items if item)


def _render_links(paper: dict) -> str:
    lines = []
    if paper.get("abs_url"):
        lines.append(f"- Abstract: {paper['abs_url']}")
    if paper.get("pdf_url"):
        lines.append(f"- PDF: {paper['pdf_url']}")
    if paper.get("html_url"):
        lines.append(f"- HTML: {paper['html_url']}")
    if paper.get("local_pdf_path"):
        lines.append(f"- Local PDF: `{paper['local_pdf_path']}`")
    if paper.get("local_html_path"):
        lines.append(f"- Local HTML: `{paper['local_html_path']}`")
    return _join_lines(lines)


def build_paper_note(paper: dict, summary: dict, date_folder: str, enrichment: dict | None = None) -> str:
    enrichment = enrichment or {}

    title = paper.get("title", "")
    authors = ", ".join(paper.get("authors", []))
    categories = ", ".join(paper.get("categories", []))
    summary_tags = summary.get("tags", []) or []
    detail_tags = enrichment.get("tags", []) or []
    merged_tags = []
    for tag in summary_tags + detail_tags:
        if tag and tag not in merged_tags:
            merged_tags.append(tag)

    frontmatter = [
        "---",
        f'title: "{title.replace(chr(34), chr(39))}"',
        f'arxiv_id: "{paper.get("arxiv_id", "")}"',
        f'date_folder: "{date_folder}"',
        "tags:",
    ]
    if merged_tags:
        frontmatter.extend([f"  - {tag}" for tag in merged_tags])
    else:
        frontmatter.append("  - arxiv")
    frontmatter.append("---")

    body = [
        *frontmatter,
        "",
        f"# {title}",
        "",
        "## 基本信息",
        f"- Authors: {authors}",
        f"- Categories: {categories}",
        f"- Published: {paper.get('published', '')}",
        f"- Updated: {paper.get('updated', '')}",
        "",
        "## 链接与本地文件",
        _render_links(paper) or "- 暂无",
        "",
        "## 一句话总结",
        summary.get("one_sentence_summary", ""),
        "",
        "## 核心内容",
        _render_list(summary.get("main_content", [])),
        "",
        "## 关键点",
        _render_list(summary.get("key_points", [])),
        "",
        "## 方法",
        summary.get("method", ""),
        "",
        "## 发现",
        summary.get("findings", ""),
        "",
        "## 局限性",
        summary.get("limitations", ""),
    ]

    if enrichment:
        body.extend([
            "",
            "## 全文增强摘要",
            enrichment.get("tldr", ""),
            "",
            "## 研究问题",
            enrichment.get("problem", ""),
            "",
            "## 核心思路",
            enrichment.get("core_idea", ""),
            "",
            "## 方法细节",
            enrichment.get("method", ""),
            "",
            "## 实验与结果",
            _join_lines([
                enrichment.get("experiments", ""),
                enrichment.get("results", ""),
            ]),
            "",
            "## 阅读建议",
            enrichment.get("reading_advice", ""),
            "",
            "## 与我当前研究的相关性",
            enrichment.get("relevance", ""),
            "",
            "## 全文提取信息",
            f"- Source Type: {enrichment.get('source_type', '')}",
            f"- Extracted Chars: {enrichment.get('raw_text_chars', 0)}",
        ])

    body.extend([
        "",
        "## Abstract",
        paper.get("abstract", "") or paper.get("summary", ""),
        "",
        "## Personal Notes",
        "- [ ]",
        "",
    ])

    return "\n".join(body).strip() + "\n"


def build_daily_index(date_folder: str, papers: list[dict]) -> str:
    """
    这里保留一个“整页生成”版本，
    但主流程之后不再拿它去覆写 index.md。
    """
    lines = [
        f"# arXiv Daily Index - {date_folder}",
        "",
    ]

    for paper in papers:
        note_name = paper.get("note_name", "").strip()
        one_sentence_summary = paper.get("one_sentence_summary", "").strip()
        one_sentence_summary = " ".join(one_sentence_summary.split())

        if not note_name:
            continue

        if one_sentence_summary:
            lines.append(f"- [ ] [[{note_name}]] — {one_sentence_summary}")
        else:
            lines.append(f"- [ ] [[{note_name}]]")

    lines.append("")
    return "\n".join(lines)
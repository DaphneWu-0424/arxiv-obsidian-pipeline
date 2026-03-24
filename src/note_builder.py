from __future__ import annotations

from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from typing import Dict, Any, List

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=False, # 因为生成的是 Markdown 而非 HTML，无需自动转义特殊字符
    trim_blocks=True,
    lstrip_blocks=True,
)

def build_paper_note(paper: Dict[str, Any], summary: Dict[str, Any], date_folder: str) -> str:
    template = env.get_template("paper_note.md.j2")
    context = {
        **paper, # 字典解包合并到一个上下文里
        **summary,
        "date_folder": date_folder,
    }
    return template.render(**context)


def build_daily_index(date_folder: str, papers: List[Dict[str, Any]]) -> str:
    template = env.get_template("daily_index.md.j2")
    return template.render(
        date_folder=date_folder,
        paper_count=len(papers),
        papers=papers,
    )
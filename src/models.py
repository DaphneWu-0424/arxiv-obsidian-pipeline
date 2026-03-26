from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict


@dataclass
class PaperRecord:
    arxiv_id: str
    title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    categories: List[str] = field(default_factory=list)

    abs_url: str = ""
    pdf_url: str = ""
    html_url: Optional[str] = None

    published: Optional[str] = None
    updated: Optional[str] = None

    local_pdf_path: Optional[Path] = None
    local_html_path: Optional[Path] = None


@dataclass
class FullTextContent:
    source_type: str  # "html" / "pdf" / "abstract"
    raw_text: str
    sections: Dict[str, str] = field(default_factory=dict)
    figures: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)


@dataclass
class EnrichedPaperNote:
    tldr: str = ""
    why_it_matters: str = ""
    core_idea: str = ""
    method: str = ""
    experiments: str = ""
    limitations: str = ""
    relevance: str = ""
    reading_suggestion: str = ""
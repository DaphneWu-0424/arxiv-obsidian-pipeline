from __future__ import annotations

import re
from pathlib import Path


def sanitize_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r'[<>:"/\\|?*]', " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:max_len].strip()


def ensure_daily_folder(vault_path: str, papers_root: str, date_folder: str) -> Path:
    folder = Path(vault_path) / papers_root / date_folder
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def make_note_filename(arxiv_id: str, title: str) -> str:
    safe_title = sanitize_filename(title)
    return f"{arxiv_id} - {safe_title}.md"


def write_text_file(file_path: Path, content: str) -> None:
    file_path.write_text(content, encoding="utf-8")


def write_paper_note(vault_path: str, papers_root: str, date_folder: str, arxiv_id: str, title: str, content: str) -> Path:
    folder = ensure_daily_folder(vault_path, papers_root, date_folder)
    note_name = make_note_filename(arxiv_id, title)
    file_path = folder / note_name
    write_text_file(file_path, content)
    return file_path


def write_daily_index(vault_path: str, papers_root: str, date_folder: str, content: str) -> Path:
    folder = ensure_daily_folder(vault_path, papers_root, date_folder)
    file_path = folder / "index.md"
    write_text_file(file_path, content)
    return file_path
from __future__ import annotations

import re
from pathlib import Path
import yaml


CHECKED_LINE_RE = re.compile(r"^- \[x\] \[\[(.*?)\]\].*$", re.MULTILINE)
LOCAL_PDF_RE = re.compile(r"^- Local PDF:\s+`([^`]+)`\s*$", re.MULTILINE)
LOCAL_HTML_RE = re.compile(r"^- Local HTML:\s+`([^`]+)`\s*$", re.MULTILINE)
ARXIV_ID_RE = re.compile(r'^arxiv_id:\s*"?(.*?)"?\s*$', re.MULTILINE)


def load_settings(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_checked_notes(index_text: str) -> list[str]:
    return CHECKED_LINE_RE.findall(index_text)


def parse_local_asset_path(note_text: str, kind: str) -> Path | None:
    if kind == "pdf":
        pattern = LOCAL_PDF_RE
    elif kind == "html":
        pattern = LOCAL_HTML_RE
    else:
        return None

    m = pattern.search(note_text)
    if not m:
        return None

    raw_path = m.group(1).strip()
    if not raw_path:
        return None

    return Path(raw_path)


def parse_arxiv_id_from_note(note_text: str, note_name: str) -> str | None:
    m = ARXIV_ID_RE.search(note_text)
    if m:
        arxiv_id = m.group(1).strip().strip('"').strip("'")
        if arxiv_id:
            return arxiv_id

    m2 = re.match(r"^([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)\s+-\s+", note_name)
    if m2:
        return m2.group(1)

    return None


def resolve_asset_path(asset_path: Path, project_root: Path) -> Path:
    if asset_path.is_absolute():
        return asset_path
    return (project_root / asset_path).resolve()


def fallback_asset_path_from_settings(
    settings: dict,
    project_root: Path,
    arxiv_id: str | None,
    kind: str,
) -> Path | None:
    if not arxiv_id:
        return None

    if kind == "pdf":
        cache_dir = settings.get("pdf_cache_dir")
        suffix = ".pdf"
    elif kind == "html":
        cache_dir = settings.get("html_cache_dir")
        suffix = ".html"
    else:
        return None

    if not cache_dir:
        return None

    return (project_root / cache_dir / f"{arxiv_id}{suffix}").resolve()


def delete_one_asset(note_text: str, note_name: str, settings: dict, project_root: Path, kind: str) -> None:
    asset_label = kind.upper()

    # 优先从详情页里的 Local PDF / Local HTML 行读取
    asset_path = parse_local_asset_path(note_text, kind)
    if asset_path is not None:
        resolved = resolve_asset_path(asset_path, project_root)
        if resolved.exists():
            resolved.unlink()
            print(f"已删除本地 {asset_label}: {resolved}")
        else:
            print(f"本地 {asset_label} 路径存在于详情页中，但文件不存在，跳过: {resolved}")
        return

    # 兜底：根据 arxiv_id + cache_dir 推断
    arxiv_id = parse_arxiv_id_from_note(note_text, note_name)
    guessed_path = fallback_asset_path_from_settings(settings, project_root, arxiv_id, kind)
    if guessed_path and guessed_path.exists():
        guessed_path.unlink()
        print(f"已按 arXiv ID 推断并删除本地 {asset_label}: {guessed_path}")
    else:
        if guessed_path:
            print(f"未找到可删除的本地 {asset_label}（按设置推断路径不存在）: {guessed_path}")
        else:
            print(f"未找到 Local {asset_label} 信息，也无法从设置推断路径: {note_name}.md")


def delete_assets_for_note(note_path: Path, settings: dict, project_root: Path) -> None:
    if not note_path.exists():
        print(f"详情页不存在，无法解析本地资源路径: {note_path}")
        return

    note_text = note_path.read_text(encoding="utf-8", errors="ignore")
    note_name = note_path.stem

    delete_one_asset(note_text, note_name, settings, project_root, "pdf")
    delete_one_asset(note_text, note_name, settings, project_root, "html")


def cleanup_one_index(index_path: Path, settings: dict, project_root: Path) -> None:
    folder = index_path.parent
    text = index_path.read_text(encoding="utf-8")

    checked_notes = find_checked_notes(text)
    if not checked_notes:
        print(f"没有勾选删除项: {index_path}")
        return

    print(f"在 {index_path} 中发现 {len(checked_notes)} 个待删除项")

    for note_name in checked_notes:
        note_path = folder / f"{note_name}.md"

        # 先删本地 PDF / HTML，再删详情页
        delete_assets_for_note(note_path, settings, project_root)

        if note_path.exists():
            note_path.unlink()
            print(f"已删除详情页: {note_path}")
        else:
            print(f"详情页不存在，跳过: {note_path}")

    new_lines = []
    for line in text.splitlines():
        if CHECKED_LINE_RE.match(line):
            continue
        new_lines.append(line)

    new_text = "\n".join(new_lines)
    new_text = re.sub(r"\n{3,}", "\n\n", new_text).strip() + "\n"
    index_path.write_text(new_text, encoding="utf-8")
    print(f"已更新 index: {index_path}")


def main() -> None:
    settings = load_settings()
    project_root = Path(__file__).resolve().parent.parent

    vault_path = Path(settings["vault_path"])
    papers_root = settings["papers_root"]

    papers_dir = vault_path / papers_root
    if not papers_dir.exists():
        print(f"Papers 目录不存在: {papers_dir}")
        return

    index_files = list(papers_dir.glob("*/index.md"))
    if not index_files:
        print("没有找到任何 index.md")
        return

    for index_path in sorted(index_files):
        cleanup_one_index(index_path, settings, project_root)


if __name__ == "__main__":
    main()
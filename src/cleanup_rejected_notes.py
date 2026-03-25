from __future__ import annotations

import re
from pathlib import Path
import yaml


def load_settings(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_checked_notes(index_text: str) -> list[str]:
    """
    匹配这种格式：
    - [x] [[2503.12345 - Paper Title]] — ...
    返回 note_name 列表（不带 .md）
    """
    pattern = re.compile(r"^- \[x\] \[\[(.*?)\]\].*$", re.MULTILINE)
    return pattern.findall(index_text)


def cleanup_one_index(index_path: Path) -> None:
    folder = index_path.parent
    text = index_path.read_text(encoding="utf-8")

    checked_notes = find_checked_notes(text)
    if not checked_notes:
        print(f"没有勾选删除项: {index_path}")
        return

    print(f"在 {index_path} 中发现 {len(checked_notes)} 个待删除项")

    for note_name in checked_notes:
        note_path = folder / f"{note_name}.md"
        if note_path.exists():
            note_path.unlink()
            print(f"已删除详情页: {note_path}")
        else:
            print(f"详情页不存在，跳过: {note_path}")

    # 从 index.md 删除所有已勾选行
    new_lines = []
    for line in text.splitlines():
        if re.match(r"^- \[x\] \[\[(.*?)\]\].*$", line):
            continue
        new_lines.append(line)

    new_text = "\n".join(new_lines).strip() + "\n"
    index_path.write_text(new_text, encoding="utf-8")
    print(f"已更新 index: {index_path}")


def main() -> None:
    settings = load_settings()
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
        cleanup_one_index(index_path)


if __name__ == "__main__":
    main()
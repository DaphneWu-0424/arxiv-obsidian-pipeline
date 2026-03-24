from __future__ import annotations

import os
import re
import traceback
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from gmail_client import build_gmail_session, list_recent_arxiv_messages, get_message_text
from email_parser import extract_arxiv_ids_from_content
from arxiv_client import fetch_batch_metadata
from summarizer import summarize_from_abstract
from note_builder import build_paper_note, build_daily_index
from obsidian_writer import write_paper_note, write_daily_index
from db import (
    init_db,
    get_conn,
    mark_email_processed,
    mark_paper_processed,
)

load_dotenv()


def load_settings(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_paper_successful(db_path: str, arxiv_id: str, date_folder: str) -> bool:
    """
    只把 status=success 的论文视为“已完成”。
    failed 记录下次仍然允许重试。
    """
    with get_conn(db_path) as conn:
        row = conn.execute(
            """
            SELECT status
            FROM processed_papers
            WHERE arxiv_id = ? AND date_folder = ?
            LIMIT 1
            """,
            (arxiv_id, date_folder),
        ).fetchone()

        return row is not None and row["status"] == "success"


def extract_one_sentence_summary_from_note(note_text: str) -> str:
    """
    从已有 note 中提取 “## 一句话总结” 段落，用于重建 index.md。
    """
    match = re.search(
        r"## 一句话总结\s*(.*?)\s*(?:\n## |\Z)",
        note_text,
        flags=re.S,
    )
    if not match:
        return ""

    summary = match.group(1).strip()
    summary = re.sub(r"\s+", " ", summary)
    return summary


def load_index_items_from_vault(vault_path: str, papers_root: str, date_folder: str) -> list[dict]:
    """
    从当天文件夹里扫描所有论文 note，重建 index 所需的数据。
    这样即使一封邮件分多次跑，index.md 也会包含当天已生成的全部 note。
    """
    folder = Path(vault_path) / papers_root / date_folder
    if not folder.exists():
        return []

    items = []
    for note_path in sorted(folder.glob("*.md")):
        if note_path.name.lower() == "index.md":
            continue

        try:
            text = note_path.read_text(encoding="utf-8")
        except Exception:
            text = ""

        items.append({
            "note_name": note_path.stem,
            "one_sentence_summary": extract_one_sentence_summary_from_note(text),
            "note_path": str(note_path),
        })

    return items


def main() -> None:
    settings = load_settings()

    credentials_path = os.getenv("GMAIL_CREDENTIALS_PATH", "config/credentials.json")
    token_path = os.getenv("GMAIL_TOKEN_PATH", "config/token.json")

    vault_path = settings["vault_path"]
    papers_root = settings["papers_root"]
    gmail_label = settings["gmail_label"]
    db_path = settings["database_path"]
    max_papers_per_run = int(settings.get("max_papers_per_run", 20))

    init_db(db_path)

    session = build_gmail_session(credentials_path, token_path)
    messages = list_recent_arxiv_messages(session, gmail_label, max_results=10)

    print(f"扫描到 {len(messages)} 封邮件")

    touched_dates: set[str] = set()
    processed_count = 0

    for m in messages:
        gmail_message_id = m["id"]
        subject = ""

        try:
            detail = get_message_text(session, gmail_message_id)
            subject = detail["subject"]
            body = detail["body"]
            body_text = detail.get("body_text", "")
            body_html = detail.get("body_html", "")
            print("body_text length:", len(body_text))
            print("body_html length:", len(body_html))

            email_date_folder = detail["date_folder"]
            if not email_date_folder:
                email_date_folder = datetime.now().strftime("%Y-%m-%d")

            touched_dates.add(email_date_folder)

            print("=" * 60)
            print("邮件主题:", subject)
            print("邮件接收时间:", detail["received_at"])
            print("目录日期:", email_date_folder)

            arxiv_ids = set()
            arxiv_ids.update(extract_arxiv_ids_from_content(body))
            arxiv_ids.update(extract_arxiv_ids_from_content(body_text))
            arxiv_ids.update(extract_arxiv_ids_from_content(body_html))
            arxiv_ids = sorted(arxiv_ids)
            print(f"提取到 {len(arxiv_ids)} 个 arXiv ID")

            if not arxiv_ids:
                mark_email_processed(
                    db_path=db_path,
                    gmail_message_id=gmail_message_id,
                    subject=subject,
                    processed_at=now_iso(),
                    status="failed",
                    error_message="No arXiv IDs extracted from email body",
                )
                print(f"邮件没有提取到论文，标记失败待后续重试: {gmail_message_id}")
                continue

            all_pending_ids = [
                aid for aid in arxiv_ids
                if not is_paper_successful(db_path, aid, email_date_folder)
            ]

            print(f"该邮件剩余未处理论文数: {len(all_pending_ids)}")

            if not all_pending_ids:
                mark_email_processed(
                    db_path=db_path,
                    gmail_message_id=gmail_message_id,
                    subject=subject,
                    processed_at=now_iso(),
                    status="complete",
                )
                print(f"邮件已全部处理完成: {gmail_message_id}")
                continue

            batch_ids = all_pending_ids[:max_papers_per_run]
            print(f"本次实际处理论文数: {len(batch_ids)}")

            papers = fetch_batch_metadata(batch_ids)
            print(f"从 arXiv API 获取到 {len(papers)} 篇元数据")

            for p in papers:
                arxiv_id = p["arxiv_id"]
                title = p["title"]

                if is_paper_successful(db_path, arxiv_id, email_date_folder):
                    print(f"跳过已处理论文: {arxiv_id}")
                    continue

                try:
                    summary_result = summarize_from_abstract(p)

                    note_content = build_paper_note(
                        paper=p,
                        summary=summary_result,
                        date_folder=email_date_folder,
                    )

                    note_path = write_paper_note(
                        vault_path=vault_path,
                        papers_root=papers_root,
                        date_folder=email_date_folder,
                        arxiv_id=arxiv_id,
                        title=title,
                        content=note_content,
                    )

                    mark_paper_processed(
                        db_path=db_path,
                        arxiv_id=arxiv_id,
                        date_folder=email_date_folder,
                        gmail_message_id=gmail_message_id,
                        title=title,
                        note_path=str(note_path),
                        processed_at=now_iso(),
                        status="success",
                    )

                    processed_count += 1
                    print(f"写入成功: {note_path}")

                except Exception as e:
                    mark_paper_processed(
                        db_path=db_path,
                        arxiv_id=arxiv_id,
                        date_folder=email_date_folder,
                        gmail_message_id=gmail_message_id,
                        title=title,
                        note_path="",
                        processed_at=now_iso(),
                        status="failed",
                        error_message=str(e),
                    )
                    print(f"处理论文失败: {arxiv_id} | {e}")
                    traceback.print_exc()

            remaining_ids = [
                aid for aid in arxiv_ids
                if not is_paper_successful(db_path, aid, email_date_folder)
            ]

            if remaining_ids:
                mark_email_processed(
                    db_path=db_path,
                    gmail_message_id=gmail_message_id,
                    subject=subject,
                    processed_at=now_iso(),
                    status="partial",
                    error_message=f"{len(remaining_ids)} papers remaining",
                )
                print(f"邮件部分完成，还剩 {len(remaining_ids)} 篇: {gmail_message_id}")
            else:
                mark_email_processed(
                    db_path=db_path,
                    gmail_message_id=gmail_message_id,
                    subject=subject,
                    processed_at=now_iso(),
                    status="complete",
                )
                print(f"邮件全部完成: {gmail_message_id}")

        except Exception as e:
            mark_email_processed(
                db_path=db_path,
                gmail_message_id=gmail_message_id,
                subject=subject,
                processed_at=now_iso(),
                status="failed",
                error_message=str(e),
            )
            print(f"处理邮件失败: {gmail_message_id} | {e}")
            traceback.print_exc()

    # 每次运行后，重建本次涉及日期的完整 index.md
    for date_folder in sorted(touched_dates):
        index_items = load_index_items_from_vault(vault_path, papers_root, date_folder)
        if not index_items:
            continue

        index_content = build_daily_index(
            date_folder=date_folder,
            papers=index_items,
        )

        index_path = write_daily_index(
            vault_path=vault_path,
            papers_root=papers_root,
            date_folder=date_folder,
            content=index_content,
        )

        print(f"写入每日索引: {index_path}")

    print(f"本次成功处理论文数: {processed_count}")


if __name__ == "__main__":
    main()
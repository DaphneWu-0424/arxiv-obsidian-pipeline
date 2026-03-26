from __future__ import annotations

import os
import traceback
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import yaml
from dotenv import load_dotenv

from gmail_client import build_gmail_session, list_recent_arxiv_messages, get_message_text
from email_parser import extract_arxiv_ids_from_content
from arxiv_client import fetch_batch_metadata
from summarizer import summarize_from_abstract
from paper_enricher import enrich_paper_detail
from note_builder import build_paper_note
from obsidian_writer import write_paper_note, append_index_item
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


def process_one_paper(
    p: dict,
    email_date_folder: str,
    vault_path: str,
    papers_root: str,
    settings: dict,
) -> dict:
    arxiv_id = p["arxiv_id"]
    title = p["title"]

    summary_result = summarize_from_abstract(p)
    paper_with_assets, enrichment_result = enrich_paper_detail(p, settings)

    note_content = build_paper_note(
        paper=paper_with_assets,
        summary=summary_result,
        date_folder=email_date_folder,
        enrichment=enrichment_result,
    )

    note_path = write_paper_note(
        vault_path=vault_path,
        papers_root=papers_root,
        date_folder=email_date_folder,
        arxiv_id=arxiv_id,
        title=title,
        content=note_content,
    )

    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "note_path": str(note_path),
        "one_sentence_summary": summary_result["one_sentence_summary"],
    }


def main() -> None:
    settings = load_settings()

    credentials_path = os.getenv("GMAIL_CREDENTIALS_PATH", "config/credentials.json")
    token_path = os.getenv("GMAIL_TOKEN_PATH", "config/token.json")

    vault_path = settings["vault_path"]
    papers_root = settings["papers_root"]
    gmail_label = settings["gmail_label"]
    db_path = settings["database_path"]
    max_papers_per_run = int(settings.get("max_papers_per_run", 20))
    max_workers = int(settings.get("max_workers", 3))
    max_messages = int(settings.get("max_messages_per_run", 10))

    init_db(db_path)

    session = build_gmail_session(credentials_path, token_path)
    messages = list_recent_arxiv_messages(session, gmail_label, max_results=max_messages)

    print(f"扫描到 {len(messages)} 封邮件")

    processed_count = 0

    for m in messages:
        gmail_message_id = m["id"]
        subject = ""

        try:
            detail = get_message_text(session, gmail_message_id)
            subject = detail["subject"]

            body = detail.get("body", "")
            body_text = detail.get("body_text", "")
            body_html = detail.get("body_html", "")

            email_date_folder = detail.get("date_folder") or datetime.now().strftime("%Y-%m-%d")

            print("=" * 60)
            print("邮件主题:", subject)
            print("邮件接收时间:", detail.get("received_at", ""))
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
                print(f"邮件未提取到论文，标记失败待后续重试: {gmail_message_id}")
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

            if not papers:
                mark_email_processed(
                    db_path=db_path,
                    gmail_message_id=gmail_message_id,
                    subject=subject,
                    processed_at=now_iso(),
                    status="failed",
                    error_message="No papers fetched from arXiv API",
                )
                print(f"arXiv API 未返回论文元数据: {gmail_message_id}")
                continue

            worker_count = max(1, min(max_workers, len(papers)))
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                future_to_paper = {}

                for p in papers:
                    arxiv_id = p["arxiv_id"]

                    if is_paper_successful(db_path, arxiv_id, email_date_folder):
                        print(f"跳过已处理论文: {arxiv_id}")
                        continue

                    future = executor.submit(
                        process_one_paper,
                        p,
                        email_date_folder,
                        vault_path,
                        papers_root,
                        settings,
                    )
                    future_to_paper[future] = p

                for future in as_completed(future_to_paper):
                    p = future_to_paper[future]
                    arxiv_id = p["arxiv_id"]
                    title = p["title"]

                    try:
                        result = future.result()

                        mark_paper_processed(
                            db_path=db_path,
                            arxiv_id=arxiv_id,
                            date_folder=email_date_folder,
                            gmail_message_id=gmail_message_id,
                            title=title,
                            note_path=result["note_path"],
                            processed_at=now_iso(),
                            status="success",
                        )

                        append_index_item(
                            vault_path=vault_path,
                            papers_root=papers_root,
                            date_folder=email_date_folder,
                            note_name=Path(result["note_path"]).stem,
                            one_sentence_summary=result["one_sentence_summary"],
                        )

                        processed_count += 1
                        print(f"写入成功: {result['note_path']}")

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

    print(f"本次成功处理论文数: {processed_count}")


if __name__ == "__main__":
    main()
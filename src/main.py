from __future__ import annotations

import os
from datetime import datetime
import traceback

import yaml
from dotenv import load_dotenv

from gmail_client import build_gmail_session, list_recent_arxiv_messages, get_message_text
from email_parser import extract_arxiv_ids_from_content
from arxiv_client import fetch_batch_metadata
from summarizer import summarize_from_abstract
from note_builder import build_paper_note, build_daily_index
from obsidian_writer import write_paper_note, write_daily_index, make_note_filename
from db import (
    init_db,
    is_email_processed,
    mark_email_processed,
    is_paper_processed,
    mark_paper_processed,
)

load_dotenv()


def load_settings(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


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

    date_folder = datetime.now().strftime("%Y-%m-%d")
    index_items = []
    processed_count = 0

    for m in messages:
        gmail_message_id = m["id"]

        if is_email_processed(db_path, gmail_message_id):
            print(f"跳过已处理邮件: {gmail_message_id}")
            continue

        try:
            detail = get_message_text(session, gmail_message_id)
            subject = detail["subject"]
            body = detail["body"]

            print("=" * 60)
            print("邮件主题:", subject)

            arxiv_ids = extract_arxiv_ids_from_content(body)
            print(f"提取到 {len(arxiv_ids)} 个 arXiv ID")

            if not arxiv_ids:
                mark_email_processed(
                    db_path=db_path,
                    gmail_message_id=gmail_message_id,
                    subject=subject,
                    processed_at=now_iso(),
                    status="success",
                )
                continue

            # 先按配置限流，再过滤掉今天已处理过的论文
            limited_ids = arxiv_ids[:max_papers_per_run]
            pending_ids = [
                aid for aid in limited_ids
                if not is_paper_processed(db_path, aid, date_folder)
            ]

            print(f"本次待处理论文数: {len(pending_ids)}")

            if not pending_ids:
                mark_email_processed(
                    db_path=db_path,
                    gmail_message_id=gmail_message_id,
                    subject=subject,
                    processed_at=now_iso(),
                    status="success",
                )
                continue

            papers = fetch_batch_metadata(pending_ids)
            print(f"从 arXiv API 获取到 {len(papers)} 篇元数据")

            for p in papers:
                arxiv_id = p["arxiv_id"]
                title = p["title"]

                if is_paper_processed(db_path, arxiv_id, date_folder):
                    print(f"跳过已处理论文: {arxiv_id}")
                    continue

                try:
                    summary_result = summarize_from_abstract(p)

                    note_content = build_paper_note(
                        paper=p,
                        summary=summary_result,
                        date_folder=date_folder,
                    )

                    note_path = write_paper_note(
                        vault_path=vault_path,
                        papers_root=papers_root,
                        date_folder=date_folder,
                        arxiv_id=arxiv_id,
                        title=title,
                        content=note_content,
                    )

                    note_name = make_note_filename(arxiv_id, title).replace(".md", "")

                    index_items.append({
                        "note_name": note_name,
                        "one_sentence_summary": summary_result["one_sentence_summary"],
                        "note_path": str(note_path),
                    })

                    mark_paper_processed(
                        db_path=db_path,
                        arxiv_id=arxiv_id,
                        date_folder=date_folder,
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
                        date_folder=date_folder,
                        gmail_message_id=gmail_message_id,
                        title=title,
                        note_path="",
                        processed_at=now_iso(),
                        status="failed",
                        error_message=str(e),
                    )
                    print(f"处理论文失败: {arxiv_id} | {e}")
                    traceback.print_exc()

            mark_email_processed(
                db_path=db_path,
                gmail_message_id=gmail_message_id,
                subject=subject,
                processed_at=now_iso(),
                status="success",
            )

        except Exception as e:
            mark_email_processed(
                db_path=db_path,
                gmail_message_id=gmail_message_id,
                subject="",
                processed_at=now_iso(),
                status="failed",
                error_message=str(e),
            )
            print(f"处理邮件失败: {gmail_message_id} | {e}")
            traceback.print_exc()

    if index_items:
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
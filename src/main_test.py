import os
from dotenv import load_dotenv
from datetime import datetime
import yaml

from note_builder import build_paper_note, build_daily_index
from obsidian_writer import write_paper_note, write_daily_index, make_note_filename

import gmail_client
from email_parser import extract_arxiv_ids_from_content
from summarizer import summarize_from_abstract
from arxiv_client import fetch_batch_metadata
from gmail_client import build_gmail_session, list_recent_arxiv_messages, get_message_text

print("gmail_client file:", gmail_client.__file__)

load_dotenv()

def load_settings(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)




def main():
    settings = load_settings()


    credentials_path = os.getenv("GMAIL_CREDENTIALS_PATH", "config/credentials.json")
    token_path = os.getenv("GMAIL_TOKEN_PATH", "config/token.json")

    vault_path = settings["vault_path"]
    papers_root = settings["papers_root"]

    session = build_gmail_session(credentials_path, token_path)
    print("session =", session)
    print("session type =", type(session))

    messages = list_recent_arxiv_messages(session, "Arxiv/Daily", max_results=5)
    print(f"找到 {len(messages)} 封邮件")

    date_folder = datetime.now().strftime("%Y-%m-%d")
    index_items = []

    for m in messages:
        detail = get_message_text(session, m["id"])
        print("=" * 60)
        print("Subject:", detail["subject"])
        print("Snippet:", detail["snippet"])
        print("Body preview:", detail["body"][:300])


        arxiv_ids = extract_arxiv_ids_from_content(detail["body"])
        print("arXiv IDs count:", len(arxiv_ids))
        print("First 10 arXiv IDs:", arxiv_ids[:10])

        max_papers = min(settings.get("max_papers_per_run", 20), 3)
        test_ids = arxiv_ids[:3]
        papers = fetch_batch_metadata(test_ids)

        print(f"Fetched {len(papers)} papers from arXiv API")
        for p in papers:
            print("-" * 60)
            print("ID:", p["arxiv_id"])
            print("Version:", p["arxiv_version"])
            print("Title:", p["title"])
            print("Authors:", ", ".join(p["authors"][:5]))
            print("Categories:", p["categories"])
            print("Summary preview:", p["summary"][:200])


            summary_result = summarize_from_abstract(p)
            print("AI one_sentence_summary:", summary_result["one_sentence_summary"])
            print("AI key_points:", summary_result["key_points"])

            note_content = build_paper_note(
                paper=p,
                summary=summary_result,
                date_folder=date_folder,
            )

            note_path = write_paper_note(
                vault_path=vault_path,
                papers_root=papers_root,
                date_folder=date_folder,
                arxiv_id=p["arxiv_id"],
                title=p["title"],
                content=note_content,
            )

            note_name = make_note_filename(p["arxiv_id"], p["title"]).replace(".md", "")

            index_items.append({
                "note_name": note_name,
                "one_sentence_summary": summary_result["one_sentence_summary"],
                "note_path": str(note_path),
            })

            print("Wrote note:", note_path)

        break  # 测试期只处理第一封邮件

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

    print("Wrote daily index:", index_path)


if __name__ == "__main__":
    main()
import os
from dotenv import load_dotenv

import gmail_client
from email_parser import extract_arxiv_ids_from_content
from gmail_client import build_gmail_session, list_recent_arxiv_messages, get_message_text

print("gmail_client file:", gmail_client.__file__)

load_dotenv()


def main():
    credentials_path = os.getenv("GMAIL_CREDENTIALS_PATH", "config/credentials.json")
    token_path = os.getenv("GMAIL_TOKEN_PATH", "config/token.json")

    session = build_gmail_session(credentials_path, token_path)
    print("session =", session)
    print("session type =", type(session))

    messages = list_recent_arxiv_messages(session, "Arxiv/Daily", max_results=5)
    print(f"找到 {len(messages)} 封邮件")

    for m in messages:
        detail = get_message_text(session, m["id"])
        print("=" * 60)
        print("Subject:", detail["subject"])
        print("Snippet:", detail["snippet"])
        print("Body preview:", detail["body"][:300])
        arxiv_ids = extract_arxiv_ids_from_content(detail["body"])
        print("arXiv IDs:", arxiv_ids)


if __name__ == "__main__":
    main()
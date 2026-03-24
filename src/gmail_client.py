from __future__ import annotations

import base64
import os
from typing import List, Dict, Any
from datetime import datetime

from google.auth.transport.requests import Request, AuthorizedSession
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def build_gmail_session(credentials_path: str, token_path: str) -> AuthorizedSession:
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(host="127.0.0.1", port=0)

        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    return AuthorizedSession(creds)


def list_recent_arxiv_messages(
    session: AuthorizedSession,
    label_name: str,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    params = {
        "q": f"label:{label_name}",
        "maxResults": max_results,
    }

    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("messages", [])


def _decode_base64url(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    decoded_bytes = base64.urlsafe_b64decode((data + padding).encode("utf-8"))
    return decoded_bytes.decode("utf-8", errors="ignore")


def _get_attachment_text(
    session: AuthorizedSession,
    message_id: str,
    attachment_id: str,
) -> str:
    url = (
        f"https://gmail.googleapis.com/gmail/v1/users/me/messages/"
        f"{message_id}/attachments/{attachment_id}"
    )
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json().get("data", "")
    if not data:
        return ""
    return _decode_base64url(data)


def _get_message_raw(session: AuthorizedSession, message_id: str) -> str:
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
    params = {"format": "raw"}
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    raw_data = resp.json().get("raw", "")
    if not raw_data:
        return ""
    return _decode_base64url(raw_data)


def get_message_text(session: AuthorizedSession, message_id: str) -> Dict[str, Any]:
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"
    params = {"format": "full"}

    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    msg = resp.json()

    payload = msg.get("payload", {})
    headers = payload.get("headers", [])

    subject = ""
    for h in headers:
        if h["name"].lower() == "subject":
            subject = h["value"]
            break

    snippet = msg.get("snippet", "")

    internal_date_ms = msg.get("internalDate")
    received_at = None
    date_folder = None
    if internal_date_ms:
        received_at = datetime.fromtimestamp(int(internal_date_ms) / 1000)
        date_folder = received_at.strftime("%Y-%m-%d")

    plain_parts: list[str] = []
    html_parts: list[str] = []

    def collect_parts(part: Dict[str, Any]) -> None:
        mime_type = part.get("mimeType", "")
        body = part.get("body", {}) or {}
        data = body.get("data")
        attachment_id = body.get("attachmentId")

        text = ""
        if mime_type in ("text/plain", "text/html"):
            if data:
                text = _decode_base64url(data)
            elif attachment_id:
                text = _get_attachment_text(session, message_id, attachment_id)

            if text:
                if mime_type == "text/plain":
                    plain_parts.append(text)
                else:
                    html_parts.append(text)

        for sub_part in part.get("parts", []) or []:
            collect_parts(sub_part)

    collect_parts(payload)

    body_text = "\n".join(plain_parts).strip()
    body_html = "\n".join(html_parts).strip()

    # 兜底：如果 full 一个正文 part 都没拿到，就退回 raw
    if not body_text and not body_html:
        raw_text = _get_message_raw(session, message_id)
        body_text = raw_text.strip()

    combined_body = body_text if body_text else body_html

    return {
        "id": message_id,
        "subject": subject,
        "snippet": snippet,
        "body": combined_body,
        "body_text": body_text,
        "body_html": body_html,
        "internal_date_ms": internal_date_ms,
        "received_at": received_at.isoformat() if received_at else "",
        "date_folder": date_folder or "",
    }
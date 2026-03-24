from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

def get_conn(db_path: str) -> sqlite3.Connection:
    '''
    创建并返回一个到 SQLite 数据库的连接对象
    '''
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row # 将工厂设置为sqlite3.row类型，这样查询返回的行可以作为字典或通过列名访问
    return conn

def init_db(db_path:str) -> None:
    '''
    初始化数据库，创建两个表，processed_emails用于记录已经处理的邮件，
    里面的id, gmail_message_id等都是列名
    '''
    with get_conn(db_path) as conn:
        conn.execute(
            '''
        CREATE TABLE IF NOT EXISTS processed_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gmail_message_id TEXT NOT NULL UNIQUE,
            subject TEXT,
            processed_at TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT
        )
            '''
        )

        conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            arxiv_id TEXT NOT NULL,
            date_folder TEXT NOT NULL,
            gmail_message_id TEXT,
            title TEXT,
            note_path TEXT,
            processed_at TEXT NOT NULL,
            status TEXT NOT NULL,
            error_message TEXT,
            UNIQUE(arxiv_id, date_folder)
        )
        """)

        conn.commit()

def is_email_processed(db_path: str, gmail_message_id: str) -> bool:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM processed_emails WHERE gmail_message_id = ? LIMIT 1",
            (gmail_message_id,),
        ).fetchone()
        return row is not None
    

def mark_email_processed(
    db_path: str,
    gmail_message_id: str,
    subject: str,
    processed_at: str,
    status: str = "success",
    error_message: Optional[str] = None,
) -> None:
    with get_conn(db_path) as conn:
        conn.execute("""
        INSERT INTO processed_emails (
            gmail_message_id, subject, processed_at, status, error_message
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(gmail_message_id) DO UPDATE SET
            subject=excluded.subject,
            processed_at=excluded.processed_at,
            status=excluded.status,
            error_message=excluded.error_message
        """, (gmail_message_id, subject, processed_at, status, error_message))
        conn.commit()


def is_paper_processed(db_path: str, arxiv_id: str, date_folder: str) -> bool:
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM processed_papers WHERE arxiv_id = ? AND date_folder = ? LIMIT 1",
            (arxiv_id, date_folder),
        ).fetchone()
        return row is not None


def mark_paper_processed(
    db_path: str,
    arxiv_id: str,
    date_folder: str,
    gmail_message_id: str,
    title: str,
    note_path: str,
    processed_at: str,
    status: str = "success",
    error_message: Optional[str] = None,
) -> None:
    with get_conn(db_path) as conn:
        conn.execute("""
        INSERT INTO processed_papers (
            arxiv_id, date_folder, gmail_message_id, title, note_path,
            processed_at, status, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(arxiv_id, date_folder) DO UPDATE SET
            gmail_message_id=excluded.gmail_message_id,
            title=excluded.title,
            note_path=excluded.note_path,
            processed_at=excluded.processed_at,
            status=excluded.status,
            error_message=excluded.error_message
        """, (
            arxiv_id, date_folder, gmail_message_id, title, note_path,
            processed_at, status, error_message
        ))
        conn.commit()
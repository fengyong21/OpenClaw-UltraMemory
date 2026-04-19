#!/usr/bin/env python3
"""归档当前对话到 SQLite + Markdown 分片（V2：含 Parent_ID 链表）"""
import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from simhash_core import compute_simhash, compute_instruction_hash, hamming_key

MEMORY_DIR = Path.home() / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "simhash.db"
RAW_DIR = MEMORY_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def get_last_simhash(session_id: str) -> int | None:
    """查询上一轮对话的 SimHash，用于填入 Parent_ID"""
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT simhash FROM memory_index WHERE session_id=? ORDER BY id DESC LIMIT 1",
        (session_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


def archive_dialogue(
    dialogue_text: str,
    instruction_text: str,
    session_id: str,
    summary: str = ""
):
    """
    归档入口：
    1. 计算 SimHash + Parent_ID + instruction_hash
    2. 写入 SQLite（含链表指针）
    3. 追加原始文本到 Markdown
    4. 更新 session_anchor（防迷失锚点）
    """
    sim = compute_simhash(dialogue_text)
    key = hamming_key(sim)
    parent_id = get_last_simhash(session_id)
    instr_hash = compute_instruction_hash(instruction_text)
    today = datetime.now().strftime("%Y-%m-%d")

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS memory_index (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        simhash INTEGER NOT NULL,
        parent_id INTEGER,
        instruction_hash INTEGER NOT NULL,
        hamming_key TEXT NOT NULL,
        date TEXT NOT NULL,
        session_id TEXT NOT NULL,
        source_file TEXT NOT NULL,
        summary TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS session_anchor (
        session_id TEXT PRIMARY KEY,
        instruction_text TEXT NOT NULL,
        instruction_hash INTEGER NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    source_file = str(RAW_DIR / f"{today}.md")

    conn.execute(
        """INSERT INTO memory_index
           (simhash, parent_id, instruction_hash, hamming_key, date, session_id, source_file, summary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (sim, parent_id, instr_hash, key, today, session_id, source_file, summary)
    )
    conn.execute(
        """INSERT OR REPLACE INTO session_anchor (session_id, instruction_text, instruction_hash)
           VALUES (?, ?, ?)""",
        (session_id, instruction_text, instr_hash)
    )
    conn.commit()
    conn.close()

    with open(source_file, "a", encoding="utf-8") as f:
        f.write(f"\n---\n## Session {session_id} | {today}\n{dialogue_text}\n")

    print(f"归档完成 | 指纹: {sim} | Parent: {parent_id} | 会话: {session_id}")

if __name__ == "__main__":
    argv = sys.argv[1:]
    dialogue = argv[0]
    instruction = argv[1] if len(argv) > 1 else ""
    session_id = argv[2] if len(argv) > 2 else "default"
    summary = argv[3] if len(argv) > 3 else ""
    archive_dialogue(dialogue, instruction, session_id, summary)

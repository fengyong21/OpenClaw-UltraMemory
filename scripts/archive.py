#!/usr/bin/env python3
"""
archive.py — 归档脚本：将对话历史写入 SQLite + Markdown 分片

功能：
1. 计算对话的 SimHash 指纹
2. 写入 simhash.db（指纹 + 元数据）
3. 追加原文到 raw/YYYY-MM-DD.md

使用方式：
    python3 archive.py "对话内容" [摘要]

示例：
    python3 archive.py "这是一个关于 OpenClaw 记忆优化的讨论" "讨论了记忆架构"
"""

import sys
import sqlite3
from datetime import datetime
from pathlib import Path

# 导入核心算法
from simhash_core import compute_simhash, hamming_key

# ========== 配置 ==========
# 默认路径，可通过环境变量覆盖
MEMORY_DIR = Path.home() / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "simhash.db"
RAW_DIR = MEMORY_DIR / "raw"

# 确保目录存在
RAW_DIR.mkdir(parents=True, exist_ok=True)


def init_db():
    """初始化 SQLite 表结构"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_index (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            simhash     INTEGER NOT NULL,
            hamming_key TEXT NOT NULL,
            date        TEXT NOT NULL,
            source_file TEXT NOT NULL,
            summary     TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hamming_key ON memory_index(hamming_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_simhash ON memory_index(simhash)")
    conn.commit()
    return conn


def archive_dialogue(dialogue_text: str, summary: str = "") -> dict:
    """
    归档一条对话记录。

    Args:
        dialogue_text: 原始对话内容
        summary: 可选摘要（<= 140 字）

    Returns:
        dict: 归档结果（含指纹、日期、文件路径）
    """
    # 计算指纹
    sim = compute_simhash(dialogue_text)
    key = hamming_key(sim)
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 原始文件路径
    source_file = str(RAW_DIR / f"{today}.md")

    # 写入 SQLite
    conn = init_db()
    conn.execute(
        """
        INSERT INTO memory_index (simhash, hamming_key, date, source_file, summary)
        VALUES (?, ?, ?, ?, ?)
        """,
        (sim, key, today, source_file, summary[:140] if summary else "")
    )
    conn.commit()
    conn.close()

    # 追加原文到 Markdown 分片
    entry = f"""
---
## [{timestamp}]
{summary or '(无摘要)'}

{dialogue_text}
"""
    with open(source_file, "a", encoding="utf-8") as f:
        f.write(entry)

    return {
        "simhash": sim,
        "hamming_key": key,
        "date": today,
        "source_file": source_file,
        "status": "归档成功"
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python3 archive.py <对话内容> [摘要]")
        sys.exit(1)

    dialogue = sys.argv[1]
    summary = sys.argv[2] if len(sys.argv) > 2 else ""

    result = archive_dialogue(dialogue, summary)

    # 输出状态（供外部调用捕获）
    print(f"[claw-memory] 归档完成 | 指纹: {result['simhash']} | 日期: {result['date']} | 存储: 极小")
    print(f"[claw-memory] 索引记录数: {sqlite3.connect(str(DB_PATH)).execute('SELECT COUNT(*) FROM memory_index').fetchone()[0]}")


if __name__ == "__main__":
    main()

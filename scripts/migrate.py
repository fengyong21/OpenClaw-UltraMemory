#!/usr/bin/env python3
"""
migrate.py — 迁移脚本：批量为已有 Markdown 文件建立 simhash.db 索引

功能：
1. 扫描 ~/.workbuddy/*/memory/*.md
2. 对每个文件计算 SimHash
3. 写入 simhash.db，建立索引
4. 打印迁移报告

使用方式：
    python3 migrate.py

一次性操作，迁移完成后可删除。
"""

import sqlite3
from pathlib import Path
from datetime import datetime

from simhash_core import compute_simhash, hamming_key

# ========== 配置 ==========
HOME = Path.home()
MEMORY_DIR = HOME / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "simhash.db"


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


def scan_md_files() -> list:
    """扫描所有 .md 文件（支持 workspace 子目录）"""
    md_files = []

    workbuddy = HOME / ".workbuddy"
    if not workbuddy.exists():
        return md_files

    # 扫描所有 workspace 目录下的 memory/*.md
    for workspace in workbuddy.iterdir():
        if workspace.is_dir() and not workspace.name.startswith('.'):
            memory_dir = workspace / "memory"
            if memory_dir.exists():
                for md in memory_dir.glob("*.md"):
                    if md.name not in ("MEMORY.md",):  # 排除灵魂记忆文件
                        md_files.append(md)

    # 也扫描根目录 memory/
    if MEMORY_DIR.exists():
        for md in MEMORY_DIR.glob("*.md"):
            if md.name not in ("MEMORY.md",):
                md_files.append(md)

    return md_files


def migrate():
    """执行迁移"""
    md_files = scan_md_files()

    if not md_files:
        print("[claw-memory] 未找到需要迁移的 Markdown 文件")
        print(f"[claw-memory] 请确认 ~/.workbuddy/ 下存在 memory/*.md 文件")
        return

    conn = init_db()
    success = 0
    skipped = 0

    for md in md_files:
        try:
            text = md.read_text(encoding="utf-8")
            if not text.strip():
                skipped += 1
                continue

            sim = compute_simhash(text)
            key = hamming_key(sim)
            date = md.stem  # 文件名作为日期

            # 检查是否已存在
            exists = conn.execute(
                "SELECT 1 FROM memory_index WHERE simhash=?", (sim,)
            ).fetchone()

            if not exists:
                conn.execute(
                    """INSERT INTO memory_index
                       (simhash, hamming_key, date, source_file, summary)
                       VALUES (?, ?, ?, ?, ?)""",
                    (sim, key, date, str(md), f"[迁移] {md.name}")
                )
                success += 1
            else:
                skipped += 1

        except Exception as e:
            print(f"[claw-memory] 跳过 {md}: {e}")
            skipped += 1

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM memory_index").fetchone()[0]
    conn.close()

    print(f"[claw-memory] 迁移完成！")
    print(f"  ✓ 新增记录: {success} 条")
    print(f"  - 跳过（已存在/空文件）: {skipped} 条")
    print(f"  - simhash.db 总记录数: {total} 条")


if __name__ == "__main__":
    migrate()

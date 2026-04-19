#!/usr/bin/env python3
"""
migrate.py — V3 历史数据迁移脚本

功能：
1. 扫描 ~/.workbuddy/*/memory/*.md 历史文件
2. 按 "---" 分隔符拆分为独立记忆片段
3. 批量写入 hot_window.db（heat=1，走完整个写入流程，含自然衰减）
4. 打印迁移报告

使用方式：
    python3 migrate.py

一次性操作，迁移完成后可保留或删除。
"""
import sys
import sqlite3
import re
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ──────────── 路径配置（与 hot_window.py 保持一致）────────────
HOME = Path.home()
MEMORY_DIR = HOME / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "hot_window.db"
RAW_DIR = MEMORY_DIR / "raw"

# ──────────── V3 核心参数（必须与 hot_window.py 一致）────────────
WINDOW_SIZE  = 1000
PROTECT_SECS = 604800   # 7 天
DECAY_RATE   = 0.99
HEAT_CAP     = 200
HEAT_FLOOR   = 1
TOP_K        = 10

# ──────────── 工具函数（复制自 hot_window.py）────────────
def _simple_hash(text: str) -> str:
    from collections import Counter
    freq = Counter(text.lower()[:200])
    return "".join(f"{k}{v}" for k, v in sorted(freq.items())[:16])

def _hash_distance(a: str, b: str) -> int:
    return sum(1 for x, y in zip(a.ljust(32), b.ljust(32)) if x != y)

def _extract_keywords(text: str) -> list:
    words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', text)
    return list(set(words))[:5]

# ──────────── DB 初始化 ─────────────
def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_link  TEXT    NOT NULL,
            heat      REAL    NOT NULL DEFAULT 1,
            timestamp INTEGER NOT NULL,
            summary   TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_heat ON memory(heat DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts   ON memory(timestamp)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_anchor (
            session_id       TEXT PRIMARY KEY,
            instruction_text TEXT NOT NULL,
            instruction_hash TEXT NOT NULL,
            created_at       INTEGER NOT NULL
        )
    """)
    conn.commit()

# ──────────── 扫描历史文件 ─────────────
def scan_md_files() -> list:
    """扫描所有 memory/*.md，排除 MEMORY.md"""
    md_files = []

    # 1. ~/.workbuddy/memery/（拼写错误的历史遗留目录）
    memery_dir = HOME / ".workbuddy" / "memery"
    if memery_dir.exists():
        for md in memery_dir.glob("*.md"):
            md_files.append(md)

    # 2. ~/.workbuddy/*/memory/*.md
    workbuddy = HOME / ".workbuddy"
    if workbuddy.exists():
        for workspace in workbuddy.iterdir():
            if not workspace.is_dir() or workspace.name.startswith('.'):
                continue
            memory_dir = workspace / "memory"
            if memory_dir.exists():
                for md in memory_dir.glob("*.md"):
                    if md.name not in ("MEMORY.md",):
                        md_files.append(md)

    # 3. ~/WorkBuddy/*/.workbuddy/memory/*.md（实际工作区路径）
    workbuddy_projects = HOME / "WorkBuddy"
    if workbuddy_projects.exists():
        for project in workbuddy_projects.iterdir():
            if not project.is_dir():
                continue
            memory_dir = project / ".workbuddy" / "memory"
            if memory_dir.exists():
                for md in memory_dir.glob("*.md"):
                    if md.name not in ("MEMORY.md",):
                        md_files.append(md)

    return md_files


def split_sections(md_path: Path) -> list:
    """
    按 ## 时间戳 模式拆分文件为独立记忆片段。
    同时兼容纯文本（无分隔符则整块作为一个记忆）。
    """
    text = md_path.read_text(encoding="utf-8")

    # 优先按 ## ISO时间戳 分隔
    pattern = r'(?=^## \d{4}-\d{2}-\d{2})'
    sections = re.split(pattern, text, flags=re.MULTILINE)

    results = []
    for section in sections:
        section = section.strip()
        if not section or len(section) < 20:
            continue
        # 提取第一行作摘要
        first_line = section.split('\n')[0].strip('# ').strip()
        results.append({
            "text": section,
            "summary": first_line[:120] if first_line else section[:60],
        })
    return results


# ──────────── 写入单条（不走完整流程，直接插 DB）────────────
def insert_migration_record(conn: sqlite3.Connection, raw_link: str,
                            summary: str, timestamp: int) -> int:
    """
    直接插入 DB，不走 write_memory 流程（避免对大量历史数据重复触发衰减/淘汰）。
    迁移完成后统一做一次 evict。
    """
    cursor = conn.execute(
        "INSERT INTO memory (raw_link, heat, timestamp, summary) VALUES (?, 1, ?, ?)",
        (raw_link, timestamp, summary)
    )
    return cursor.lastrowid


# ──────────── 主迁移流程 ─────────────
def migrate():
    print("=" * 50)
    print("Claw Memory V3 — 历史数据迁移")
    print("=" * 50)

    md_files = scan_md_files()
    if not md_files:
        print("[claw-memory] 未找到需要迁移的 Markdown 文件")
        print(f"[claw-memory] 扫描路径：~/.workbuddy/*/memory/*.md")
        return

    # 初始化 DB
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)

    # 检查已有记录数
    before_count = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    print(f"\n📂 扫描到 {len(md_files)} 个历史文件")
    print(f"📊 hot_window.db 现有记录：{before_count} 条\n")

    total_inserted = 0
    total_skipped = 0

    # 收集所有待写入的片段（统一衰减和淘汰）
    pending = []

    for md_path in sorted(md_files):
        sections = split_sections(md_path)
        if not sections:
            total_skipped += 1
            continue

        # 从文件名推断日期时间戳
        date_str = md_path.stem  # e.g. "2026-04-18"
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            ts = int(dt.replace(tzinfo=timezone.utc).timestamp())
        except ValueError:
            ts = int(md_path.stat().st_mtime)

        for sec in sections:
            # 写入原始文本到 raw/
            raw_path = RAW_DIR / f"migrated_{date_str}.md"
            with open(raw_path, "a", encoding="utf-8") as f:
                f.write(f"\n---\n## [迁移] {md_path.name} @ {date_str}\n{sec['text']}\n")

            pending.append({
                "raw_link": str(raw_path),
                "summary": sec["summary"],
                "timestamp": ts,
            })
            total_inserted += 1

    print(f"📝 待迁移记忆片段：{total_inserted} 条")
    if total_inserted == 0:
        print("[claw-memory] 没有新的记忆片段需要迁移")
        conn.close()
        return

    # 批量写入（heat=1）
    print("\n⚙️  开始写入...")
    for item in pending:
        insert_migration_record(conn, item["raw_link"],
                                item["summary"], item["timestamp"])

    # 批量自然衰减
    print("📉 应用自然衰减...")
    conn.execute(f"""
        UPDATE memory
        SET heat = MAX({HEAT_FLOOR}, MIN({HEAT_CAP}, heat * {DECAY_RATE}))
        WHERE id NOT IN (
            SELECT id FROM memory ORDER BY timestamp DESC LIMIT {len(pending)}
        )
    """)

    conn.commit()

    # 批量淘汰（超出窗口时）
    total_count = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    if total_count > WINDOW_SIZE:
        print(f"🗑️  记录数 ({total_count}) 超窗口 ({WINDOW_SIZE})，执行淘汰...")
        excess = total_count - WINDOW_SIZE
        protect_ts = int(time.time()) - PROTECT_SECS
        conn.execute(f"""
            DELETE FROM memory
            WHERE id IN (
                SELECT id FROM memory
                WHERE timestamp < {protect_ts}
                ORDER BY heat ASC, timestamp ASC
                LIMIT {excess}
            )
        """)
        conn.commit()

    after_count = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    conn.close()

    print("\n" + "=" * 50)
    print("✅ 迁移完成！")
    print(f"  ✓ 新增记录：{total_inserted} 条")
    print(f"  - 跳过（空/无效）：{total_skipped} 条")
    print(f"  - DB 现总记录：{after_count} 条")
    print(f"  - 热数据目录：{RAW_DIR}")
    print("=" * 50)


if __name__ == "__main__":
    migrate()

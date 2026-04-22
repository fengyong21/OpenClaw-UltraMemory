#!/usr/bin/env python3
"""
V4 → V5 迁移脚本
将旧 schema（id, parent_id, simhash, raw_link, heat, timestamp, summary）
迁移到新 schema（simhash, raw_link, meta）
"""
import sqlite3
import json
import shutil
import re
from pathlib import Path
from datetime import datetime

MEMORY_DIR = Path.home() / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "hot_window.db"
BACKUP_DIR = MEMORY_DIR / "backup_v4"

def backup_db():
    """备份旧数据库"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f"hot_window_v4_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, backup_path)
        print(f"✅ 备份完成: {backup_path}")
    return backup_path

def read_raw_v4(raw_path: str) -> str:
    """读取 V4 格式的 raw 文件"""
    try:
        with open(raw_path, encoding="utf-8") as f:
            content = f.read()
            # V4 格式: ## timestamp\ntext
            lines = content.split("\n")
            text_lines = []
            in_content = False
            for line in lines:
                if line.startswith("## "):
                    in_content = True
                    continue
                if in_content:
                    text_lines.append(line)
            return "\n".join(text_lines).strip()
    except FileNotFoundError:
        return ""

def compute_simhash_v5(text: str) -> str:
    """
    V5 进阶级 SimHash：多粒度 + 加权
    """
    STOPWORDS = {
        '的', '了', '是', '在', '和', '有', '我', '你', '他', '她', '它',
        '这', '那', '个', '一', '不', '也', '就', '都', '要', '会', '可以',
        'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been',
        'have', 'has', 'had', 'do', 'does', 'did', 'to', 'of', 'in',
    }

    if not text or len(text.strip()) < 2:
        return "0" * 16

    HASH_BITS = 64

    # 多粒度 n-gram
    ngrams_list = [
        [text[i:i+2] for i in range(max(0, len(text)-1))],  # 2-gram
        [text[i:i+3] for i in range(max(0, len(text)-2))],  # 3-gram
        [text[i:i+4] for i in range(max(0, len(text)-3))],  # 4-gram
    ]
    ngram_weights = [0.3, 0.4, 0.3]

    v = [0.0] * HASH_BITS

    from collections import Counter

    for ngrams, ngram_weight in zip(ngrams_list, ngram_weights):
        if not ngrams:
            continue
        freq = Counter(ngrams)
        total = len(ngrams)

        for ngram, count in freq.items():
            tf = count / total
            is_stop = any(stop in ngram for stop in STOPWORDS)
            stop_penalty = 0.3 if is_stop else 1.0
            weight = tf * ngram_weight * stop_penalty

            h = hash(ngram)
            for i in range(HASH_BITS):
                if h >> i & 1:
                    v[i] += weight
                else:
                    v[i] -= weight

    fingerprint = 0
    for i in range(HASH_BITS):
        if v[i] > 0:
            fingerprint |= (1 << i)

    return format(fingerprint, '016x')


def migrate():
    """执行迁移"""
    print("🚀 开始 V4 → V5 迁移...")

    # 1. 备份
    backup_path = backup_db()

    # 2. 读取 V4 数据
    conn = sqlite3.connect(str(DB_PATH))

    try:
        rows = conn.execute("""
            SELECT id, parent_id, simhash, raw_link, heat, timestamp, summary
            FROM memory
        """).fetchall()
    except sqlite3.OperationalError as e:
        print(f"⚠️  无法读取 V4 数据: {e}")
        conn.close()
        return
    conn.close()

    if not rows:
        print("📭 无 V4 数据，跳过迁移")
        return

    print(f"📦 找到 {len(rows)} 条 V4 记录")

    # 3. 重新计算 simhash 并构建 V5 数据
    new_rows = []
    for row in rows:
        rec_id, parent_id, old_simhash, raw_link, heat, timestamp, summary = row

        # 读取 raw 内容重新计算 simhash
        raw_text = read_raw_v4(raw_link) if raw_link else ""
        if raw_text:
            new_simhash = compute_simhash_v5(raw_text)
        else:
            new_simhash = old_simhash or "0" * 16

        meta = {
            "timestamp": timestamp,
            "parent_id": parent_id,
        }

        new_rows.append((new_simhash, raw_link, json.dumps(meta, ensure_ascii=False)))

    print(f"✅ 重新计算 simhash 完成")

    # 4. 重命名旧表，创建新表
    conn = sqlite3.connect(str(DB_PATH))

    # 重命名旧表
    conn.execute("ALTER TABLE memory RENAME TO memory_v4")
    conn.execute("DROP INDEX IF EXISTS idx_heat")
    conn.execute("DROP INDEX IF EXISTS idx_ts")
    conn.execute("DROP INDEX IF EXISTS idx_parent")
    conn.commit()

    # 创建 V5 新表
    conn.execute("""
        CREATE TABLE memory (
            simhash   TEXT PRIMARY KEY,
            raw_link  TEXT NOT NULL,
            meta      TEXT
        )
    """)
    conn.commit()

    # 5. 写入 V5 数据
    success = 0
    skipped = 0
    for simhash, raw_link, meta in new_rows:
        try:
            conn.execute(
                "INSERT INTO memory (simhash, raw_link, meta) VALUES (?, ?, ?)",
                (simhash, raw_link, meta)
            )
            success += 1
        except sqlite3.IntegrityError:
            # 重复 simhash，跳过
            skipped += 1

    conn.commit()
    conn.close()

    print(f"✅ 迁移完成!")
    print(f"   - 成功: {success} 条")
    print(f"   - 跳过（重复）: {skipped} 条")
    print(f"   - 备份: {backup_path}")
    print(f"\n📋 V5 新 schema: simhash + raw_link + meta")


def rollback(backup_file: str):
    """回滚到 V4"""
    if not Path(backup_file).exists():
        print(f"⚠️  备份文件不存在: {backup_file}")
        return

    conn = sqlite3.connect(str(DB_PATH))

    # 删除 V5 表
    conn.execute("DROP TABLE IF EXISTS memory")

    # 恢复备份
    conn.execute(f"ATTACH DATABASE '{backup_file}' AS backup")
    conn.execute("CREATE TABLE memory AS SELECT * FROM backup.memory")
    conn.execute("DETACH DATABASE backup")

    conn.close()
    print(f"✅ 回滚完成")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        if len(sys.argv) > 2:
            rollback(sys.argv[2])
        else:
            print("用法: migrate_v5.py rollback <backup_file>")
    else:
        migrate()

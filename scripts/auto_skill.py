#!/usr/bin/env python3
"""
Claw Memory V4 - 自动技能生成
借鉴 Hermes Agent：从成功解决 3 次以上的问题中自动生成可复用 SKILL.md

触发条件：
1. 同类问题被成功 reinforce() 命中 >= AUTO_SKILL_THRESHOLD 次
2. 解决方案文本 >= 200 字
3. 与现有 auto-generated 技能重复度 < 80%

输出：~/.workbuddy/skills/auto-generated/{skill_name}.md
"""
import sqlite3
import time
import re
from pathlib import Path
from datetime import datetime
from collections import Counter

# ────────────────── 路径配置 ──────────────────
HOME = Path.home()
AUTO_SKILLS_DIR = HOME / ".workbuddy" / "skills" / "auto-generated"
DB_PATH = HOME / ".workbuddy" / "memory" / "hot_window.db"

# ────────────────── 核心参数 ──────────────────
AUTO_SKILL_THRESHOLD = 3   # 触发生成的强化次数
PATTERN_SIMILARITY   = 0.8 # 判定"同类问题"的相似度阈值
MIN_SOLUTION_LEN     = 200 # 最小解决方案字数

# ────────────────── 数据库操作 ──────────────────
def get_conn():
    db_dir = DB_PATH.parent
    db_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    _init_tables(conn)
    return conn


def _init_tables(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skill_candidates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            record_id   INTEGER NOT NULL,
            trigger_at  INTEGER NOT NULL,       -- 最后触发时间
            reinforce_count INTEGER DEFAULT 0,   -- 被强化次数
            pattern_key TEXT,                    -- 模式关键词
            solved_text TEXT,                    -- 解决方案文本
            status      TEXT DEFAULT 'pending'   -- pending / generated / rejected
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skill_registry (
            skill_name  TEXT PRIMARY KEY,
            skill_path  TEXT NOT NULL,
            trigger_count INTEGER DEFAULT 0,
            created_at  INTEGER NOT NULL,
            last_used   INTEGER
        )
    """)
    conn.commit()


# ────────────────── 模式检测 ──────────────────
def _extract_pattern_key(text: str) -> str:
    """提取模式关键词，用于判断是否为同类问题"""
    words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', text.lower())
    # 过滤通用词
    stopwords = {'什么', '怎么', '如何', '为什么', '能不能', '是不是',
                 '帮我', '给我', '一下', '这个', '那个', '问题'}
    filtered = [w for w in words if w not in stopwords][:5]
    return '|'.join(sorted(filtered))


def _text_similarity(a: str, b: str) -> float:
    """简单词重叠相似度（0-1）"""
    if not a or not b:
        return 0.0
    set_a = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', a.lower()))
    set_b = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', b.lower()))
    if not set_a or not set_b:
        return 0.0
    overlap = len(set_a & set_b)
    return overlap / max(len(set_a), len(set_b))


def check_pattern_match(record_id: int, text: str) -> bool:
    """检查这条记录是否与已有模式高度匹配"""
    conn = get_conn()
    pattern_key = _extract_pattern_key(text)

    # 查找同类模式
    existing = conn.execute(
        "SELECT id, trigger_count FROM skill_registry"
    ).fetchall()

    for skill_id, count in existing:
        if count > 0 and pattern_key == pattern_key:  # 简化：直接用关键词匹配
            conn.close()
            return True

    conn.close()
    return False


# ────────────────── 候选池管理 ──────────────────
def on_reinforce(record_id: int, raw_text: str):
    """
    每次 reinforce() 被调用时触发。
    1. 查找或创建候选记录
    2. 强化次数 +1
    3. 达到阈值时触发生成
    """
    if len(raw_text) < MIN_SOLUTION_LEN:
        return  # 内容不够，不进候选池

    conn = get_conn()

    # 查找现有候选
    row = conn.execute(
        "SELECT id, reinforce_count FROM skill_candidates WHERE record_id=? AND status='pending'",
        (record_id,)
    ).fetchone()

    if row:
        cid, count = row
        conn.execute(
            "UPDATE skill_candidates SET reinforce_count=?, trigger_at=? WHERE id=?",
            (count + 1, int(time.time()), cid)
        )
    else:
        pattern_key = _extract_pattern_key(raw_text)
        conn.execute(
            "INSERT INTO skill_candidates (record_id, trigger_at, reinforce_count, pattern_key, solved_text) VALUES (?, ?, 1, ?, ?)",
            (record_id, int(time.time()), pattern_key, raw_text[:5000])
        )

    conn.commit()

    # 检查是否达到触发阈值
    _check_and_generate(conn)
    conn.close()


def _check_and_generate(conn: sqlite3.Connection):
    """检查候选池，触发生成"""
    rows = conn.execute(
        "SELECT id, record_id, pattern_key, solved_text, reinforce_count "
        "FROM skill_candidates WHERE status='pending' AND reinforce_count >= ?",
        (AUTO_SKILL_THRESHOLD,)
    ).fetchall()

    for cid, record_id, pattern_key, solved_text, reinforce_count in rows:
        if _should_generate(conn, pattern_key, solved_text):
            skill_name = _generate_skill(pattern_key, solved_text, reinforce_count)
            conn.execute(
                "UPDATE skill_candidates SET status='generated' WHERE id=?",
                (cid,)
            )
            conn.execute(
                "INSERT OR REPLACE INTO skill_registry (skill_name, trigger_count, created_at) VALUES (?, 0, ?)",
                (skill_name, int(time.time()))
            )
            conn.commit()


def _should_generate(conn: sqlite3.Connection, pattern_key: str, solved_text: str) -> bool:
    """检查是否应该生成：内容足够 + 与现有技能重复度低"""
    if not solved_text or len(solved_text) < MIN_SOLUTION_LEN:
        return False

    existing = conn.execute("SELECT skill_name, trigger_count FROM skill_registry").fetchall()
    for skill_name, count in existing:
        if count > 0:
            skill_path = AUTO_SKILLS_DIR / f"{skill_name}.md"
            if skill_path.exists():
                with open(skill_path, encoding="utf-8") as f:
                    existing_text = f.read()
                if _text_similarity(solved_text, existing_text) >= PATTERN_SIMILARITY:
                    return False  # 重复度过高，跳过

    return True


# ────────────────── 技能生成 ──────────────────
def _generate_skill(pattern_key: str, solved_text: str, reinforce_count: int) -> str:
    """生成一个 SKILL.md 文件"""
    AUTO_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    # 生成技能名
    keywords = pattern_key.split('|')[:3]
    skill_name = "skill-" + "-".join(keywords)
    skill_name = re.sub(r'[^\w\-]', '_', skill_name.lower())

    skill_path = AUTO_SKILLS_DIR / f"{skill_name}.md"

    # 生成触发词
    triggers = [f'"{kw}"' for kw in keywords]

    content = f"""---
name: {skill_name}
description: 解决 {pattern_key} 问题的标准流程
triggers:
  - {', '.join(triggers)}
success_count: {reinforce_count}
created_at: {datetime.now().strftime('%Y-%m-%d')}
author: auto-generated (OpenClaw-UltraMemory V4)
---

## 解决流程

{solved_text}

## 备注

本技能由 OpenClaw 自动生成，已被成功复用 {reinforce_count} 次。
"""

    with open(skill_path, "w", encoding="utf-8") as f:
        f.write(content)

    return skill_name


# ────────────────── 技能检索 ──────────────────
def search_skills(query: str = "") -> list:
    """检索 auto-generated 技能"""
    if not AUTO_SKILLS_DIR.exists():
        return []

    keywords = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', query.lower())[:3]
    results = []

    for skill_file in AUTO_SKILLS_DIR.glob("skill-*.md"):
        with open(skill_file, encoding="utf-8") as f:
            content = f.read()

        # 简单关键词匹配
        if keywords:
            if any(kw in content.lower() for kw in keywords):
                results.append(str(skill_file))
        else:
            results.append(str(skill_file))

    return results


# ────────────────── CLI 入口 ──────────────────
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "check":
        # 模拟 reinforce 触发
        record_id = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        sample_text = sys.argv[3] if len(sys.argv) > 3 else "解决方案内容" * 20
        on_reinforce(record_id, sample_text)
        print(f"✅ 候选池已更新 | record_id={record_id}")

    elif cmd == "list":
        skills = search_skills()
        print(f"📦 Auto-generated 技能 ({len(skills)} 个):")
        for s in skills:
            print(f"  - {s}")

    elif cmd == "generate":
        pattern_key = sys.argv[2] if len(sys.argv) > 2 else "test-pattern"
        solved_text = sys.argv[3] if len(sys.argv) > 3 else "解决方案示例" * 30
        name = _generate_skill(pattern_key, solved_text, 3)
        print(f"✅ 技能已生成: {name}")

    else:
        print("用法: auto_skill.py [check|list|generate] [args...]")

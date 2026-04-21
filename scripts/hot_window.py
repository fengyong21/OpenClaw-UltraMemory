#!/usr/bin/env python3
"""
Claw Memory V3 - 热度钉扎滑动窗
核心逻辑：新数据进，旧数据出，好数据留，越用越聪明。

特性：
- 极简 4 字段单表，无复杂算法
- 原始文本无损归档到 Markdown，SQLite 只存索引
- Heat 强化 + 自然衰减（防老霸主垄断）
- 关键词初筛 + 热度排序双层检索
- instruction_hash 锚点防迷失（继承 V2）
- 新记录保护期 7 天内不参与淘汰
"""
import sqlite3
import time
import re
from pathlib import Path
from datetime import datetime

# ────────────────── 路径配置 ──────────────────
MEMORY_DIR = Path.home() / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "hot_window.db"
RAW_DIR = MEMORY_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ────────────────── 核心参数 ──────────────────
WINDOW_SIZE   = 1000      # 滑动窗口最大条数
PROTECT_SECS  = 604800    # 新记录保护期：7 天
DECAY_RATE    = 0.99      # 每次写入时对所有记录做一次自然衰减
HEAT_CAP      = 200       # 热度上限，防老霸主垄断
HEAT_FLOOR    = 1         # 热度下限
TOP_K         = 10        # 检索时返回 top-k 条


# ────────────────── 初始化 DB ──────────────────
def init_db(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,                       -- 父节点 ID，形成父子链（None=根节点）
            raw_link  TEXT    NOT NULL,              -- MD 文件路径
            heat      REAL    NOT NULL DEFAULT 1,    -- 热度（浮点，衰减用）
            timestamp INTEGER NOT NULL,               -- Unix 时间戳
            summary   TEXT                          -- 一句话摘要
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_heat     ON memory(heat DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ts      ON memory(timestamp)")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_anchor (
            session_id       TEXT PRIMARY KEY,
            instruction_text TEXT NOT NULL,
            instruction_hash TEXT NOT NULL,
            created_at       INTEGER NOT NULL
        )
    """)
    conn.commit()

    # 迁移旧数据：如果 parent_id 列不存在，则 ALTER TABLE 添加
    try:
        conn.execute("SELECT parent_id FROM memory LIMIT 1")
        # 列存在，索引可能也已存在，再次创建不会报错（IF NOT EXISTS）
        conn.execute("CREATE INDEX IF NOT EXISTS idx_parent ON memory(parent_id)")
    except sqlite3.OperationalError:
        # 旧表没有 parent_id 列，需要 ALTER TABLE + 索引
        conn.execute("ALTER TABLE memory ADD COLUMN parent_id INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_parent ON memory(parent_id)")
    conn.commit()


# ────────────────── 自然衰减 ──────────────────
def apply_decay(conn: sqlite3.Connection):
    """每次写入时对所有记录热度 × DECAY_RATE，并钳位到 [HEAT_FLOOR, HEAT_CAP]"""
    conn.execute(f"""
        UPDATE memory
        SET heat = MAX({HEAT_FLOOR}, MIN({HEAT_CAP}, heat * {DECAY_RATE}))
    """)


# ────────────────── 滑动淘汰 ──────────────────
def evict(conn: sqlite3.Connection):
    """超出窗口时，淘汰热度最低且已过保护期的记录"""
    count = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
    if count <= WINDOW_SIZE:
        return
    protect_ts = int(time.time()) - PROTECT_SECS
    conn.execute(f"""
        DELETE FROM memory
        WHERE id = (
            SELECT id FROM memory
            WHERE timestamp < {protect_ts}
            ORDER BY heat ASC, timestamp ASC
            LIMIT 1
        )
    """)


# ────────────────── 写入 ──────────────────
def write_memory(text: str, summary: str = "") -> int:
    """
    归档一段对话文本，构建父子链。
    1. 原文追加到 raw/YYYY-MM-DD.md（无损只追加）
    2. 查询最新一条记录的 id，作为新记录的 parent_id
    3. 自然衰减现有记录
    4. 插入新索引（heat=1，parent_id=上一条id）
    5. 淘汰超出窗口的最旧/最冷记录
    """
    today = datetime.now().strftime("%Y-%m-%d")
    raw_path = RAW_DIR / f"{today}.md"
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    with open(raw_path, "a", encoding="utf-8") as f:
        f.write(f"\n---\n## {datetime.now().isoformat()}\n{text}\n")

    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)

    # 查最新一条记录的 id，作为父节点（没有记录时为 None=根节点）
    last_id = conn.execute("SELECT MAX(id) FROM memory").fetchone()[0]

    apply_decay(conn)

    ts = int(time.time())
    cursor = conn.execute(
        "INSERT INTO memory (parent_id, raw_link, heat, timestamp, summary) VALUES (?, ?, 1, ?, ?)",
        (last_id, str(raw_path), ts, summary or text[:120])
    )
    new_id = cursor.lastrowid

    evict(conn)
    conn.commit()
    conn.close()

    return new_id


# ────────────────── 强化 ──────────────────
def reinforce(record_id: int, delta: float = 1.0):
    """记忆被成功使用时调用，热度 +delta，上限 HEAT_CAP"""
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)
    conn.execute(f"""
        UPDATE memory
        SET heat = MIN({HEAT_CAP}, heat + ?)
        WHERE id = ?
    """, (delta, record_id))
    conn.commit()
    conn.close()


# ────────────────── 检索 ──────────────────
def search(query: str = "", top_k: int = TOP_K) -> list:
    """
    双层检索：
    1. 关键词初筛（summary 或 raw_link 匹配）
    2. 热度降序 TOP-K
    如果关键词无匹配，降级为纯热度 TOP-K。
    """
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)

    keywords = _extract_keywords(query)
    rows = []

    if keywords:
        like_clauses = " OR ".join(["summary LIKE ?" for _ in keywords])
        params = [f"%{kw}%" for kw in keywords]
        rows = conn.execute(
            f"SELECT id, parent_id, raw_link, heat, timestamp, summary FROM memory "
            f"WHERE ({like_clauses}) ORDER BY heat DESC LIMIT ?",
            params + [top_k]
        ).fetchall()

    if not rows:
        rows = conn.execute(
            "SELECT id, parent_id, raw_link, heat, timestamp, summary FROM memory "
            "ORDER BY heat DESC LIMIT ?",
            (top_k,)
        ).fetchall()

    conn.close()

    results = []
    for row in rows:
        rec_id, parent_id, raw_link, heat, ts, summary = row
        raw_text = _read_raw(raw_link)
        results.append({
            "id": rec_id,
            "parent_id": parent_id,
            "heat": round(heat, 2),
            "summary": summary,
            "raw_text": raw_text,
            "timestamp": ts,
        })
    return results


# ────────────────── 链路回溯 ──────────────────
def trace_chain(record_id: int, depth: int = 5) -> list:
    """
    给定一条记忆的 id，顺 parent_id 链向上回溯指定深度。
    返回从根节点到当前节点的完整上下文链（有序列表）。
    用于解决"数据膨胀后逻辑断裂"的问题。

    返回格式：
    [
        {"id": 1, "parent_id": None,  "summary": "...", "raw_text": "...", "timestamp": ...},
        {"id": 2, "parent_id": 1,     "summary": "...", "raw_text": "...", "timestamp": ...},
        {"id": 3, "parent_id": 2,     "summary": "...", "raw_text": "...", "timestamp": ...},
    ]
    """
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)

    chain = []
    current_id = record_id

    for _ in range(depth):
        row = conn.execute(
            "SELECT id, parent_id, summary, raw_link, heat, timestamp "
            "FROM memory WHERE id = ?",
            (current_id,)
        ).fetchone()
        if not row:
            break

        rec_id, p_id, summary, raw_link, heat, ts = row
        raw_text = _read_raw(raw_link)
        chain.append({
            "id": rec_id,
            "parent_id": p_id,
            "summary": summary,
            "raw_text": raw_text,
            "heat": round(heat, 2),
            "timestamp": ts,
        })

        if p_id is None:
            # 遇到根节点，停止
            break
        current_id = p_id

    conn.close()
    # 反转：从根节点到当前节点
    return list(reversed(chain))


def get_session_context(session_id: str, depth: int = 5) -> list:
    """
    给定 session_id，取该会话链上热度和最高的记忆，向前回溯 depth 轮。
    用于会话恢复时快速拉取相关上下文。
    """
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)

    # 找该会话关联的记忆（取最热的一条作为入口）
    row = conn.execute(
        "SELECT id FROM memory ORDER BY heat DESC LIMIT 1"
    ).fetchone()

    conn.close()

    if not row:
        return []
    return trace_chain(row[0], depth=depth)


# ────────────────── 锚点（防迷失）──────────────────
def set_anchor(session_id: str, instruction_text: str):
    """在会话开始时存入原始指令锚点"""
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)
    anchor_hash = _simple_hash(instruction_text)
    conn.execute("""
        INSERT OR REPLACE INTO session_anchor
        (session_id, instruction_text, instruction_hash, created_at)
        VALUES (?, ?, ?, ?)
    """, (session_id, instruction_text[:500], anchor_hash, int(time.time())))
    conn.commit()
    conn.close()


def check_drift(current_text: str, session_id: str, threshold: int = 8) -> dict:
    """检测 Agent 是否偏离原始指令（字符级差异简版）"""
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT instruction_text, instruction_hash FROM session_anchor WHERE session_id=?",
        (session_id,)
    ).fetchone()
    conn.close()

    if not row:
        return {"is_drifting": False, "anchor_text": "", "distance": 0}

    anchor_text, anchor_hash = row
    current_hash = _simple_hash(current_text)
    dist = _hash_distance(current_hash, anchor_hash)

    return {
        "is_drifting": dist > threshold,
        "anchor_text": anchor_text,
        "distance": dist,
    }


# ────────────────── 工具函数 ──────────────────
def _extract_keywords(text: str) -> list:
    """提取长度 >= 2 的中文词和英文词"""
    words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', text)
    return list(set(words))[:5]  # 最多 5 个关键词


def _read_raw(path: str, max_chars: int = 600) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()[-max_chars:]  # 取末尾（最新一段）
    except FileNotFoundError:
        return ""


def _simple_hash(text: str) -> str:
    """极简字符频率哈希，用于锚点比对"""
    from collections import Counter
    freq = Counter(text.lower()[:200])
    return "".join(f"{k}{v}" for k, v in sorted(freq.items())[:16])


def _hash_distance(a: str, b: str) -> int:
    """两个哈希字符串的字符差异数"""
    return sum(1 for x, y in zip(a.ljust(32), b.ljust(32)) if x != y)


# ────────────────── CLI 入口 ──────────────────
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "write":
        text = sys.argv[2] if len(sys.argv) > 2 else ""
        rid = write_memory(text)
        print(f"✅ 归档成功 | id={rid}")

    elif cmd == "search":
        query = sys.argv[2] if len(sys.argv) > 2 else ""
        results = search(query)
        for i, r in enumerate(results, 1):
            print(f"[{i}] 热度:{r['heat']} | {r['summary'][:80]}")

    elif cmd == "reinforce":
        rid = int(sys.argv[2])
        reinforce(rid)
        print(f"✅ 热度强化 id={rid}")

    elif cmd == "anchor":
        session_id, text = sys.argv[2], sys.argv[3]
        set_anchor(session_id, text)
        print(f"✅ 锚点已设置 session={session_id}")

    elif cmd == "drift":
        text, session_id = sys.argv[2], sys.argv[3]
        result = check_drift(text, session_id)
        status = "⚠️ 跑偏" if result["is_drifting"] else "✅ 正常"
        print(f"{status} | 偏离距离:{result['distance']}")
        if result["is_drifting"]:
            print(f"[锚点提醒] 原始目标：{result['anchor_text'][:200]}")

    elif cmd == "chain":
        # 链路回溯：hot_window.py chain <record_id> [depth]
        rid = int(sys.argv[2])
        depth = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        chain = trace_chain(rid, depth=depth)
        print(f"🔗 链路回溯 depth={depth}，共 {len(chain)} 条\n")
        for i, node in enumerate(chain):
            marker = "← 当前" if i == len(chain) - 1 else ""
            print(f"[{i+1}] id={node['id']} | parent_id={node['parent_id']} | heat={node['heat']} {marker}")
            print(f"    摘要: {node['summary'][:80]}")
            print(f"    原文: {node['raw_text'][:200]}")
            print()

    elif cmd == "context":
        # 取最新一条记忆并回溯上下文链
        depth = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        conn = sqlite3.connect(str(DB_PATH))
        init_db(conn)
        top_row = conn.execute(
            "SELECT id FROM memory ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not top_row:
            print("无记忆记录")
        else:
            chain = trace_chain(top_row[0], depth=depth)
            print(f"📋 当前上下文链（最新记忆向前 {depth} 轮），共 {len(chain)} 条\n")
            for i, node in enumerate(chain):
                marker = "← 当前" if i == len(chain) - 1 else ""
                print(f"[{i+1}] id={node['id']} | parent_id={node['parent_id']} | heat={node['heat']} {marker}")
                print(f"    摘要: {node['summary'][:80]}")
                print(f"    原文: {node['raw_text'][:200]}")
                print()

    else:
        print("用法: hot_window.py [write|search|reinforce|anchor|drift|chain|context] [args...]")

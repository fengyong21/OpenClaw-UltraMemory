#!/usr/bin/env python3
"""
Claw Memory V5 - 精简 L2 + 进阶级 SimHash + 防迷失 + 技能生长
核心目标：小本本极小化，context window 装更多内容

L2 schema（精简版）：
  - simhash：多粒度指纹（2-gram + 3-gram + 4-gram），加权
  - raw_link：指向原材料文件，按需读取

删除的字段：
  - parent_id：编码进 raw 文件内容
  - summary：按需读 raw
  - heat：不维护热度
  - timestamp：从 raw 文件推导

三层检索：
  你输入 → is_task_input 判断 → 关键词初筛 → SimHash 语义搜
"""
import sqlite3
import time
import re
import json
import os
import shutil
from pathlib import Path
from datetime import datetime
from collections import Counter

# ────────────────── 路径配置 ──────────────────
MEMORY_DIR = Path.home() / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "hot_window.db"
RAW_DIR = MEMORY_DIR / "raw"
BACKUP_DIR = MEMORY_DIR / "backup_v4"
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ────────────────── 核心参数 ──────────────────
TOP_K = 10  # 检索时返回 top-k 条
HASH_BITS = 64  # SimHash 位数

# ────────────────── 停用词表（低权重）──────────────────
STOPWORDS = {
    '的', '了', '是', '在', '和', '有', '我', '你', '他', '她', '它',
    '这', '那', '个', '一', '不', '也', '就', '都', '要', '会', '可以',
    '没', '没有', '与', '及', '或', '但', '而', '所以', '因为', '如果',
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'can', 'to', 'of', 'in', 'for', 'on', 'with',
    'at', 'by', 'from', 'as', 'into', 'through', 'during', 'before', 'after',
}

# ────────────────── 初始化 DB（精简版 schema）─────────────────
def init_db(conn: sqlite3.Connection):
    """V5 精简 schema + session_anchor 防迷失"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory (
            simhash   TEXT PRIMARY KEY,  -- 多粒度加权 SimHash
            raw_link  TEXT NOT NULL,    -- 原材料文件路径
            meta      TEXT              -- JSON：parent_id, timestamp, session_id
        )
    """)
    # session_anchor 表：会话锚点，防迷失机制的核心
    conn.execute("""
        CREATE TABLE IF NOT EXISTS session_anchor (
            session_id TEXT PRIMARY KEY,     -- 会话唯一ID（UUID）
            instruction_text TEXT NOT NULL,  -- 入口指令原文
            instruction_hash TEXT NOT NULL, -- 入口指令指纹
            created_at INTEGER NOT NULL     -- 创建时间戳
        )
    """)
    # 旧表迁移：如果存在 V4 的旧表，重命名为 backup
    try:
        conn.execute("SELECT id FROM memory_v4 LIMIT 1")
        # 旧表存在，需要迁移
    except:
        pass
    conn.commit()


# ────────────────── 进阶级 SimHash：多粒度 + 加权 ──────────────────
def _tokenize(text: str) -> list:
    """
    分词：中文按字符，英文按空格分隔
    返回 [(token, weight), ...]
    """
    if not text:
        return []

    # 英文分词
    en_tokens = re.findall(r'[a-zA-Z]{2,}', text.lower())
    # 中文字符（连续2个以上）
    zh_tokens = re.findall(r'[\u4e00-\u9fff]{2,}', text)

    tokens = en_tokens + zh_tokens
    freq = Counter(tokens)

    # 加权：停用词低权重，稀有词高权重
    result = []
    total = len(tokens) or 1
    for token, count in freq.items():
        # TF 加权 + 停用词惩罚
        tf = count / total
        if token in STOPWORDS:
            weight = tf * 0.3  # 停用词降权
        else:
            weight = tf * 1.0  # 正常权重
        result.append((token, weight))

    return result


def _ngram_hash(text: str, n: int) -> int:
    """计算 n-gram 的 hash 值"""
    ngrams = [text[i:i+n] for i in range(max(0, len(text) - n + 1))]
    if not ngrams:
        return hash(text[:n] if text else "")
    # 取第一个 n-gram 的 hash
    return hash(ngrams[0])


def _compute_simhash(text: str) -> str:
    """
    V5 进阶级 SimHash：
    1. 多粒度：2-gram + 3-gram + 4-gram
    2. 加权：关键词高权重，停用词低权重
    3. 融合：加权平均各粒度的向量
    """
    if not text or len(text.strip()) < 2:
        return "0" * 16

    # 多粒度 n-gram
    ngrams_list = [
        [text[i:i+2] for i in range(max(0, len(text)-1))],  # 2-gram
        [text[i:i+3] for i in range(max(0, len(text)-2))],  # 3-gram
        [text[i:i+4] for i in range(max(0, len(text)-3))],  # 4-gram
    ]

    # 多粒度权重
    ngram_weights = [0.3, 0.4, 0.3]  # 2-gram:30%, 3-gram:40%, 4-gram:30%

    # 64位向量，初始为 0
    v = [0.0] * HASH_BITS

    # 对每个粒度
    for ngrams, ngram_weight in zip(ngrams_list, ngram_weights):
        if not ngrams:
            continue

        # 统计 n-gram 频率
        freq = Counter(ngrams)
        total = len(ngrams)

        for ngram, count in freq.items():
            # TF 加权
            tf = count / total

            # 停用词惩罚
            is_stop = any(stop in ngram for stop in STOPWORDS)
            stop_penalty = 0.3 if is_stop else 1.0

            weight = tf * ngram_weight * stop_penalty

            # hash 到 64 位向量
            h = hash(ngram)
            for i in range(HASH_BITS):
                if h >> i & 1:
                    v[i] += weight
                else:
                    v[i] -= weight

    # 生成指纹
    fingerprint = 0
    for i in range(HASH_BITS):
        if v[i] > 0:
            fingerprint |= (1 << i)

    return format(fingerprint, '016x')


def _hamming_distance(h1: str, h2: str) -> int:
    """计算两个十六进制 SimHash 之间的 Hamming 距离"""
    try:
        f1 = int(h1, 16) if h1 else 0
        f2 = int(h2, 16) if h2 else 0
        xor = f1 ^ f2
        return bin(xor).count('1')
    except (ValueError, TypeError):
        return HASH_BITS + 1  # 无效哈希，视为最远


# ────────────────── 任务判断 ──────────────────
_TASK_PATTERNS = [
    r'帮\w*做', r'帮\w*写', r'帮\w*改', r'帮\w*优化',
    r'帮我\w*', r'有个\w*问题', r'报错', r'错误', r'失败',
    r'不工作', r'失灵', r'修复', r'解决',
    r'实现\w*功能', r'实现\w*方案',
    r'怎么\w*', r'如何\w*',
    r'我想\w*', r'我要\w*',
    r'\w{2,}不\w{0,5}(了|起来|动)', r'\w{2,}跑不起',
    r'连接\w*失败', r'部署\w*失败', r'编译\w*失败',
]

_TASK_STOPWORDS = {'好', '恩', '可以', '谢谢', '不用', '行', '哦', '嗯', 'hi', 'hello', '你好', '嗨'}


def is_task_input(text: str) -> bool:
    """判断输入是否是任务/问题描述，触发主动记忆搜索"""
    text = text.strip()
    if len(text) < 5:
        return False
    if text.lower() in _TASK_STOPWORDS:
        return False
    for p in _TASK_PATTERNS:
        if re.search(p, text):
            return True
    return False


# ────────────────── 会话锚点（防迷失）─────────────────
import uuid

def start_session(instruction_text: str) -> dict:
    """
    开启新会话，注册锚点。
    用于新话题/新任务开始时调用，让 AI 永远知道"我从哪来"。

    返回：session_id, instruction_hash, created_at
    """
    import hashlib
    ts = int(time.time())
    session_id = str(uuid.uuid4())[:8]  # 短 UUID
    # 用内容 hash，而非 simhash（simhash 是语义指纹，这个是指令指纹）
    instruction_hash = hashlib.md5(instruction_text.encode()).hexdigest()[:16]

    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)
    conn.execute(
        "INSERT OR REPLACE INTO session_anchor (session_id, instruction_text, instruction_hash, created_at) VALUES (?, ?, ?, ?)",
        (session_id, instruction_text[:200], instruction_hash, ts)
    )
    conn.commit()
    conn.close()

    return {
        "session_id": session_id,
        "instruction_hash": instruction_hash,
        "created_at": ts,
    }


def get_current_session() -> dict:
    """
    获取当前活跃会话（最新创建的锚点）。
    如果没有，返回 None。
    """
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)
    row = conn.execute(
        "SELECT session_id, instruction_text, instruction_hash, created_at FROM session_anchor ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if not row:
        return None

    return {
        "session_id": row[0],
        "instruction_text": row[1],
        "instruction_hash": row[2],
        "created_at": row[3],
    }


def get_session_records(session_id: str = None) -> list:
    """
    获取指定会话的所有记忆记录。
    用于"回到这个会话"的上下文重建。
    """
    if not session_id:
        sess = get_current_session()
        if not sess:
            return []
        session_id = sess["session_id"]

    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)

    # 通过 meta JSON 中的 session_id 筛选
    rows = conn.execute(
        "SELECT simhash, raw_link, meta FROM memory WHERE JSON_EXTRACT(meta, '$.session_id') = ?",
        (session_id,)
    ).fetchall()
    conn.close()

    results = []
    for simhash, raw_link, meta_json in rows:
        meta = json.loads(meta_json) if meta_json else {}
        raw_text = _read_raw(raw_link)
        results.append({
            "simhash": simhash,
            "raw_link": raw_link,
            "raw_text": raw_text[:200],
            "timestamp": meta.get("timestamp", 0),
            "session_id": meta.get("session_id"),
        })

    return sorted(results, key=lambda x: x["timestamp"])


# ────────────────── 写入 ──────────────────
def write_memory(text: str, parent_id: int = None, session_id: str = None) -> dict:
    """
    归档一段对话文本。
    1. 原文追加到 raw/YYYY-MM-DD.md（无损只追加）
    2. 计算进阶级 SimHash（多粒度 + 加权）
    3. 写入精简索引（simhash + raw_link + meta）
    4. 自动关联当前 session（如果没有显式传入）
    """
    today = datetime.now().strftime("%Y-%m-%d")
    raw_path = RAW_DIR / f"{today}.md"

    ts = int(time.time())

    # 自动关联当前 session
    if not session_id:
        sess = get_current_session()
        if sess:
            session_id = sess["session_id"]

    meta = {
        "timestamp": ts,
        "parent_id": parent_id,
        "session_id": session_id,  # V5 新增：会话关联
    }

    # 追加到 raw 文件
    with open(raw_path, "a", encoding="utf-8") as f:
        entry = {
            "ts": ts,
            "parent_id": parent_id,
            "session_id": session_id,
            "text": text,
        }
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # 计算进阶级 SimHash
    sh = _compute_simhash(text)

    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)

    # 写入精简索引
    cursor = conn.execute(
        "INSERT OR REPLACE INTO memory (simhash, raw_link, meta) VALUES (?, ?, ?)",
        (sh, str(raw_path), json.dumps(meta, ensure_ascii=False))
    )
    conn.commit()
    conn.close()

    return {"simhash": sh, "raw_link": str(raw_path), "timestamp": ts}


# ────────────────── 检索 ──────────────────
def search(query: str = "", top_k: int = TOP_K, include_chain: bool = False, anchor_boost: bool = True) -> list:
    """
    三层检索（V5 精简版 + 锚点引导）：
    第1层：关键词初筛（兼容 V4/V5 raw 格式）
    第2层：SimHash 语义搜索（多粒度 + 加权，阈值放宽）
    第3层：锚点引导（同 session 记录获得额外分数）

    策略：关键词快速定位 → simhash 精排 → 锚点加权

    参数：
      query: 检索词
      top_k: 返回条数
      include_chain: 是否在结果中包含父节点上下文链
      anchor_boost: 是否启用锚点引导（同 session +5 分）
    """
    if not query.strip():
        return []

    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)

    # 获取当前 session（锚点引导用）
    current_session = get_current_session()
    current_session_id = current_session["session_id"] if current_session else None

    query_hash = _compute_simhash(query)
    keywords = _extract_keywords(query)
    threshold = 20  # 放宽阈值，短文本需要更宽松

    # 获取所有记录
    rows = conn.execute("SELECT simhash, raw_link, meta FROM memory").fetchall()
    conn.close()

    # 收集候选
    candidates = []
    for simhash, raw_link, meta_json in rows:
        meta = json.loads(meta_json) if meta_json else {}
        raw_text = _read_raw(raw_link)
        record_session_id = meta.get("session_id")

        # 计算相似度分数
        score = 0
        layer = None

        # 第1层：关键词匹配
        keyword_match = 0
        for kw in keywords:
            if kw.lower() in raw_text.lower():
                keyword_match += 1
        if keyword_match > 0:
            score += keyword_match * 10  # 关键词高权重
            layer = "keyword"

        # 第2层：SimHash 语义
        if simhash:
            dist = _hamming_distance(query_hash, simhash)
            if dist <= threshold:
                # 距离越小分数越高
                sim_score = (threshold - dist) / threshold
                score += sim_score * 5
                if layer is None:
                    layer = "simhash"

        # 第3层：锚点引导（如果启用）
        if anchor_boost and record_session_id and record_session_id == current_session_id:
            score += 5  # 同 session 额外加分
            layer = f"{layer}+anchor" if layer else "anchor"

        if score > 0:
            candidates.append({
                "simhash": simhash,
                "raw_link": raw_link,
                "distance": _hamming_distance(query_hash, simhash) if simhash else 999,
                "raw_text": raw_text,
                "timestamp": meta.get("timestamp", 0),
                "parent_id": meta.get("parent_id"),
                "session_id": record_session_id,
                "score": score,
                "layer": layer or "unknown",
            })

    # 按分数排序
    candidates.sort(key=lambda x: -x["score"])

    results = candidates[:top_k]

    # 添加锚点上下文（当前会话的入口指令）
    if current_session:
        for result in results:
            result["anchor_context"] = {
                "session_id": current_session["session_id"],
                "instruction_text": current_session["instruction_text"],
                "is_current_session": result.get("session_id") == current_session["session_id"],
            }

    # 可选：带上父节点上下文链
    if include_chain:
        for result in results:
            ts = result["timestamp"]
            chain = _trace_by_timestamp(ts, depth=3)
            if chain:
                result["chain"] = chain

    # ──── 技能生长联动 ────
    # 命中的记录如果质量够好，尝试生成技能
    for r in results[:3]:  # 只检查 top-3
        if r.get("score", 0) > 0 and len(r.get("raw_text", "")) > 200:
            check_skill_generation(
                record_id=r.get("timestamp", 0),
                raw_text=r.get("raw_text", ""),
                session_id=r.get("session_id")
            )

    return results


# ────────────────── 链路回溯 ──────────────────
def _trace_by_timestamp(timestamp: int, depth: int = 5) -> list:
    """
    通过 timestamp 回溯父节点链。
    返回从父节点到当前节点的上下文链。
    """
    chain = []

    # 获取这条记忆的 parent_id
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)
    row = conn.execute(
        "SELECT meta FROM memory WHERE JSON_EXTRACT(meta, '$.timestamp') = ?",
        (timestamp,)
    ).fetchone()
    conn.close()

    if not row:
        return []

    meta = json.loads(row[0]) if row[0] else {}
    current_parent = meta.get("parent_id")

    if current_parent is None:
        return []

    # 回溯 parent 链
    for _ in range(depth):
        if current_parent is None:
            break

        found = False
        for raw_file in RAW_DIR.glob("*.md"):
            content = open(raw_file, encoding="utf-8").read()

            # V5 JSON 格式
            if content.strip().startswith("{"):
                for line in content.split("\n"):
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("ts") == current_parent or entry.get("parent_id") == current_parent:
                            chain.append(entry)
                            current_parent = entry.get("parent_id")
                            found = True
                            break
                    except:
                        continue
            else:
                # V4 Markdown 格式：找对应的 timestamp
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if line.startswith("## ") and str(timestamp) in line:
                        # 找到了，回溯更早的
                        if i > 0 and lines[i-1].startswith("---"):
                            # 这是 V4 格式的迁移文件
                            pass
                        found = True
                        break

            if found:
                break

        if not found:
            break

    return chain


def trace_chain(record_id: int = None, depth: int = 5) -> list:
    """
    给定一条记忆，回溯 parent_id 链。
    兼容两种 raw 格式：V4 Markdown 和 V5 JSON
    """
    if record_id is None:
        # 取最新一条
        conn = sqlite3.connect(str(DB_PATH))
        init_db(conn)
        row = conn.execute(
            "SELECT raw_link, meta FROM memory ORDER BY JSON_EXTRACT(meta, '$.timestamp') DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            return []
        raw_link, meta_json = row
        meta = json.loads(meta_json) if meta_json else {}
        record_id = meta.get("parent_id")

    chain = []
    current_parent = record_id

    # 遍历所有 raw 文件找 parent 链
    for _ in range(depth):
        if current_parent is None:
            break

        found = False
        for raw_file in RAW_DIR.glob("*.md"):
            content = open(raw_file, encoding="utf-8").read()

            # 尝试 JSON 格式（V5）
            if content.strip().startswith("{"):
                for line in content.split("\n"):
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("ts") == current_parent or entry.get("parent_id") == current_parent:
                            chain.append(entry)
                            current_parent = entry.get("parent_id")
                            found = True
                            break
                    except:
                        continue

            # 尝试 Markdown 格式（V4）- 从 meta JSON 中获取 parent_id
            if not found and meta_json:
                meta = json.loads(meta_json)
                if meta.get("parent_id") == current_parent:
                    chain.append({"parent_id": meta.get("parent_id"), "text": content[:200]})
                    current_parent = meta.get("parent_id")
                    found = True

            if found:
                break

        if not found:
            break

    return list(reversed(chain))


# ────────────────── 工具函数 ──────────────────
def _read_raw(path: str, max_chars: int = 1000) -> str:
    """读取 raw 文件内容"""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
            # 取最后一条记录
            lines = content.strip().split("\n")
            if not lines:
                return ""

            # 尝试 JSON 格式（V5）
            if lines[-1].strip().startswith("{"):
                try:
                    last = json.loads(lines[-1])
                    return last.get("text", "")[-max_chars:]
                except:
                    pass

            # Markdown 格式（V4）：取最后一段
            # V4 格式: ## timestamp\ntext\n
            text_lines = []
            for line in reversed(lines):
                if line.startswith("## "):
                    break
                text_lines.insert(0, line)
            return "\n".join(text_lines).strip()[-max_chars:]
    except FileNotFoundError:
        return ""


def _extract_keywords(text: str) -> list:
    """提取关键词"""
    words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', text)
    return list(set(words))[:5]


# ────────────────── 迁移工具 ──────────────────
def migrate_from_v4():
    """
    从 V4 迁移到 V5：
    1. 备份旧数据库
    2. 读取 V4 数据
    3. 用新算法重新计算 simhash
    4. 生成 V5 精简 schema
    """
    # 1. 备份
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_db = BACKUP_DIR / f"hot_window_v4_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, backup_db)
        print(f"✅ 备份完成: {backup_db}")

    # 2. 读取 V4 数据
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            "SELECT id, parent_id, simhash, raw_link, heat, timestamp, summary FROM memory"
        ).fetchall()
    except sqlite3.OperationalError:
        print("⚠️ V4 数据不存在，跳过迁移")
        conn.close()
        return
    conn.close()

    if not rows:
        print("📭 无 V4 数据需要迁移")
        return

    # 3. 重新计算 simhash 并生成 V5 数据
    new_rows = []
    for row in rows:
        rec_id, parent_id, old_simhash, raw_link, heat, timestamp, summary = row

        # 读取 raw 内容重新计算 simhash
        raw_text = _read_raw_from_v4(raw_link)
        if raw_text:
            new_simhash = _compute_simhash(raw_text)
        else:
            new_simhash = old_simhash or "0" * 16

        meta = {
            "timestamp": timestamp,
            "parent_id": parent_id,
        }

        new_rows.append((new_simhash, raw_link, json.dumps(meta, ensure_ascii=False)))

    # 4. 删除旧表，创建新表，写入 V5 数据
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("DROP TABLE IF EXISTS memory_v4")
    conn.execute("ALTER TABLE memory TO memory_v4")  # 把旧表改名
    init_db(conn)  # 创建新表

    for simhash, raw_link, meta in new_rows:
        try:
            conn.execute(
                "INSERT INTO memory (simhash, raw_link, meta) VALUES (?, ?, ?)",
                (simhash, raw_link, meta)
            )
        except sqlite3.IntegrityError:
            # 重复 simhash，保留
            pass

    conn.commit()
    conn.close()

    print(f"✅ 迁移完成: {len(new_rows)} 条记录已转换到 V5 schema")


def _read_raw_from_v4(path: str) -> str:
    """V4 版本的 raw 文件读取"""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
            # V4 格式：标题 + 内容
            lines = content.split("\n")
            # 跳过标题，取正文
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


# ────────────────── 统计 ──────────────────
def stats():
    """查看当前记忆统计"""
    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn)
    count = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]

    # session_anchor 统计
    session_count = conn.execute("SELECT COUNT(*) FROM session_anchor").fetchone()[0]
    current = get_current_session()

    # 统计 raw 文件
    raw_count = len(list(RAW_DIR.glob("*.md"))) if RAW_DIR.exists() else 0

    conn.close()

    print(f"📊 记忆统计")
    print(f"  - 索引条数: {count}")
    print(f"  - raw 文件: {raw_count}")
    print(f"  - 会话锚点: {session_count} 个")
    if current:
        print(f"  - 当前会话: {current['session_id']}「{current['instruction_text'][:30]}...」")
    print(f"  - schema: simhash + raw_link + meta + session_id (V5)")


# ────────────────── CLI 入口 ──────────────────
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"

    if cmd == "write":
        text = sys.argv[2] if len(sys.argv) > 2 else input("输入记忆内容: ")
        parent_id = int(sys.argv[3]) if len(sys.argv) > 3 else None
        result = write_memory(text, parent_id)
        print(f"✅ 归档成功 | simhash={result['simhash'][:8]}...")

    elif cmd == "search":
        query = sys.argv[2] if len(sys.argv) > 2 else ""
        include_chain = "--chain" in sys.argv
        if not query:
            print("用法: hot_window.py search <查询> [--chain]")
            print("  --chain: 显示每条结果的父节点上下文链")
        else:
            results = search(query, include_chain=include_chain)
            print(f"🔍 检索「{query}」→ {len(results)} 条结果\n")
            for i, r in enumerate(results, 1):
                print(f"[{i}] {r['layer']} | 距离={r['distance']} | {r['raw_text'][:80]}...")
                if include_chain and r.get("chain"):
                    print(f"    └─ 上下文链 {len(r['chain'])} 条:")
                    for j, node in enumerate(r["chain"][:3]):
                        print(f"       [{j+1}] {node.get('text', '')[:50]}...")
                print()

    elif cmd == "chain":
        rid = int(sys.argv[2]) if len(sys.argv) > 2 else None
        depth = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        chain = trace_chain(rid, depth=depth)
        print(f"🔗 链路回溯 depth={depth}，共 {len(chain)} 条\n")
        for i, node in enumerate(chain):
            print(f"[{i+1}] parent={node.get('parent_id')} | {node.get('text', '')[:60]}...")

    elif cmd == "session":
        # session 管理
        sub = sys.argv[2] if len(sys.argv) > 2 else "current"
        if sub == "start":
            # 开启新会话
            instruction = sys.argv[3] if len(sys.argv) > 3 else input("入口指令: ")
            result = start_session(instruction)
            print(f"🆕 新会话开启: {result['session_id']}")
            print(f"   入口: {instruction[:50]}...")
            print(f"   指纹: {result['instruction_hash']}")
        elif sub == "current":
            # 显示当前会话
            sess = get_current_session()
            if sess:
                print(f"📍 当前会话: {sess['session_id']}")
                print(f"   入口: {sess['instruction_text']}")
                print(f"   创建于: {datetime.fromtimestamp(sess['created_at'])}")
                # 显示该会话的所有记录
                records = get_session_records(sess['session_id'])
                print(f"   记录数: {len(records)} 条")
            else:
                print("📭 当前没有活跃会话")
                print("   用法: hot_window.py session start <入口指令>")
        elif sub == "list":
            # 列出所有会话
            conn = sqlite3.connect(str(DB_PATH))
            init_db(conn)
            rows = conn.execute("SELECT session_id, instruction_text, created_at FROM session_anchor ORDER BY created_at DESC LIMIT 10").fetchall()
            conn.close()
            print(f"📜 最近 {len(rows)} 个会话:\n")
            for sid, text, ts in rows:
                print(f"  [{sid}] {datetime.fromtimestamp(ts)} | {text[:40]}...")
        else:
            print(f"未知子命令: {sub}")
            print("用法: session [start|current|list]")

    elif cmd == "migrate":
        print("🚀 开始 V4 → V5 迁移...")
        migrate_from_v4()

    elif cmd == "stats":
        stats()

    elif cmd == "help":
        print("""
Claw Memory V5 - 精简 L2 + 进阶级 SimHash + 防迷失锚点

用法:
  hot_window.py write <文本> [parent_id]   写入记忆（自动关联当前 session）
  hot_window.py search <查询> [--chain]   检索记忆（带锚点引导）
  hot_window.py chain [record_id] [depth]  链路回溯
  hot_window.py session start <指令>        开启新会话（防迷失）
  hot_window.py session current            显示当前会话
  hot_window.py session list               列出最近会话
  hot_window.py migrate                    V4 → V5 迁移
  hot_window.py stats                      统计信息
  hot_window.py help                       显示帮助
        """)

    else:
        print(f"未知命令: {cmd}")
        print("用法: hot_window.py [write|search|chain|migrate|stats|help]")

# ────────────────── 技能生长联动（草稿版）─────────────────
# 后续优化方向：
# - 质量打分（长度/代码块/关键词）
# - 锚点验证（多轮会话才生成）
# - 草稿模式（用户确认后才激活）

def check_skill_generation(record_id: int, raw_text: str, session_id: str = None):
    """
    检查是否应该生成技能（草稿版）。
    当前只做基础检查：
    1. 文本长度 >= 200
    2. 有代码块（简单验证）
    3. 和现有 skill 不重复
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from auto_skill import on_reinforce, _text_similarity

        # 基础检查：长度 + 代码块
        if len(raw_text) < 200:
            return None
        if "```" not in raw_text and "def " not in raw_text and "class " not in raw_text:
            return None  # 没有代码/函数，可能不是技术方案

        on_reinforce(record_id, raw_text)
        return True
    except ImportError:
        # auto_skill 未安装，跳过
        return None

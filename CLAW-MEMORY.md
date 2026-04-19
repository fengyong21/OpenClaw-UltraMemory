# Claw 记忆优化方案 V2

## 升级说明

V1 → V2 核心升级点：

| 升级项 | V1 | V2 |
|--------|----|----|
| 检索方式 | 单条文摘匹配 | 链式上下文组装 |
| 结构连贯性 | 无 | Parent_ID 链表保证逻辑不断 |
| 防迷失机制 | 无 | 原始指令哈希锚点 |
| 检索深度 | 单条 | 回溯 N 轮链路 |
| 概念定位 | 数据仓库 | 知识图谱 |

---

## 一、定位与铁律

### 核心定位

将 Claw 的记忆体系从"靠系统压缩"升级为"主动管理三层记忆"，在极小存储/算力约束下实现：

- **无限历史**：对话永久归档，存储不膨胀
- **瞬时召回**：毫秒级从历史中捞相关上下文
- **零打扰**：后台静默运行，不弹窗不打断自动化
- **结构连贯**：通过 Parent_ID 链表保证逻辑链不断裂

### 铁律（绝对禁止）

| 维度 | 要求 | 禁忌 |
|------|------|------|
| 数据 | 无限膨胀 | ❌ 禁止删除、覆盖历史记录 |
| 存储 | 极小 | ❌ 禁止向量数据库（Milvus/Pinecone） |
| 算力 | 极小 | ❌ 禁止复杂神经网络推理 |
| 速度 | 瞬时调用 | ❌ 禁止线性扫描 |
| 连贯性 | 结构不丢失 | ❌ 禁止逻辑断裂 |
| 移植 | 可嫁接 | ❌ 禁止锁定特定设备 |

---

## 二、架构：三层记忆金字塔

```
┌──────────────────────────────────────────────┐
│              User / MCP Client               │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│               OpenClaw Core                  │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐ │
│  │Hot Layer │  │Warm Layer  │  │Cold Layer│ │
│  │(Context) │  │(SQL+Index) │  │(Archive) │ │
│  │  极速响应 │  │  极小算力   │  │  无限存储 │ │
│  └──────────┘  └───────────┘  └──────────┘ │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│          Local Storage (SQLite + Files)       │
└──────────────────────────────────────────────┘
```

### 热数据层（Hot Layer）— 防迷失

- **载体**：Context Window + `MEMORY.md`
- **职责**：存放"当前任务目标"和"系统提示词"
- **关键设计**：保留"原始指令的哈希锚点"（instruction_hash），确保 Agent 不跑偏
- **触发**：每次启动或切换任务时，从热数据层读取锚点注入 Context

### 温数据层（Warm Layer）— 极小算力与结构

- **载体**：SQLite + SimHash
- **存储逻辑**：主键 = SimHash_64bit；关联键 = Parent_ID（指向前一轮的 SimHash）
- **结构连贯性**：通过 `Parent_ID` 建立前后文链式关系，检索时可沿链路回溯
- **算力消耗**：仅使用 XOR（异或运算）+ `ORDER BY Timestamp`，算力趋近于 0

### 冷数据层（Cold Layer）— 无损与移植

- **载体**：Markdown 原始文件 + MCP 协议
- **职责**：Markdown 负责人类可读原始数据；MCP 负责对外暴露接口
- **移植性**：SQLite 单文件 + 文本格式，打包即可带走

---

## 三、数据模型

### 3.1 SQLite Schema（V2，含 Parent_ID 链表）

```sql
-- 位置：~/.workbuddy/YYYYMMDDHHmmss/.workbuddy/memory/simhash.db

CREATE TABLE memory_index (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    simhash          INTEGER NOT NULL,              -- 64-bit 指纹（主键指纹）
    parent_id        INTEGER,                        -- 上一轮对话的 simhash，形成链表
    instruction_hash INTEGER NOT NULL,               -- 原始指令哈希锚点，防 Agent 跑偏
    hamming_key      TEXT NOT NULL,                 -- XOR 聚类键（前 16-bit）
    date             TEXT NOT NULL,                 -- 归档日期 YYYY-MM-DD
    session_id       TEXT NOT NULL,                -- 会话唯一 ID（跨天连续追踪）
    source_file      TEXT NOT NULL,                 -- 原始文件路径
    summary          TEXT,                          -- AI 生成的一句话摘要（≤ 140 字）
    created_at       TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_hamming_key ON memory_index(hamming_key);
CREATE INDEX idx_simhash ON memory_index(simhash);
CREATE INDEX idx_parent_id ON memory_index(parent_id);      -- V2 新增：链表索引
CREATE INDEX idx_session_id ON memory_index(session_id);     -- V2 新增：会话索引
CREATE INDEX idx_instruction_hash ON memory_index(instruction_hash);  -- V2 新增：锚点索引

-- 防迷失：记录每个会话的原始指令哈希
CREATE TABLE session_anchor (
    session_id       TEXT PRIMARY KEY,
    instruction_text TEXT NOT NULL,                 -- 原始指令原文（完整保留）
    instruction_hash INTEGER NOT NULL,               -- 原始指令的 SHA-256 哈希
    created_at       TEXT DEFAULT (datetime('now'))
);
```

### 3.2 原始文件存储

```
~/.workbuddy/YYYYMMDDHHmmss/.workbuddy/memory/
├── simhash.db                    # 指纹索引 + 链表（极小）
├── raw/
│   ├── 2026-04-01.md            # 原始对话归档
│   ├── 2026-04-02.md
│   └── ...
└── session/
    └── {session_id}/            # 按会话 ID 分目录
        ├── meta.json             # 元数据（instruction_text + anchor）
        └── messages.mdl          # 该会话的原始消息流
```

### 3.3 归档触发条件

满足任一即归档：
- 对话轮次 >= 15
- 上下文利用率 >= 70%
- 单次会话超过 30 分钟
- 用户明确说"记住这个"

---

## 四、SimHash 算法（精简版，算力极小）

### 4.1 指纹计算（写入时）

```python
# scripts/simhash_core.py

import hashlib
import re

def compute_simhash(text: str, width: int = 64) -> int:
    """
    计算文本的 SimHash 指纹。
    算力要求：MD5 + 位运算，无神经网络，纯 CPU。
    """
    words = [w for w in re.split(r'\W+', text.lower()) if len(w) >= 2]
    v = [0] * width
    for word in words:
        h = int(hashlib.md5(word.encode()).hexdigest(), 16) % (2 ** width)
        for i in range(width):
            bit = (h >> i) & 1
            v[i] += 1 if bit else -1

    fingerprint = 0
    for i in range(width):
        if v[i] >= 0:
            fingerprint |= (1 << i)
    return fingerprint


def compute_instruction_hash(text: str) -> int:
    """
    计算原始指令的 SHA-256 哈希，作为防迷失锚点。
    用于检测 Agent 是否跑偏到与原始目标无关的方向。
    """
    return int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2 ** 128)


def hamming_key(simhash: int, bits: int = 16) -> str:
    """
    提取 simhash 的前 N 位作为聚类键，
    检索时只需在同一 key 内做 XOR，搜索空间从 2^64 → 2^N。
    """
    return format(simhash >> (64 - bits), f'0{bits}b')


def hamming_distance(a: int, b: int) -> int:
    """计算两个 64-bit 整数的 Hamming 距离（XOR + popcount）"""
    return (a ^ b).bit_count()
```

---

## 五、执行流程（V2）

### 5.1 写入（归档）流程

```
1. 触发 → 对话结束或达到阈值（轮次/时间/利用率）
2. 计算 → 计算当前对话的 SimHash 指纹
3. 查询 → 查上一轮的 Simhash，填入 Parent_ID（链表关联）
4. 锚定 → 记录本次会话的原始指令哈希（instruction_hash）
5. 存储 → 写入 SQLite（指纹 + Parent_ID + instruction_hash）
           + 备份原始文本到 Markdown 分片
```

### 5.2 读取（召回）流程

```
1. 查询 → 用户输入问题
2. 匹配 → 计算问题的 SimHash，快速匹配（Hamming <= 3）
3. 组装 → 命中后：
   - 沿 Parent_ID 链表向前回溯最多 5 轮（可配置）
   - 读取每轮的 source_file，提取相关段落
   - 顺路检查 instruction_hash，若与当前 session 锚点一致则优先注入
4. 注入 → 将组装好的上下文注入 Context Window
          格式：[相关历史 {n}] ...（不暴露文件名和内部 ID）
```

### 5.3 防迷失检测

```
每次响应前：
1. 提取当前 Context 中的用户原始指令
2. 计算 instruction_hash，与 session_anchor 表中的锚点比对
3. 若 Hamming 距离 > 阈值，说明 Agent 已跑偏
4. 触发"拉回"：将锚点指令摘要注入 Context，提醒当前目标
```

---

## 六、关键脚本（V2）

### 6.1 archive.py（归档脚本，含 Parent_ID 链路）

```python
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
    parent_id = get_last_simhash(session_id)  # 链表关联
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

    # 写入主索引（含 Parent_ID 链表）
    conn.execute(
        """INSERT INTO memory_index
           (simhash, parent_id, instruction_hash, hamming_key, date, session_id, source_file, summary)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (sim, parent_id, instr_hash, key, today, session_id, source_file, summary)
    )

    # 更新/插入会话锚点
    conn.execute(
        """INSERT OR REPLACE INTO session_anchor (session_id, instruction_text, instruction_hash)
           VALUES (?, ?, ?)""",
        (session_id, instruction_text, instr_hash)
    )

    conn.commit()
    conn.close()

    # 追加原文分片
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
```

### 6.2 inject.py（召回脚本，含链路回溯）

```python
#!/usr/bin/env python3
"""从历史中召回相关记忆（V2：沿 Parent_ID 链路回溯组装上下文）"""
import sys
import sqlite3
from pathlib import Path
from simhash_core import compute_simhash, hamming_distance, hamming_key

MEMORY_DIR = Path.home() / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "simhash.db"


def trace_chain(simhash: int, max_depth: int = 5) -> list:
    """
    沿 Parent_ID 链表回溯最多 max_depth 轮，
    返回从当前到最早一轮的所有 simhash 和 source_file。
    """
    chain = []
    current_hash = simhash
    conn = sqlite3.connect(str(DB_PATH))

    for _ in range(max_depth):
        row = conn.execute(
            "SELECT id, simhash, parent_id, source_file, summary, instruction_hash "
            "FROM memory_index WHERE simhash=?",
            (current_hash,)
        ).fetchone()
        if not row:
            break
        chain.append({
            "id": row[0],
            "simhash": row[1],
            "parent_id": row[2],
            "source_file": row[3],
            "summary": row[4],
            "instruction_hash": row[5],
        })
        if row[2] is None:  # 没有 parent，链表到头
            break
        current_hash = row[2]

    conn.close()
    return chain


def read_raw_text(source_file: str, max_chars: int = 800) -> str:
    """读取原文分片，过滤后取前 max_chars 字符"""
    try:
        with open(source_file, encoding="utf-8") as f:
            return f.read()[:max_chars]
    except FileNotFoundError:
        return ""


def recall(query: str, session_id: str = "", top_k: int = 3, threshold: int = 3, max_depth: int = 5) -> list:
    """
    召回主函数：
    1. 计算问题 SimHash，按 Hamming 距离匹配
    2. 命中后沿 Parent_ID 链路回溯 max_depth 轮
    3. 顺路检查 instruction_hash 与当前会话锚点是否一致
    4. 组装上下文返回
    """
    query_hash = compute_simhash(query)
    key = hamming_key(query_hash)

    # 获取当前会话的锚点哈希（用于判断是否跑偏）
    conn = sqlite3.connect(str(DB_PATH))
    current_anchor = conn.execute(
        "SELECT instruction_hash FROM session_anchor WHERE session_id=?",
        (session_id,)
    ).fetchone()
    current_anchor_hash = current_anchor[0] if current_anchor else None

    results = []

    # 优先在同一 hamming_key 内查找
    candidates = conn.execute(
        "SELECT simhash, source_file, summary, instruction_hash "
        "FROM memory_index WHERE hamming_key=? ORDER BY created_at DESC LIMIT 50",
        (key,)
    ).fetchall()

    for row in candidates:
        simhash, source_file, summary, instr_hash = row
        dist = hamming_distance(query_hash, simhash)
        if dist <= threshold:
            # 命中：沿链路回溯
            chain = trace_chain(simhash, max_depth)

            # 检查链路中是否有与当前锚点一致的历史（强相关）
            anchor_match = any(
                hamming_distance(c['instruction_hash'], current_anchor_hash) < 2
                for c in chain if current_anchor_hash
            )

            # 读取原文片段
            raw_text = read_raw_text(source_file)

            results.append({
                "distance": dist,
                "chain_depth": len(chain),
                "anchor_match": anchor_match,
                "summary": summary or raw_text[:200],
                "chain": chain,
                "raw_text": raw_text,
            })

            if len(results) >= top_k:
                break

    conn.close()

    # 无结果时，扩大到相邻 key
    if not results:
        for adj in adjacent_keys_of(key):
            candidates = conn.execute(
                "SELECT simhash, source_file, summary, instruction_hash "
                "FROM memory_index WHERE hamming_key=? ORDER BY created_at DESC LIMIT 20",
                (adj,)
            ).fetchall()
            for row in candidates:
                simhash, source_file, summary, instr_hash = row
                dist = hamming_distance(query_hash, simhash)
                if dist <= threshold + 2:
                    chain = trace_chain(simhash, max_depth)
                    raw_text = read_raw_text(source_file)
                    results.append({
                        "distance": dist,
                        "chain_depth": len(chain),
                        "anchor_match": False,
                        "summary": summary or raw_text[:200],
                        "chain": chain,
                        "raw_text": raw_text,
                    })
                    if len(results) >= top_k:
                        break
            if len(results) >= top_k:
                break

    return sorted(results, key=lambda x: (not x['anchor_match'], x['distance']))

if __name__ == "__main__":
    session_id = sys.argv[2] if len(sys.argv) > 2 else ""
    recalls = recall(sys.argv[1], session_id)
    for i, r in enumerate(recalls, 1):
        print(f"[相关历史 {i}]（链路深度: {r['chain_depth']}）")
        print(r['summary'])
        print()
```

### 6.3 drift_detect.py（防迷失检测）

```python
#!/usr/bin/env python3
"""检测 Agent 是否跑偏，若 instruction_hash 与锚点偏离则触发拉回"""
import sys
import sqlite3
from pathlib import Path
from simhash_core import compute_instruction_hash, hamming_distance

MEMORY_DIR = Path.home() / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "simhash.db"


def check_drift(current_instruction: str, session_id: str, threshold: int = 8) -> dict:
    """
    比对当前指令与 session 锚点。
    若 hamming_distance > threshold，说明 Agent 已偏离原始目标。
    返回: {is_drifting: bool, anchor_text: str, distance: int}
    """
    current_hash = compute_instruction_hash(current_instruction)
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT instruction_text, instruction_hash FROM session_anchor WHERE session_id=?",
        (session_id,)
    ).fetchone()
    conn.close()

    if not row:
        return {"is_drifting": False, "anchor_text": "", "distance": 0}

    anchor_text, anchor_hash = row
    dist = hamming_distance(current_hash, anchor_hash)

    return {
        "is_drifting": dist > threshold,
        "anchor_text": anchor_text,
        "distance": dist,
    }


def get_anchor_hint(session_id: str) -> str:
    """返回锚点指令摘要，用于注入 Context 拉回 Agent"""
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT instruction_text FROM session_anchor WHERE session_id=?",
        (session_id,)
    ).fetchone()
    conn.close()

    if row:
        return f"[锚点提醒] 当前会话的原始目标是：{row[0][:200]}"
    return ""
```

### 6.4 migrate.py（历史迁移）

```python
#!/usr/bin/env python3
"""V1 → V2 迁移：将旧版 simhash.db 升级为含 Parent_ID 链表的新版"""
import sqlite3
from pathlib import Path
from simhash_core import compute_simhash, compute_instruction_hash, hamming_key

MEMORY_DIR = Path.home() / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "simhash.db"


def migrate():
    """对历史 Markdown 文件批量计算 SimHash，建立 V2 链表索引"""
    conn = sqlite3.connect(str(DB_PATH))

    # 升级表结构
    conn.execute("""CREATE TABLE IF NOT EXISTS memory_index_v2 (
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

    # 迁移旧数据（parent_id 和 instruction_hash 设为 NULL，后续补填）
    conn.execute(
        """INSERT INTO memory_index_v2
           (simhash, parent_id, instruction_hash, hamming_key, date, session_id, source_file, summary, created_at)
           SELECT simhash, NULL, 0, hamming_key, date, date, source_file, summary, created_at
           FROM memory_index""",
    )

    # 按时间排序，补填 parent_id（链表关联）
    rows = conn.execute(
        "SELECT id, simhash FROM memory_index_v2 ORDER BY created_at ASC"
    ).fetchall()

    for i in range(1, len(rows)):
        conn.execute(
            "UPDATE memory_index_v2 SET parent_id=? WHERE id=?",
            (rows[i - 1][1], rows[i][0])
        )

    # 删除旧表，重命名新表
    conn.execute("DROP TABLE memory_index")
    conn.execute("ALTER TABLE memory_index_v2 RENAME TO memory_index")

    conn.commit()
    print(f"迁移完成：{len(rows)} 条记录，已建立 Parent_ID 链表")

if __name__ == "__main__":
    migrate()
```

---

## 七、Skill 集成（V2）

### 7.1 SKILL.md

```markdown
---
name: claw-memory
version: 2.0.0
description: Claw 记忆优化 V2。触发：对话超过 15 轮、上下文利用率超 70%、"回忆"、"之前"、"历史上"、检测到跑偏
triggers:
  - "回忆"
  - "之前我们"
  - "历史上"
  - "查一下"
  - "还记得"
  - 对话轮次 >= 15
  - 上下文利用率 >= 70%
  - instruction_hash 偏离锚点
---

# Claw Memory Skill V2

## 执行逻辑

### Phase 1: 热数据保持
- 读取 MEMORY.md（灵魂记忆）注入 Context
- 检查 session_anchor，获取原始指令哈希锚点
- 不主动压缩当前任务相关上下文

### Phase 2: 温数据归档（满足触发条件时执行）
1. 调用 `scripts/archive.py`：
   - 计算当前对话的 SimHash 指纹
   - 查询上一轮 SimHash，填入 Parent_ID（链表关联）
   - 记录原始指令的 instruction_hash（防迷失锚点）
   - 写入 `simhash.db`（指纹 + Parent_ID + instruction_hash）
   - 追加原始对话到 `raw/YYYY-MM-DD.md`
2. 后台静默执行，不弹窗，不打断

### Phase 3: 记忆召回（满足召回触发时执行）
1. 用户提问中含召回关键词，或上下文利用率高
2. 调用 `scripts/inject.py`：
   - 计算问题 SimHash
   - 在 `simhash.db` 中检索 Hamming 距离 <= 3 的记录
   - 命中后沿 Parent_ID 链路回溯最多 5 轮
   - 顺路检查 instruction_hash 与当前会话锚点是否一致
   - 组装完整上下文注入 Context
3. 展示摘要，不暴露内部文件名和 ID

### Phase 4: 防迷失检测（每次响应前执行）
1. 调用 `scripts/drift_detect.py`：
   - 比对当前 Context 中的指令与 session_anchor
   - 若 hamming_distance > 8，判定为跑偏
2. 触发拉回：将锚点指令摘要注入 Context

## 存储约束
- SQLite 只存指纹（8 byte/条）+ 元数据 + 链表指针（8 byte），不存全文
- 原文按 YYYY-MM-DD 分片存 Markdown
- 单条归档：对话 >= 15 轮 或 >= 30 分钟
- 历史数据禁止删除、覆盖
```

---

## 八、与 capability-evolver 的协同

```
用户行为数据 ──归档──> claw-memory V2 (温数据层)
                              │
                              ▼ 提取用户习惯偏好 + 跑偏记录
                         MEMORY.md 更新
                              │
                              ▼ 触发
                    capability-evolver 进化
```

---

## 九、部署检查清单

- [ ] 在 `~/.workbuddy/skills/claw-memory/` 建立目录结构
- [ ] 替换 `scripts/simhash_core.py` → V2（含 `compute_instruction_hash`）
- [ ] 替换 `scripts/archive.py` → V2（含 Parent_ID 链表）
- [ ] 替换 `scripts/inject.py` → V2（含链路回溯）
- [ ] 新增 `scripts/drift_detect.py` → 防迷失检测
- [ ] 执行 `python scripts/migrate.py`（一次性 V1 → V2 迁移）
- [ ] 验证归档：`python scripts/archive.py "测试对话内容" "原始目标" "test-session" ""`
- [ ] 验证召回：`python scripts/inject.py "之前我们做了什么" "test-session"`
- [ ] 验证防迷失：`python scripts/drift_detect.py "跑偏的指令" "test-session"`
- [ ] 配置触发阈值（按需调整 max_depth、threshold）

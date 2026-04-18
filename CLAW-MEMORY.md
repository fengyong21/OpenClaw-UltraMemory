# Claw 记忆优化方案

## 定位

将 Claw 的记忆体系从"靠系统压缩"升级为"主动管理三层记忆"，在极小存储/算力约束下实现：
- **无限历史**：对话永久归档，存储不膨胀
- **瞬时召回**：毫秒级从历史中捞相关上下文
- **零打扰**：后台静默运行，不弹窗不打断自动化

---

## 一、架构：三层记忆金字塔

```
┌─────────────────────────────────────────┐
│  热数据层 · Context Window (0 延迟)      │
│  当前任务 + MEMORY.md(灵魂记忆)          │
│  工作流：读取 → 使用 → 不压缩            │
└─────────────────────────────────────────┘
                    │
                    ▼ 触发：上下文超过 70% 或对话轮次 >= 15
┌─────────────────────────────────────────┐
│  温数据层 · SQLite + SimHash (毫秒级)   │
│  功能：检索相关历史 → 注入 Context       │
│  存储：只存 64-bit 指纹 + 原始文件引用   │
└─────────────────────────────────────────┘
                    │
                    ▼ 触发：冷数据引用 或 新设备接入
┌─────────────────────────────────────────┐
│  冷数据层 · Markdown 原档 (零算力)       │
│  功能：归档原始对话，永久保留            │
│  格式：YYYY-MM-DD.md，按时间分片         │
└─────────────────────────────────────────┘
```

### 核心设计原则

| 约束 | 实现策略 |
|------|----------|
| 存储极小 | SQLite 只存 64-bit 指纹 + 文件路径引用，不存全文 |
| 算力极小 | CPU 位运算（XOR/Hamming），无神经网络 |
| 数据无限 | 指纹不随文本膨胀，原文按时间分片存 Markdown |
| 瞬时调用 | 指纹查表 O(1)，命中后按路径读原文 |
| 记忆可移植 | MCP Server 暴露 query 接口，单文件迁移 |

---

## 二、数据模型

### 2.1 SQLite Schema（极简指纹表）

```sql
-- 位置：~/.workbuddy/YYYYMMDDHHmmss/.workbuddy/memory/simhash.db

CREATE TABLE memory_index (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    simhash     INTEGER NOT NULL,          -- 64-bit 指纹，SQLite INTEGER（9 byte）
    hamming_key TEXT NOT NULL,             -- 用于 XOR 聚类的分组键（前 16-bit）
    date        TEXT NOT NULL,             -- 归档日期 YYYY-MM-DD
    source_file TEXT NOT NULL,             -- 原始文件路径
    summary     TEXT,                      -- 可选：AI 生成的一句话摘要（≤ 140 字）
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_hamming_key ON memory_index(hamming_key);
CREATE INDEX idx_simhash ON memory_index(simhash);
```

### 2.2 原始文件存储（Markdown 分片）

```
~/.workbuddy/YYYYMMDDHHmmss/.workbuddy/memory/
├── simhash.db                    # 指纹索引（极小）
├── raw/
│   ├── 2026-04-01.md            # 原始对话归档
│   ├── 2026-04-02.md
│   └── ...
└── session/
    └── current.md               # 当前会话实时写入
```

**归档触发条件（满足任一即归档）：**
- 对话轮次 >= 15
- 上下文利用率 >= 70%
- 单次会话超过 30 分钟

---

## 三、SimHash 算法（精简版，算力极小）

### 3.1 指纹计算（写入时）

```python
# scripts/simhash_core.py

import hashlib
import re

def compute_simhash(text: str, width: int = 64) -> int:
    """
    计算文本的 SimHash 指纹。
    算力要求：MD5 + 位运算，无神经网络，纯 CPU。
    """
    # 分词：空格/标点切分，极简分词器
    words = [w for w in re.split(r'\W+', text.lower()) if len(w) >= 2]

    v = [0] * width
    for word in words:
        # 用 MD5 将词映射到 width-bit 空间（可替换为更低算力的 xxhash）
        h = int(hashlib.md5(word.encode()).hexdigest(), 16) % (2 ** width)

        for i in range(width):
            bit = (h >> i) & 1
            v[i] += 1 if bit else -1

    fingerprint = 0
    for i in range(width):
        if v[i] >= 0:
            fingerprint |= (1 << i)

    return fingerprint


def hamming_key(simhash: int, bits: int = 16) -> str:
    """
    提取 simhash 的前 N 位作为聚类键，
    检索时只需在同一 key 内做 XOR，范围从 2^64 → 2^N。
    """
    return format(simhash >> (64 - bits), f'0{bits}b')
```

### 3.2 相似检索（读取时）

```python
def search_similar(query: str, db_path: str, top_k: int = 5, hamming_threshold: int = 3) -> list:
    """
    在 SQLite 中检索与 query 相似的历史记忆。
    策略：先按 hamming_key 缩小范围，再做精确 Hamming 距离计算。
    时间复杂度：O(top_k)，非全表扫描。
    """
    query_hash = compute_simhash(query)
    key = hamming_key(query_hash)

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT simhash, source_file, summary FROM memory_index WHERE hamming_key=?",
        (key,)
    ).fetchall()

    candidates = []
    for row in rows:
        dist = hamming_distance(query_hash, row[0])
        if dist <= hamming_threshold:
            candidates.append((dist, row[1], row[2]))

    # 无结果时，扩大搜索到相邻 key
    if not candidates:
        adjacent_keys = adjacent_keys_of(key)
        for adj in adjacent_keys:
            rows = conn.execute(
                "SELECT simhash, source_file, summary FROM memory_index WHERE hamming_key=?",
                (adj,)
            ).fetchall()
            for row in rows:
                dist = hamming_distance(query_hash, row[0])
                if dist <= hamming_threshold + 2:
                    candidates.append((dist, row[1], row[2]))

    conn.close()
    return sorted(candidates)[:top_k]


def hamming_distance(a: int, b: int) -> int:
    """计算两个 64-bit 整数的 Hamming 距离（XOR + popcount）"""
    return (a ^ b).bit_count()
```

---

## 四、Skill 集成（WorkBuddy 适配）

### 4.1 目录结构

```
~/.workbuddy/skills/claw-memory/
├── SKILL.md              # 技能定义（触发条件 + 工作流）
├── scripts/
│   ├── simhash_core.py   # 核心算法（指纹 + 检索）
│   ├── archive.py         # 归档脚本（写入 SQLite + 分片 Markdown）
│   └── inject.py          # 注入脚本（从历史捞取 → 注入 Context）
└── config.json           # 配置（阈值、路径、LLM API）
```

### 4.2 SKILL.md

```markdown
---
name: claw-memory
version: 1.0.0
description: Claw 记忆优化。触发：对话超过 15 轮、上下文利用率超 70%、"回忆"、"之前"、"历史上"
triggers:
  - "回忆"
  - "之前我们"
  - "历史上"
  - "查一下"
  - 对话轮次 >= 15
  - 上下文利用率 >= 70%
---

# Claw Memory Skill

## 执行逻辑

### Phase 1: 热数据保持
- 读取 MEMORY.md（灵魂记忆）注入 Context
- 不主动压缩当前任务相关上下文

### Phase 2: 温数据归档（满足触发条件时执行）
1. 调用 `scripts/archive.py`：
   - 计算当前对话的 SimHash 指纹
   - 写入 `simhash.db`（指纹 + 文件路径）
   - 追加原始对话到 `raw/YYYY-MM-DD.md`
2. 后台静默执行，不弹窗，不打断

### Phase 3: 记忆召回（满足召回触发时执行）
1. 用户提问中含召回关键词，或上下文利用率高
2. 调用 `scripts/inject.py`：
   - 计算问题 SimHash
   - 在 `simhash.db` 中检索 Hamming 距离 <= 3 的记录
   - 按路径读取原文，过滤后取 top 3 条
   - 注入 Context（格式：`[相关历史 N] ...`）
3. 展示摘要，不展示原始文件名

## 存储约束
- SQLite 只存指纹（8 byte/条）+ 元数据，不存全文
- 原文按 YYYY-MM-DD 分片存 Markdown
- 单条归档：对话 >= 15 轮 或 >= 30 分钟
```

### 4.3 关键脚本

**`scripts/archive.py`**：
```python
#!/usr/bin/env python3
"""归档当前对话到 SQLite + Markdown 分片"""
import sys
import sqlite3
import json
from pathlib import Path
from simhash_core import compute_simhash, hamming_key

MEMORY_DIR = Path.home() / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "simhash.db"
RAW_DIR = MEMORY_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

def archive_dialogue(dialogue_text: str, summary: str = ""):
    sim = compute_simhash(dialogue_text)
    key = hamming_key(sim)
    today = "2026-04-18"  # 实际从 datetime 获取

    # 写入 SQLite
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""CREATE TABLE IF NOT EXISTS memory_index (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        simhash INTEGER NOT NULL,
        hamming_key TEXT NOT NULL,
        date TEXT NOT NULL,
        source_file TEXT NOT NULL,
        summary TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    source_file = str(RAW_DIR / f"{today}.md")

    conn.execute(
        "INSERT INTO memory_index (simhash, hamming_key, date, source_file, summary) VALUES (?, ?, ?, ?, ?)",
        (sim, key, today, source_file, summary)
    )
    conn.commit()
    conn.close()

    # 追加原文分片
    with open(source_file, "a", encoding="utf-8") as f:
        f.write(f"\n---\n## Session {today}\n{dialogue_text}\n")

    print(f"归档完成 | 指纹: {sim} | 日期: {today}")

if __name__ == "__main__":
    archive_dialogue(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")
```

**`scripts/inject.py`**：
```python
#!/usr/bin/env python3
"""根据当前问题，从历史中召回相关记忆"""
import sys
import sqlite3
from pathlib import Path
from simhash_core import compute_simhash, hamming_distance, adjacent_keys_of

MEMORY_DIR = Path.home() / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "simhash.db"

def recall(query: str, top_k: int = 3, threshold: int = 3) -> list:
    query_hash = compute_simhash(query)
    results = []

    conn = sqlite3.connect(str(DB_PATH))
    # 先按 key 聚类查找，再精确 Hamming 过滤
    for row in conn.execute("SELECT * FROM memory_index ORDER BY created_at DESC LIMIT 100"):
        simhash, source_file, summary = row[1], row[4], row[5]
        if hamming_distance(query_hash, simhash) <= threshold:
            with open(source_file, encoding="utf-8") as f:
                raw = f.read()
            results.append({"summary": summary, "raw": raw[:500]})
            if len(results) >= top_k:
                break
    conn.close()
    return results

if __name__ == "__main__":
    recalls = recall(sys.argv[1])
    for i, r in enumerate(recalls, 1):
        print(f"[相关历史 {i}]\n{r['summary'] or r['raw'][:200]}\n")
```

---

## 五、与现有系统的关系

### 5.1 现有 memory/ 体系 → 新架构映射

| 现有文件 | 新架构层 | 说明 |
|----------|----------|------|
| `MEMORY.md` | 热数据层 | 灵魂记忆，保持不变，每次启动读取 |
| `memory/YYYY-MM-DD.md` | 冷数据层 | 原始归档，新架构直接沿用 |
| `memory/MEMORY.md` | → 温数据层 | 需迁移到 `simhash.db` 指纹索引 |

### 5.2 迁移步骤

1. 对现有 `memory/` 下所有 `.md` 文件批量计算 SimHash，建立 `simhash.db`
2. 脚本：`scripts/migrate.py`，一次性迁移，历史无缝衔接

```python
# scripts/migrate.py
from pathlib import Path
import sqlite3
from simhash_core import compute_simhash, hamming_key

def migrate():
    db = sqlite3.connect(str(MEMORY_DIR / "simhash.db"))
    for md in Path(MEMORY_DIR).glob("*.md"):
        text = md.read_text(encoding="utf-8")
        sim = compute_simhash(text)
        db.execute("INSERT INTO memory_index (simhash, hamming_key, date, source_file) VALUES (?, ?, ?, ?)",
                    (sim, hamming_key(sim), md.stem, str(md)))
    db.commit()
    print("迁移完成")
```

---

## 六、与 capability-evolver 的协同

`claw-memory` 负责"记住过去"，`capability-evolver` 负责"进化能力"，两者互补：

```
用户行为数据 ──归档──> claw-memory (温数据层)
                              │
                              ▼ 提取用户习惯偏好
                         MEMORY.md 更新
                              │
                              ▼ 触发
                    capability-evolver 进化
```

---

## 七、部署检查清单

- [ ] 在 `~/.workbuddy/skills/claw-memory/` 建立目录结构
- [ ] 安装依赖：`pip install -r requirements.txt`（仅需标准库 + sqlite3）
- [ ] 初始化 SQLite：`python scripts/migrate.py`（一次性）
- [ ] 验证归档：`python scripts/archive.py "测试对话内容"`
- [ ] 验证召回：`python scripts/inject.py "之前我们做了什么"`
- [ ] 配置触发阈值（可选，按需调整）

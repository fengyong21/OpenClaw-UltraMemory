# 🦞 OpenClaw-UltraMemory V5

> 热度钉扎滑动窗 + 父子链上下文 + 自动技能生长 + **session_anchor 防迷失**

## 核心定位

AI 的外骨骼记忆系统。在 1000+ 条记忆里不迷失，随时能找到"我从哪来、这是哪个会话"。

**设计原则**：
- **L1 原始数据**：永不修改，只追加，可溯源
- **L2 索引数据**：极小化 ~30 bytes/条（比 V4 减少 80%）
- **检索**：大容量 + 高速度 + 可溯源

---

## 架构一览

```
用户输入
  ↓
┌──────────────────────┐
│ 第1层：关键词初筛      │  快速定位候选（+10分）
└──────────────────────┘
  ↓
┌──────────────────────┐
│ 第2层：SimHash 语义    │  多粒度 2+3+4-gram（+5分）
└──────────────────────┘
  ↓
┌──────────────────────┐
│ 第3层：锚点引导        │  同 session 优先（+5分）
└──────────────────────┘
  ↓
TOP-K → 排序输出
```

**为什么三层？** SimHash 对短文本、同义词、跨会话语义有硬伤，三层互补才能保证召回质量。

---

## 数据结构

### L1：原始数据（`raw/`）
只追加不修改，每条记录完整保留：
```json
{"ts": 1745289000, "parent_id": null, "session_id": "b6beb4eb", "text": "记忆内容..."}
```

### L2：索引（SQLite）
~30 bytes/条，极小化：
```sql
memory(
  simhash   TEXT PRIMARY KEY,  -- 64位语义指纹
  raw_link  TEXT NOT NULL,    -- 指向 raw/ 文件
  meta      TEXT              -- JSON: parent_id, timestamp, session_id
)

session_anchor(
  session_id       TEXT PRIMARY KEY,  -- 会话唯一ID
  instruction_text TEXT NOT NULL,     -- 入口指令
  instruction_hash TEXT NOT NULL,    -- 指令指纹
  created_at       INTEGER NOT NULL
)
```

---

## 快速开始

```bash
cd /Users/mac/WorkBuddy/Claw/claw-memory

# 开启新会话（防迷失机制）
python scripts/hot_window.py session start "优化 L2 加工层"

# 写入记忆（自动关联当前 session）
python scripts/hot_window.py write "开始实现 session_anchor 防迷失"

# 检索（三层混合）
python scripts/hot_window.py search "session anchor"

# 链路回溯（沿 parent_id 展开上下文）
python scripts/hot_window.py chain <id> 5

# 查看统计
python scripts/hot_window.py stats
```

---

## 核心 API

### 会话管理
```python
start_session(instruction_text)     # 开启新会话，返回 {session_id, instruction_hash}
get_current_session()               # 获取当前活跃会话
get_session_records(session_id)     # 获取会话所有记录
```

### 记忆操作
```python
write_memory(text, parent_id=None)  # 归档，自动带上 session_id
search(query, top_k=10)             # 三层检索
trace_chain(record_id, depth=5)     # 父子链回溯
```

---

## 防迷失机制

```
新会话开始
  ↓
start_session("优化 claw-memory")
  ↓
写入记忆 → 自动带上 session_id
  ↓
检索时 → 同 session 记录优先
  ↓
AI 输出："这是你在「优化 claw-memory」会话里的第 3 条记录"
```

---

## 文件结构

```
claw-memory/
├── scripts/
│   ├── hot_window.py      # 核心实现（V5 + session_anchor）
│   ├── migrate_v5.py      # V4 → V5 迁移
│   └── auto_skill.py      # 技能自动生长（草稿）
├── raw/                   # 原始数据（只追加）
├── docs/
│   └── V5_COMPLETE.md     # 完整设计文档
├── install.sh             # 安装
├── export.sh / import.sh  # 数据导出/导入
└── README.md
```

---

## 版本历史

| 版本 | 核心功能 | 状态 |
|------|---------|------|
| V1 | SimHash + Hamming 距离检索 | ✅ 完成 |
| V2 | Parent_ID 链路回溯 | ✅ 完成 |
| V3/V4 | 热度钉扎滑动窗 | ✅ 完成 |
| **V5** | **精简 L2 schema + 多粒度 simhash** | ✅ 当前 |
| — | session_anchor 防迷失 | ✅ 刚完成 |
| — | auto_skill 生长联动 | ⚠️ 草稿 |

---

## 安装

```bash
./install.sh
```

迁移（V4 → V5）：
```bash
python scripts/migrate_v5.py
```

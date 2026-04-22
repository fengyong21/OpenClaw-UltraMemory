# Claw Memory V5 - 完整梳理

> 最后更新：2026-04-22

---

## 一、项目定位

**目标**：AI 记忆系统，让 AI 在 1000+ 条记忆里不迷失，随时能找到"我从哪来"

**核心约束**：
- L1 原始数据：永不修改，只追加
- L2 加工数据：极小化（~30 bytes/条）
- 检索：大容量 + 高速度 + 可溯源

---

## 二、架构演进

| 版本 | 核心功能 | 状态 |
|------|---------|------|
| V1 | SimHash + Hamming 距离检索 | ✅ 完成 |
| V2 | Parent_ID 链路回溯 | ✅ 完成 |
| V3/V4 | 热度钉扎滑动窗 | ⚠️ 已精简（去掉热度） |
| **V5** | **精简 L2 schema + 进阶级 simhash** | ✅ 当前 |
| session_anchor | 防迷失锚点机制 | ✅ 刚完成 |

---

## 三、数据结构

### L1：原始数据（raw/）
```
raw/2026-04-22.md
```
格式：JSON Lines，每行一条记录
```json
{"ts": 1745289000, "parent_id": null, "session_id": "b6beb4eb", "text": "记忆内容..."}
```
**原则**：只追加，不修改，不删除

### L2：索引数据（SQLite）
```sql
CREATE TABLE memory (
    simhash   TEXT PRIMARY KEY,  -- 64位十六进制语义指纹（16字节）
    raw_link  TEXT NOT NULL,    -- raw 文件路径
    meta      TEXT               -- JSON：parent_id, timestamp, session_id
);

CREATE TABLE session_anchor (
    session_id TEXT PRIMARY KEY,     -- 会话唯一ID
    instruction_text TEXT NOT NULL,  -- 入口指令
    instruction_hash TEXT NOT NULL, -- 指令指纹
    created_at INTEGER NOT NULL     -- 创建时间
);
```

**L2 大小**：~30 bytes/条（比 V4 的 ~150 bytes 减少 80%）

---

## 四、检索流程（三层）

```
用户查询
    ↓
┌─────────────────────────────┐
│ 第1层：关键词初筛            │
│ 提取 query 的关键词，快速   │
│ 定位候选记录（权重 +10）    │
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│ 第2层：SimHash 语义搜索      │
│ 多粒度（2+3+4-gram）+ 加权   │
│ Hamming 距离 ≤ 20 命中      │
│ （权重 +5）                 │
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│ 第3层：锚点引导（session）   │
│ 同 session 记录额外 +5 分   │
│ 让 AI 知道"这是哪个会话的"   │
└─────────────────────────────┘
    ↓
按分数排序 → 返回 TOP-K
```

---

## 五、核心函数

### 会话管理
```python
start_session(instruction_text)
  → 开启新会话，返回 {session_id, instruction_hash, created_at}

get_current_session()
  → 获取当前活跃会话

get_session_records(session_id)
  → 获取指定会话的所有记录
```

### 记忆操作
```python
write_memory(text, parent_id=None, session_id=None)
  → 归档记忆，自动关联当前 session

search(query, top_k=10, include_chain=False, anchor_boost=True)
  → 三层检索，返回匹配结果列表

trace_chain(record_id=None, depth=5)
  → 沿 parent_id 链路回溯
```

---

## 六、防迷失机制

```
新会话开始
    ↓
start_session("优化 L2 加工层")
    ↓
写入记忆 → 自动带上 session_id
    ↓
检索时 → 同 session 记录优先
    ↓
AI 输出："这是你在「优化 L2 加工层」会话里的第 3 条记录"
```

---

## 七、使用方式

```bash
# 开启新会话（防迷失）
python hot_window.py session start "优化 claw-memory"

# 写入记忆（自动关联当前 session）
python hot_window.py write "开始实现 session_anchor"

# 检索（锚点引导）
python hot_window.py search "session anchor"

# 查看统计
python hot_window.py stats

# 链路回溯
python hot_window.py chain
```

---

## 八、待优化方向

| 方向 | 状态 | 说明 |
|------|------|------|
| auto_skill | ⚠️ 代码存在，0 个技能 | 技能自动生长 |
| 批量迁移 | ✅ 已完成 | migrate_v5.py |
| 导出/导入 | ✅ 已完成 | export.sh / import.sh |

---

## 九、文件清单

```
claw-memory/
├── scripts/
│   ├── hot_window.py      # 核心实现（V5 + session_anchor）
│   ├── migrate_v5.py      # V4 → V5 迁移
│   ├── auto_skill.py      # 技能自动生长（未激活）
│   └── child_agent.py     # 子 Agent（未激活）
├── SKILL.md               # Skill 调用文档
├── README.md              # 项目说明
├── ARTICLE.md             # 设计理念
├── CLAW-MEMORY.md         # 详细文档
├── install.sh             # 安装脚本
├── export.sh / import.sh  # 数据迁移
└── raw/                   # 原始数据（只追加）
```

---

## 十、设计原则

1. **数据不可篡改**：L1 原始数据永不修改
2. **极小化索引**：L2 只保留必要字段（simhash + raw_link + meta）
3. **可溯源**：每条记忆知道"属于哪个会话、从哪条衍生"
4. **渐进式检索**：关键词 → 语义 → 锚点，三层过滤

---
name: claw-memory
version: 3.0.0
description: Claw 记忆优化 V3。热度钉扎滑动窗，极简算力，越用越聪明。触发：对话超过 15 轮、"回忆"、"之前"、"还记得"
triggers:
  - "回忆"
  - "之前我们"
  - "历史上"
  - "还记得"
  - "查一下"
  - 对话轮次 >= 15
  - 上下文利用率 >= 70%
  - 检测到 Agent 跑偏
---

# Claw Memory Skill V3

## 设计哲学

> 新数据进，旧数据出，好数据留，越用越聪明。

摒弃 V2 的 SimHash 复杂算法，用一张极简单表 + 热度机制搞定全部逻辑。

## 版本对比

| 特性 | V1 | V2 (SimHash) | V3 (HotWindow) |
|------|----|-------------|----------------|
| 存储结构 | 5列 | 8列+2索引 | **4列单表** |
| 检索算法 | TOP-K | Hamming距离 | **关键词+热度** |
| 越用越聪明 | ❌ | ❌ | **✅ Heat强化** |
| 自然衰减 | ❌ | ❌ | **✅ ×0.99** |
| 防迷失锚点 | ❌ | ✅ | **✅ 继承** |
| 核心代码量 | 150行 | 400行 | **<100行** |

## SQLite 单表结构

```sql
CREATE TABLE memory (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_link  TEXT    NOT NULL,   -- MD文件路径（无损原文）
    heat      REAL    DEFAULT 1,  -- 热度（浮点，支持衰减）
    timestamp INTEGER NOT NULL,   -- Unix时间戳
    summary   TEXT                -- 一句话摘要
);
```

## 运行逻辑

### Phase 1: 写入（滑动+衰减）
1. 原文追加到 `raw/YYYY-MM-DD.md`（无损只追加，永不修改）
2. 现有所有记录热度 × 0.99（自然衰减，防老霸主）
3. 插入新记录（heat=1，保护期30分钟内不参与淘汰）
4. 若总数 > 1000：删除热度最低且已过保护期的记录

### Phase 2: 检索（双层过滤）
1. 关键词初筛：提取问题中的中英文关键词，匹配 summary
2. 热度排序：取 TOP-10
3. 无关键词命中时，降级为纯热度 TOP-10

### Phase 3: 强化（越用越聪明）
- 记忆被成功使用时调用 `reinforce(id)`
- Heat +1，上限 200（防垄断）

### Phase 4: 防迷失（继承 V2）
- 会话开始时调用 `set_anchor(session_id, instruction)`
- 每次响应前调用 `check_drift()`
- 偏离距离 > 8 时，将原始目标注入 Context

## 核心文件

```
scripts/hot_window.py    # 全部逻辑，<100行
```

## CLI 用法

```bash
python hot_window.py write "对话内容"           # 归档
python hot_window.py search "查询关键词"         # 检索
python hot_window.py reinforce 42               # 强化 id=42
python hot_window.py anchor sess1 "原始目标"    # 设锚点
python hot_window.py drift "当前内容" sess1     # 检测跑偏
```

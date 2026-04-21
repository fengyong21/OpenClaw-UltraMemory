---
name: claw-memory
description: OpenClaw 极限记忆系统。触发词：记忆、之前、回忆、上下文、历史记录、链路回溯、父子链、热度。自动执行写入和检索，无需用户手动触发。
---

# Claw-Memory Skill

## 核心功能

当用户提到"记忆"、"之前"、"回忆"、"上下文"等关键词时，自动调用。

## 调用方式

```bash
cd /Users/mac/WorkBuddy/Claw/claw-memory

# 写入记忆
python3 scripts/hot_window.py write "对话内容摘要"

# 检索记忆
python3 scripts/hot_window.py search "关键词"

# 链路回溯（给定记录 id）
python3 scripts/hot_window.py chain <record_id> [depth]

# 获取最热记忆的上下文链
python3 scripts/hot_window.py context [depth]

# 强化记忆热度
python3 scripts/hot_window.py reinforce <record_id>

# 会话锚点防迷失
python3 scripts/hot_window.py anchor <session_id> "原始目标"

# 检测是否跑偏
python3 scripts/hot_window.py drift "当前内容" <session_id>
```

## 架构

- **raw/**：原始数据，只追加不可篡改
- **hot_window.db**：索引数据库（id, parent_id, raw_link, heat, timestamp, summary）
- **parent_id**：父子链，解决数据膨胀后逻辑断裂
- **heat**：热度，强化递增，衰减递减，淘汰最低

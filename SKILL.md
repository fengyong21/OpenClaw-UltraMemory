---
name: claw-memory
description: OpenClaw-UltraMemory 记忆系统。触发词：记忆、回忆、归档、历史记录、自动技能、子任务并行。V4 融合 Hermes 自动技能生长机制。
triggers:
  - "记忆"
  - "回忆"
  - "之前"
  - "历史"
  - "归档"
  - "自动生成技能"
  - "子任务并行"
  - "子Agent"
  - "多步骤任务"
---

# Claw Memory V4

OpenClaw 极限记忆插件，V4 版本融合 Hermes Agent 自动技能生长机制。

## 核心能力

1. **热度钉扎滑动窗**：1000 条上限，7 天保护期，自然衰减
2. **自动技能生成**：同类问题解决 3 次 → 自动写 SKILL.md
3. **子智能体并行**：多步骤任务自动拆分并发执行
4. **防迷失锚点**：instruction_hash 检测偏离自动拉回

## 脚本说明

| 脚本 | 作用 |
|------|------|
| `hot_window.py` | 核心：写入/检索/强化/衰减 |
| `auto_skill.py` | 自动：从成功经验中生成新技能 |
| `child_agent.py` | 并行：多步骤任务拆分执行 |
| `migrate.py` | 迁移：历史数据批量灌入 |

## CLI 用法

```bash
# 记忆写入
python3 scripts/hot_window.py write "这是一段重要对话"

# 记忆检索
python3 scripts/hot_window.py search "之前关于什么的讨论"

# 强化（被命中后调用）
python3 scripts/hot_window.py reinforce 1

# 设置锚点
python3 scripts/hot_window.py anchor "session-001" "原始任务"

# 检测跑偏
python3 scripts/hot_window.py drift "当前内容" "session-001"

# 查看自动技能
python3 scripts/auto_skill.py list

# 任务规划（子Agent）
python3 scripts/child_agent.py plan "帮我部署 GEO 项目"

# 并行执行
python3 scripts/child_agent.py run "帮我部署 GEO 项目"
```

## 协同

- `capability-evolver`：大方向基因优化（1-2 周/次）
- `auto_skill.py`：技能层面小颗粒生长（每次成功触发）
- `child_agent.py`：并行执行，减少上下文消耗

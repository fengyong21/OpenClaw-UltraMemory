---
name: claw-memory
version: 1.0.0
description: Claw 极限记忆优化方案。触发：对话超过 15 轮、上下文利用率超 70%、"回忆"、"之前"、"历史上"、"查一下"
triggers:
  - "回忆"
  - "之前我们"
  - "历史上"
  - "查一下"
  - 对话轮次 >= 15
  - 上下文利用率 >= 70%
  - 单次会话 >= 30 分钟
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

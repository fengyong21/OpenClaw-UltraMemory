---
name: claw-memory
version: 2.0.0
description: Claw 记忆优化 V2。触发：对话超过 15 轮、上下文利用率超 70%、"回忆"、"之前"、"历史上"
triggers:
  - "回忆"
  - "之前我们"
  - "历史上"
  - "查一下"
  - "还记得"
  - 对话轮次 >= 15
  - 上下文利用率 >= 70%
  - 检测到跑偏
---

# Claw Memory Skill V2

## 核心升级

V2 相比 V1 新增三大特性：
1. **Parent_ID 链表**：检索时沿链路回溯，逻辑连贯不断裂
2. **instruction_hash 锚点**：防 Agent 跑偏，永远记得原始目标
3. **drift_detect.py**：每次响应前自动检测是否偏离锚点

## 执行逻辑

### Phase 1: 热数据保持
- 读取 MEMORY.md（灵魂记忆）注入 Context
- 检查 session_anchor，获取原始指令哈希锚点
- 不主动压缩当前任务相关上下文

### Phase 2: 温数据归档（满足触发条件时执行）
1. 调用 `scripts/archive.py`：
   - 计算 SimHash + 查询上一轮 parent_id
   - 记录 instruction_hash（防迷失锚点）
   - 写入 `simhash.db`（含链表指针）
   - 追加原文到 `raw/YYYY-MM-DD.md`
2. 后台静默执行，不弹窗，不打断

### Phase 3: 记忆召回（满足召回触发时执行）
1. 用户提问中含召回关键词，或上下文利用率高
2. 调用 `scripts/inject.py`：
   - 计算问题 SimHash
   - Hamming 距离匹配 + Parent_ID 链路回溯最多 5 轮
   - 顺路检查 instruction_hash 与当前锚点是否一致
   - 组装上下文注入 Context

### Phase 4: 防迷失检测（每次响应前执行）
1. 调用 `scripts/drift_detect.py`：
   - 比对当前 Context 指令与 session_anchor
   - 若 hamming_distance > 8，判定为跑偏
2. 触发拉回：将锚点摘要注入 Context

## 存储约束
- SQLite 只存指纹 + 元数据 + 链表指针，不存全文
- 原文按 YYYY-MM-DD 分片存 Markdown
- 历史数据禁止删除、覆盖

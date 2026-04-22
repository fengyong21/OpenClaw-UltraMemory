---
name: claw-memory
description: OpenClaw 极限记忆系统。触发词：记忆、之前、回忆、上下文、历史记录、链路回溯、父子链。自动执行写入和检索，无需用户手动触发。
---

# Claw-Memory V5 Skill

## 核心目标

**小本本极小化**：让 context window 装更多内容，AI 越来越聪明。

## 核心功能

### 主动检索（不等你说"之前"）

当用户输入**任务描述或问题描述**时，在回答之前自动执行检索，主动带入上下文：

**触发条件（is_task_input）：**

| 类型 | 示例 |
|------|------|
| 帮我做/写/改/优化 | "帮我做个网站"、"帮我优化检索" |
| 描述问题 | "有个问题报错"、"Mac上跑不起来了" |
| 描述失败 | "数据库连接失败"、"部署失败" |
| 请求方案 | "怎么解决"、"如何实现" |
| 目标表达 | "我想实现XX功能"、"我要做个XX" |

**两层检索流程：**

```
你输入 → 判断任务 → 🔍关键词初筛 → 🧠SimHash语义精排 → 带着结果回答
```

| 层 | 触发条件 | 作用 |
|----|---------|------|
| 🔍 关键词 | raw 内容包含关键词 | 快速定位候选 |
| 🧠 SimHash | 关键词命中不足时 | 语义相近也能搜到（Hamming距离≤20） |

---

## 调用方式

```bash
cd /Users/mac/WorkBuddy/Claw/claw-memory/scripts

# 写入记忆（自动计算多粒度SimHash + 关联parent_id）
python3 hot_window.py write "对话内容"

# 检索记忆（关键词 + SimHash 混合检索）
python3 hot_window.py search "关键词或问题描述"

# 检索记忆（带上下文链）
python3 hot_window.py search "关键词" --chain

# 链路回溯（追溯父子链）
python3 hot_window.py chain [record_id] [depth]

# 查看统计
python3 hot_window.py stats

# V4 → V5 迁移
python3 migrate_v5.py
```

---

## 架构

```
L1 原始数据（raw/）     → 只追加不可篡改
L2 索引数据（V5精简）    → simhash + raw_link + meta

hot_window.db (V5 schema):
  ├── simhash             → 多粒度加权SimHash（2+3+4-gram）
  ├── raw_link            → 原文路径
  └── meta                → JSON编码（timestamp, parent_id）
```

**精简版 L2 schema 优势：**
- 每条 ~30 bytes（原来 ~150 bytes）
- context window 能装更多索引
- simhash 检索 + 关键词兜底，召回率更高

---

## 核心参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| TOP_K | 10 | 检索返回条数 |
| SIMHASH_THRESHOLD | 20 | SimHash Hamming距离阈值（放宽应对短文本） |
| HASH_BITS | 64 | SimHash 位数 |

---

## 联动流程

```
用户输入 → is_task_input() 判断是否任务
         → 如果是：search() 检索相关记忆
         → 读取 raw 文件补全内容
         → 追溯 parent_id 链获取完整上下文
         → 带着上下文回答

新对话 → write_memory() 归档
        → 计算多粒度 SimHash
        → 写入 L2 索引
        → 关联 parent_id 形成链路
```

**search + trace_chain 组合**：
- 检索命中后，自动追溯父节点上下文
- 返回完整对话链，不只是单条记忆
- 解决"断章取义"问题

---

## 迁移

- 旧数据备份：`~/.workbuddy/memory/backup_v4/`
- 迁移脚本：`migrate_v5.py`
- 迁移后：旧数据用新算法重新计算 simhash

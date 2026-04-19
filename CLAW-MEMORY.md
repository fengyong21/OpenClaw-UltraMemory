# 🦞 OpenClaw-UltraMemory V4

基于**热度钉扎滑动窗**的记忆系统，融合 **Hermes Agent** 的自动技能生长机制。

> V1 SimHash 检索 → V2 Parent_ID 链路 → V3 热度滑动窗 → **V4 自动技能生长**

---

## 铁律：不可篡改 + 行为可追溯

本项目与 Hermes 的根本区别在于**信任模型**：

| | Hermes | OpenClaw-UltraMemory |
|--|--------|---------------------|
| 信任模型 | 隐式信任框架 | 零信任，代码自证 |
| 原始数据 | 框架可读写 | 追加只读，框架无权修改 |
| 行为审计 | 黑箱，依赖官方 | 全透明，明文脚本可逐行审查 |
| 追责能力 | 出问题找官方 | 行为自证，完整回溯 |

**两条铁律，永远不可打破：**

1. **原始数据不可篡改**：`raw/` 目录下的 `.md` 文件只追加，不修改、不覆盖、不删除。任何脚本都无权触碰已写入内容。
2. **行为全程可审计**：所有操作通过明文 Python 脚本执行，用户可随时审查代码验证行为。迁移时只需迁移 `raw/` + `*.db`，新环境可完整重建。

---

## 核心升级：Hermes 借鉴点

### 1. 自动技能生成（Auto-Skill）

Hermes 最强的机制：解决新问题后**自动写可复用技能文档**。

V4 实现：当同一类问题被成功解决 3 次以上，自动生成 `~/.workbuddy/skills/auto-generated/` 下的 SKILL.md。

```
遇到新问题 → 成功解决 → 记录解决方案 → 第3次同类问题触发生成 SKILL.md
```

**判断标准**：
- 关键词匹配度 >= 80%（基于 summary SimHash）
- 连续 3 次 `reinforce` 强化（同一条记忆被命中 3 次）
- 解决方案长度 >= 200 字（有实质内容）

### 2. 子智能体并行（Child Agent）

多步骤任务拆成子 Agent 并行跑，结果汇总，零额外上下文消耗。

```
主任务：帮我部署 GEO 项目到 Sealos
    ├── 子Agent-1：构建 Docker 镜像
    ├── 子Agent-2：配置 Kubernetes YAML
    └── 子Agent-3：更新 GitHub Actions
        ↓ 并行执行
    主Agent：汇总结果，完成部署
```

**触发条件**：
- 单次任务涉及 >= 3 个独立子步骤
- 子步骤之间无强依赖关系

### 3. 统一技能格式（agentskills.io 兼容）

所有 auto-generated 技能遵循 Hermes 开放标准：

```markdown
---
name: skill-deploy-geos-to-sealos
description: 部署 GEO 项目到 Sealos Cloud 的完整流程
triggers:
  - "部署 GEO"
  - "sealos 部署"
  - "docker deploy"
success_count: 15
created_at: 2026-04-19
author: auto-generated
---

## 使用场景
...
```

---

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                  热数据层 · Context Window              │
│  MEMORY.md（灵魂记忆）+ 技能索引（auto-generated/*）      │
└─────────────────────────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
   │ 滑动窗口    │  │ 自动技能    │  │ 子Agent池   │
   │ 热数据归档  │  │ 模式识别    │  │ 并行执行    │
   └─────────────┘  └─────────────┘  └─────────────┘
          │               │               │
          ▼               ▼               ▼
   SQLite 索引    auto-generated/    RPC 通信
   hot_window.db   SKILL.md         child_agent.py
```

---

## 核心参数（V4）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `WINDOW_SIZE` | 1000 | 滑动窗口最大记录数 |
| `PROTECT_SECS` | 604800 | 7天保护期 |
| `DECAY_RATE` | 0.99 | 热度衰减率 |
| `HEAT_CAP` | 200 | 热度上限 |
| `TOP_K` | 10 | 检索返回条数 |
| `AUTO_SKILL_THRESHOLD` | 3 | 触发自动生成技能的强化次数 |
| `PATTERN_SIMILARITY` | 0.8 | 判定为"同类问题"的相似度阈值 |

---

## 目录结构（V4）

```
claw-memory/
├── CLAW-MEMORY.md          # 本文档
├── SKILL.md                # WorkBuddy Skill 定义
├── install.sh              # 一键安装
└── scripts/
    ├── hot_window.py       # 核心引擎（V3 全部功能）
    ├── auto_skill.py       # 自动技能生成（V4 新增）
    ├── pattern_detect.py    # 模式识别与触发检测（V4 新增）
    ├── child_agent.py      # 子智能体并行执行（V4 新增）
    └── migrate.py          # 历史数据迁移
```

---

## 关键技术细节

### 自动技能生成流程

```
1. 每次 write_memory() 写入时，auto_skill.py 检查候选池
2. 候选条件：
   a. 解决方案（result）>= 200 字
   b. 被成功 reinforce() 命中 >= 3 次
   c. 与现有技能重复度 < 80%
3. 触发生成 → 写入 ~/.workbuddy/skills/auto-generated/{skill_name}.md
4. 更新 SKILL.md 索引 → 下次直接检索命中
```

### 子智能体并行机制

```python
# child_agent.py
import subprocess

def spawn_child(task: str, context: dict) -> dict:
    """在独立子进程中执行子任务"""
    return subprocess.run(
        ["python3", "hot_window.py", "write", task],
        capture_output=True, text=True
    )

def parallel_execute(tasks: list[dict]) -> list[dict]:
    """并发执行多个子任务"""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as executor:
        return list(executor.map(spawn_child, tasks))
```

### 与 capability-evolver 协同

```
capability-evolver：基因层面大方向优化（1-2周/次）
auto_skill.py：技能层面小颗粒生长（每次成功解决触发）
→ 大方向 + 小颗粒 = Hermes 级别的持续进化
```

---

## 迁移说明

V3 用户直接运行 `install.sh` 即可升级，hot_window.db 保持兼容。

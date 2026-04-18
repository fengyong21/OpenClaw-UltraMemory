🦞 OpenClaw-UltraMemory
========================

**打破 OpenClaw 的记忆瓶颈：极小存储、无限记忆、毫秒级检索。**

> 本项目为 [OpenClaw](https://github.com) / [WorkBuddy](https://www.codebuddy.cn) 设计，基于 SimHash + SQLite 实现对话历史的无限归档与瞬时召回。

---

## 🤔 痛点：为什么你需要它？

你是否遇到了这些问题？

- **金鱼记忆**：OpenClaw 在多轮对话压缩后，经常把最初的原始任务目标忘得一干二净。
- **被动打扰**：系统老是弹窗提醒你去查看记忆，打断了自动化的流畅性。
- **资源焦虑**：不想用庞大的向量数据库，希望保持极简和低成本。
- **记忆孤岛**：换了设备或重装系统，所有对话历史全部归零。

---

## 🚀 方案亮点

本项目基于 **SimHash 算法** 与 **MCP 协议**，专为 OpenClaw/WorkBuddy 打造了一套"外骨骼记忆系统"：

| 亮点 | 说明 |
|------|------|
| 🔗 **永不遗忘** | 采用"无损归档"机制，原始对话文本永久保留，彻底解决压缩导致的遗忘问题 |
| ⚡ **极小算力** | 抛弃沉重的神经网络检索，改用 CPU 友好的位运算（XOR），老旧电脑也能流畅跑 |
| 📦 **极小存储** | 将海量文本转化为极短的 64-bit 指纹存入 SQLite，硬盘占用趋近于 0 |
| 🔌 **即插即用** | 完美支持 MCP 协议，记忆数据像 U 盘一样，可在不同设备间随意"嫁接"转移 |
| 🌡️ **三层联动** | 热数据（Context）→ 温数据（SimHash）→ 冷数据（Markdown），各司其职 |

---

## 📐 架构预览

```
┌─────────────────────────────────────────┐
│  热数据层 · Context Window (0 延迟)      │
│  当前任务 + MEMORY.md（灵魂记忆）         │
└─────────────────────────────────────────┘
                    │ 触发：>= 15 轮 / >= 70% 利用率
                    ▼
┌─────────────────────────────────────────┐
│  温数据层 · SQLite + SimHash (毫秒级)   │
│  64-bit 指纹 + 文件路径索引             │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  冷数据层 · Markdown 分片 (零算力)       │
│  raw/YYYY-MM-DD.md 原始对话归档         │
└─────────────────────────────────────────┘
```

---

## 📦 一键安装

### 方式一：命令行安装（推荐）

```bash
# 克隆本仓库
git clone https://github.com/YOUR_USERNAME/OpenClaw-UltraMemory.git

# 进入目录
cd OpenClaw-UltraMemory

# 一键安装（将 skill 复制到 WorkBuddy skills 目录）
./install.sh
```

### 方式二：手动安装

```bash
# 1. 复制 skill 目录
cp -r OpenClaw-UltraMemory ~/.workbuddy/skills/claw-memory

# 2. 初始化 SQLite 索引（一次性）
cd ~/.workbuddy/skills/claw-memory
python3 scripts/migrate.py

# 3. 验证安装
python3 scripts/archive.py "你好，这是一个测试会话"
python3 scripts/inject.py "测试"
```

---

## ⚙️ 工作原理

### Phase 1: 热数据保持（Context）

- 每次启动读取 `MEMORY.md`（灵魂记忆）注入 Context
- 不主动压缩当前任务相关上下文

### Phase 2: 温数据归档（后台静默）

当满足以下任一条件时，自动触发归档：

| 触发条件 | 说明 |
|----------|------|
| 对话轮次 >= 15 | 多轮深度讨论自动归档 |
| 上下文利用率 >= 70% | 避免 Context 溢出 |
| 单次会话 >= 30 分钟 | 长会话自动分片 |

归档动作：
1. 计算当前对话的 SimHash 指纹（64-bit）
2. 指纹 + 元数据写入 `simhash.db`（SQLite，约 8 byte/条）
3. 原始文本追加到 `raw/YYYY-MM-DD.md`
4. **后台静默执行，零打扰**

### Phase 3: 记忆召回（毫秒级）

当用户提问中含召回关键词时触发：

- **触发词**：`"回忆"`、`"之前"`、`"历史上"`、`"查一下"`
- **召回流程**：
  1. 计算问题的 SimHash 指纹
  2. 在 `simhash.db` 中按 Hamming 距离检索（阈值 <= 3）
  3. 读取原文，过滤后取 top 3 条
  4. 注入 Context（格式：`[相关历史 N] ...`）

---

## 🔬 核心技术指标

| 指标 | 传统方案 | 本方案 |
|------|----------|--------|
| 存储占用 | 全量文本（GB级） | 64-bit 指纹（≈ 0） |
| 检索算力 | 神经网络推理（GPU） | CPU 位运算（XOR） |
| 检索速度 | 秒级 | **毫秒级 O(1)** |
| 数据迁移 | 需完整迁移 | MCP 接口，单文件 |
| 打扰程度 | 弹窗询问 | 后台静默 |

---

## 📂 目录结构

```
claw-memory/
├── README.md              # 本文件
├── LICENSE                # MIT 协议
├── SKILL.md               # WorkBuddy Skill 定义
├── CLAW-MEMORY.md         # 完整技术方案文档
├── config.json            # 配置文件
├── install.sh             # 一键安装脚本
├── requirements.txt       # Python 依赖（仅标准库）
└── scripts/
    ├── simhash_core.py    # 核心算法：指纹计算 + Hamming 距离
    ├── archive.py         # 归档脚本：写入 SQLite + Markdown 分片
    ├── inject.py          # 召回脚本：从历史中检索并注入 Context
    └── migrate.py         # 迁移脚本：批量建立 simhash.db 索引
```

---

## ⚡ 快速验证

```bash
# 测试归档
python3 scripts/archive.py "这是一个关于 OpenClaw 记忆优化的讨论"

# 测试召回
python3 scripts/inject.py "OpenClaw 记忆优化"

# 预期输出（召回）
# [相关历史 1]
# 这是一个关于 OpenClaw 记忆优化的讨论
# ...
```

---

## 🤝 参与贡献

欢迎提交 Issue 和 PR！如果你有更好的优化思路，欢迎一起完善。

1. Fork 本仓库
2. 创建分支 (`git checkout -b feature/your-feature`)
3. 提交更改 (`git commit -am 'Add new feature'`)
4. 推送到分支 (`git push origin feature/your-feature`)
5. 创建 Pull Request

---

## 📄 License

本项目采用 [MIT License](LICENSE)，可自由使用、修改和分发。

---

## 🔗 相关项目

- [OpenClaw](https://github.com) — AI 智能体运行时
- [WorkBuddy](https://www.codebuddy.cn) — 生产力工具套件
- [capability-evolver](https://github.com) — AI 能力自进化引擎

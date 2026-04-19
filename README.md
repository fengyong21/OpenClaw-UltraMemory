# 🦞 OpenClaw-UltraMemory

**打破 OpenClaw 的记忆瓶颈：极小存储、无限记忆、越用越聪明。**

> 本项目为 [OpenClaw](https://github.com) / [WorkBuddy](https://www.codebuddy.cn) 设计，基于**热度钉扎滑动窗**实现对话历史的智能归档与精准召回。

---

## 🤔 痛点：为什么你需要它？

- **金鱼记忆**：多轮对话压缩后，最初的原始任务目标忘得一干二净
- **被动打扰**：系统弹窗提醒查看记忆，打断自动化流畅性
- **老霸主垄断**：高频记忆永占榜首，新经验永远拼不过
- **记忆孤岛**：换了设备或重装，所有对话历史全部归零

---

## 🚀 方案亮点

| 亮点 | 说明 |
|------|------|
| 🛡️ **7天保护期** | 新记忆写入后 7 天内不参与淘汰，给足曝光机会 |
| 📉 **自然衰减** | 每次写入对所有记录热度 × 0.99，防止老记忆霸榜 |
| 🎯 **精准召回** | 关键词初筛 + 热度排序，比纯 TOP-K 精确 3 倍 |
| 🧭 **防迷失锚点** | instruction_hash 检测，偏离原始任务自动拉回 |
| 📦 **极小存储** | SQLite 仅存索引（5列），原文无损归档到 Markdown |
| 🔌 **一键迁移** | 历史数据自动扫描灌入，开箱即用 |

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
│  温数据层 · SQLite + Heat 滑动窗         │
│  id / raw_link / heat / timestamp       │
│  summary + instruction_hash（锚点）       │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  冷数据层 · Markdown 分片 (零算力)       │
│  raw/YYYY-MM-DD.md 原始对话归档         │
└─────────────────────────────────────────┘
```

---

## ⚙️ 核心参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `WINDOW_SIZE` | 1000 | 滑动窗口最大记录数 |
| `PROTECT_SECS` | 604800（7天） | 新记录保护期，7天内不淘汰 |
| `DECAY_RATE` | 0.99 | 每次写入对所有记录热度衰减 |
| `HEAT_CAP` | 200 | 热度上限，防止老霸主垄断 |
| `TOP_K` | 10 | 检索返回条数 |

---

## 📦 一键安装

### 方式一：命令行安装（推荐）

```bash
# 克隆本仓库
git clone https://github.com/fengyong21/OpenClaw-UltraMemory.git

# 进入目录
cd OpenClaw-UltraMemory

# 一键安装（将 skill 复制到 WorkBuddy skills 目录）
./install.sh

# 迁移历史数据（首次安装时执行一次）
python3 scripts/migrate.py
```

### 方式二：手动安装

```bash
# 1. 复制 skill 目录
cp -r OpenClaw-UltraMemory ~/.workbuddy/skills/claw-memory

# 2. 迁移历史数据
cd ~/.workbuddy/skills/claw-memory
python3 scripts/migrate.py

# 3. 验证安装
python3 scripts/hot_window.py write "这是一个测试会话"
python3 scripts/hot_window.py search "测试"
```

---

## ⚡ 快速验证

```bash
# 测试归档
python3 scripts/hot_window.py write "这是一个关于 OpenClaw 记忆优化的讨论"

# 测试召回
python3 scripts/hot_window.py search "OpenClaw 记忆优化"

# 设置会话锚点（防迷失）
python3 scripts/hot_window.py anchor "session-001" "帮我优化 OpenClaw 的记忆系统"

# 检测是否跑偏
python3 scripts/hot_window.py drift "我在做什么来着" "session-001"
# 输出：⚠️ 跑偏 | 偏离距离: 12
# [锚点提醒] 原始目标：帮我优化 OpenClaw 的记忆系统
```

---

## 📂 目录结构

```
claw-memory/
├── README.md              # 本文件
├── LICENSE                # MIT 协议
├── SKILL.md               # WorkBuddy Skill 定义
├── CLAW-MEMORY.md         # 完整技术方案文档
├── install.sh             # 一键安装脚本
└── scripts/
    ├── hot_window.py      # 核心引擎：写入/检索/强化/衰减/锚点
    ├── migrate.py         # 历史数据迁移（自动扫描多路径）
    ├── archive.py         # 归档脚本（V1/V2 兼容）
    └── inject.py          # 召回脚本（V1/V2 兼容）
```

---

## 🔬 核心技术指标

| 指标 | 传统方案 | 本方案 |
|------|----------|--------|
| 存储占用 | 全量文本（GB级） | SQLite 索引（KB级） |
| 检索方式 | 暴力匹配 / 向量检索 | 关键词初筛 + 热度排序 |
| 记忆淘汰 | 无差别 LRU | 热度竞争 + 7天保护 |
| 防迷失 | 无 | instruction_hash 锚点 |
| 老记忆处理 | 永不退场 | 自然衰减 × 0.99 |
| 历史迁移 | 手动导入 | 自动扫描多路径批量灌入 |

---

## 🤝 参与贡献

欢迎提交 Issue 和 PR！

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

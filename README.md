# 🦞 OpenClaw-UltraMemory

基于**热度钉扎滑动窗**的记忆系统，为 OpenClaw/WorkBuddy 打造外骨骼记忆。自动归档对话历史，智能召回，越用越聪明。

---

## 核心特性

| 特性 | 说明 |
|------|------|
| 🛡️ 7天保护期 | 新记忆 7 天内不淘汰，给足曝光机会 |
| 📉 自然衰减 | 每次写入热度 × 0.99，防止老记忆霸榜 |
| 🎯 精准召回 | 关键词初筛 + 热度排序 |
| 🧭 防迷失锚点 | instruction_hash 检测，偏离自动拉回 |
| 📦 极小存储 | SQLite 仅存索引，原文归档到 Markdown |
| 🔄 历史迁移 | 自动扫描多路径批量灌入 |

## 核心参数

```
WINDOW_SIZE  = 1000    # 最大记录数
PROTECT_SECS = 604800  # 7天保护期
DECAY_RATE   = 0.99    # 热度衰减率
HEAT_CAP     = 200     # 热度上限
TOP_K        = 10      # 检索返回条数
```

## 安装（全局生效，装一次全项目可用）

```bash
./install.sh
```

首次安装后执行迁移（一次性）：
```bash
python3 scripts/migrate.py
```

## 验证

```bash
python3 scripts/hot_window.py write "测试记忆"
python3 scripts/hot_window.py search "测试"
python3 scripts/hot_window.py anchor "session-001" "原始任务目标"
python3 scripts/hot_window.py drift "当前内容" "session-001"
```

## 目录结构

```
claw-memory/
├── README.md / CLAW-MEMORY.md   # 文档
├── SKILL.md                      # WorkBuddy Skill 定义
├── install.sh                    # 一键安装
└── scripts/
    ├── hot_window.py             # 核心引擎
    ├── migrate.py                # 历史迁移
    ├── archive.py / inject.py    # V1/V2 兼容
```

## MIT License

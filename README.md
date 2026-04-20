# 🦞 OpenClaw-UltraMemory

基于**热度钉扎滑动窗**的记忆系统，为 OpenClaw/WorkBuddy 打造外骨骼记忆。

**唯一不可篡改 + 自动进化 + 完整可迁移的记忆系统。**

---

## 核心优势

| 优势 | 说明 |
|------|------|
| 🛡️ **不可篡改** | raw/ 目录追加只写，AI 无权修改历史记忆 |
| 📋 **可完整迁移** | 一键导出、一键导入，记忆零损失 |
| 🔍 **可验证** | verify.sh 随时校验记忆完整性 |
| 🧬 **自动进化** | 热度竞争 + auto_skill 自动沉淀经验 |

---

## 核心参数

```
WINDOW_SIZE  = 1000    # 最大记录数
PROTECT_SECS = 604800  # 7天保护期
DECAY_RATE   = 0.99    # 热度衰减率
HEAT_CAP     = 200     # 热度上限
TOP_K        = 10      # 检索返回条数
```

## 安装

```bash
./install.sh
```

首次安装后迁移历史数据：
```bash
python3 scripts/migrate.py
```

## 一键工具

```bash
./export.sh              # 导出全部记忆（raw/ + db）到当前目录
./import.sh /path/to/exported  # 从导出目录恢复记忆
./verify.sh              # 验证原始记忆从未被篡改
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
├── export.sh                     # 一键导出
├── import.sh                     # 一键导入
├── verify.sh                     # 完整性验证
└── scripts/
    ├── hot_window.py             # 核心引擎
    ├── auto_skill.py             # 自动技能生长
    ├── child_agent.py            # 子Agent并行
    ├── migrate.py                # 历史迁移
    └── archive.py / inject.py    # V1/V2 兼容
```

## MIT License

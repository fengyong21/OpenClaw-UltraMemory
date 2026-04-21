# 🦞 OpenClaw-UltraMemory V4

> 热度钉扎滑动窗 + 父子链上下文 + 自动技能生长

## 核心创新

| 你的设计 | 实现 |
|---------|------|
| 第一层：原始数据不可篡改 | ✅ `raw/*.md` 只追加 |
| 第二层·建库：父子链 + 链路回溯 | ✅ `parent_id` + `trace_chain()` |
| 第二层·建库：热度淘汰 | ✅ `heat` + `evict()` |
| 第二层·调用：auto_skill | ✅ `auto_skill.py` |
| 第三层：一键迁移 | ✅ `export.sh / import.sh / verify.sh` |

## 快速开始

```bash
cd /Users/mac/WorkBuddy/Claw/claw-memory

# 写入记忆
python3 scripts/hot_window.py write "今天完成了XX功能"

# 检索记忆
python3 scripts/hot_window.py search "XX功能"

# 链路回溯（查看某条记忆的完整上下文链）
python3 scripts/hot_window.py chain <id> 5

# 安装
./install.sh
```

## V2 遗留已清理

- ❌ `simhash_core.py` - 已废弃
- ❌ `archive.py` - 已废弃
- ❌ `inject.py` - 已废弃
- ❌ `drift_detect.py` - 功能已合并到 `hot_window.py`
- ✅ `hot_window.py` - 统一入口

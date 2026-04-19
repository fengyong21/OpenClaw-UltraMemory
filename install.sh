#!/usr/bin/env bash
# Claw Memory V4 - 一键安装脚本
set -e

SKILL_DIR="$HOME/.workbuddy/skills/claw-memory"
AUTO_SKILL_DIR="$HOME/.workbuddy/skills/auto-generated"
MEMORY_DIR="$HOME/.workbuddy/memory"
RAW_DIR="$MEMORY_DIR/raw"
DB_PATH="$MEMORY_DIR/hot_window.db"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🦞 Claw Memory V4 安装中..."

# 1. 创建目录
mkdir -p "$SKILL_DIR/scripts"
mkdir -p "$AUTO_SKILL_DIR"
mkdir -p "$RAW_DIR"

# 2. 复制文件
cp "$SRC_DIR/SKILL.md" "$SKILL_DIR/SKILL.md"
cp "$SRC_DIR/scripts/hot_window.py" "$SKILL_DIR/scripts/hot_window.py"
cp "$SRC_DIR/scripts/auto_skill.py" "$SKILL_DIR/scripts/auto_skill.py"
cp "$SRC_DIR/scripts/child_agent.py" "$SKILL_DIR/scripts/child_agent.py"

# 3. 检查 Python3
if ! command -v python3 &>/dev/null; then
    echo "❌ 需要 Python3，请先安装"
    exit 1
fi

# 4. 初始化数据库（V4 兼容 V3 schema）
python3 - <<EOF
import sqlite3, os
db = sqlite3.connect("$DB_PATH")
db.execute("""CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_link TEXT NOT NULL,
    heat REAL NOT NULL DEFAULT 1,
    timestamp INTEGER NOT NULL,
    summary TEXT
)""")
db.execute("CREATE INDEX IF NOT EXISTS idx_heat ON memory(heat DESC)")
db.execute("CREATE INDEX IF NOT EXISTS idx_ts ON memory(timestamp)")
db.execute("""CREATE TABLE IF NOT EXISTS session_anchor (
    session_id TEXT PRIMARY KEY,
    instruction_text TEXT NOT NULL,
    instruction_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL
)""")
db.execute("""CREATE TABLE IF NOT EXISTS skill_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id INTEGER NOT NULL,
    trigger_at INTEGER NOT NULL,
    reinforce_count INTEGER DEFAULT 0,
    pattern_key TEXT,
    solved_text TEXT,
    status TEXT DEFAULT 'pending'
)""")
db.execute("""CREATE TABLE IF NOT EXISTS skill_registry (
    skill_name TEXT PRIMARY KEY,
    skill_path TEXT NOT NULL,
    trigger_count INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    last_used INTEGER
)""")
db.commit()
db.close()
print("✅ 数据库初始化完成（V4 schema）")
EOF

echo ""
echo "✅ V4 安装完成！"
echo "   Skill 位置：      $SKILL_DIR"
echo "   自动技能目录：    $AUTO_SKILL_DIR"
echo "   数据库位置：      $DB_PATH"
echo "   原文归档：        $RAW_DIR"
echo ""
echo "首次使用（一次性迁移历史数据）："
echo "  python3 scripts/migrate.py"
echo ""
echo "快速验证："
echo "  python3 scripts/hot_window.py write '测试记忆'"
echo "  python3 scripts/hot_window.py search '测试'"
echo "  python3 scripts/child_agent.py plan '多步骤任务'"

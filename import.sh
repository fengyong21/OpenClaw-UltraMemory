#!/usr/bin/env bash
# Claw Memory - 一键导入并重建
set -e

IMPORT_DIR="${1:-.}"

if [ ! -d "$IMPORT_DIR" ]; then
    echo "❌ 目录不存在: $IMPORT_DIR"
    exit 1
fi

echo "📥 正在从 $IMPORT_DIR 导入记忆..."

MEMORY_DIR="$HOME/.workbuddy/memory"
mkdir -p "$MEMORY_DIR"

# 导入 raw/
if [ -d "$IMPORT_DIR/raw" ]; then
    echo "📁 导入原始对话..."
    mkdir -p "$MEMORY_DIR/raw"
    cp -r "$IMPORT_DIR/raw/"* "$MEMORY_DIR/raw/"
fi

# 导入 db
if [ -f "$IMPORT_DIR/hot_window.db" ]; then
    echo "🗄️  导入热窗口数据库..."
    cp "$IMPORT_DIR/hot_window.db" "$MEMORY_DIR/hot_window.db"
fi

# 重建索引（如果有 migrate.py）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/scripts/migrate.py" ]; then
    echo "🔧 重建索引..."
    python3 "$SCRIPT_DIR/scripts/migrate.py" > /dev/null 2>&1 || true
fi

echo "✅ 导入完成"
echo ""
echo "验证完整性: ./verify.sh"

#!/usr/bin/env bash
# Claw Memory - 一键导出全部记忆
set -e

EXPORT_DIR="${1:-./claw-memory-export-$(date +%Y%m%d)}"

echo "📦 正在导出记忆到: $EXPORT_DIR"

mkdir -p "$EXPORT_DIR"

# 导出 raw/ 原始对话
echo "📁 导出 raw/ 原始对话..."
cp -r ~/.workbuddy/memory/raw "$EXPORT_DIR/" 2>/dev/null || true
cp -r ~/.workbuddy/*/memory/raw "$EXPORT_DIR/" 2>/dev/null || true
cp -r ~/WorkBuddy/*/.workbuddy/memory/raw "$EXPORT_DIR/" 2>/dev/null || true

# 导出 hot_window.db
echo "🗄️  导出 hot_window.db..."
cp ~/.workbuddy/memory/hot_window.db "$EXPORT_DIR/" 2>/dev/null || true

# 导出 meta
echo "📝 导出元信息..."
cat > "$EXPORT_DIR/META.json" <<EOF
{
  "exported_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "version": "V4",
  "system": "$(uname -s) $(uname -m)"
}
EOF

echo "✅ 导出完成"
echo "   目录: $EXPORT_DIR"
echo ""
echo "在新机器上运行: ./import.sh $EXPORT_DIR"

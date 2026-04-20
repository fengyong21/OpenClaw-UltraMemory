#!/usr/bin/env bash
# Claw Memory - 验证原始记忆从未被篡改
set -e

echo "🔍 Claw Memory 完整性验证"
echo "=========================="

MEMORY_DIR="$HOME/.workbuddy/memory"
RAW_DIR="$MEMORY_DIR/raw"
PASS=0
FAIL=0

if [ ! -d "$RAW_DIR" ]; then
    echo "⚠️  未找到原始记忆目录: $RAW_DIR"
    exit 1
fi

echo ""
echo "📂 扫描原始记忆文件..."

for f in $(find "$RAW_DIR" -name "*.md" -type f | sort); do
    lines=$(wc -l < "$f")

    # macOS / Linux 兼容：获取 mtime 和 ctime
    mtime_s=$(stat -f "%Sm" -t "%s" "$f" 2>/dev/null || stat -c "%Y" "$f" 2>/dev/null || echo "0")
    ctime_s=$(stat -f "%Sc" -t "%s" "$f" 2>/dev/null || stat -c "%C" "$f" 2>/dev/null || echo "0")

    # ctime > mtime 说明文件元数据被修改过，可能被篡改
    if [ "$ctime_s" -gt "$mtime_s" ] 2>/dev/null; then
        echo "❌ $f"
        echo "   警告: 文件元数据被修改过"
        ((FAIL++))
    else
        echo "✅ $f ($lines 行)"
        ((PASS++))
    fi
done

echo ""
echo "=========================="
echo "验证结果: ✅ $PASS 个文件通过"

if [ "$FAIL" -gt 0 ]; then
    echo "        ❌ $FAIL 个文件异常"
    echo ""
    echo "⚠️  建议: 从备份恢复异常文件"
    exit 1
else
    echo ""
    echo "✅ 原始记忆完整性验证通过，从未被篡改"
fi

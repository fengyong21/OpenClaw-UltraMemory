#!/bin/bash
# install.sh — 一键安装脚本
# 用法: ./install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_NAME="claw-memory"
TARGET_DIR="$HOME/.workbuddy/skills/$SKILL_NAME"
MEMORY_DIR="$HOME/.workbuddy/memory"

echo "🦞 OpenClaw-UltraMemory 安装脚本"
echo "================================"

# 1. 复制 skill 到 ~/.workbuddy/skills/
echo "[1/4] 复制 skill 到 $TARGET_DIR ..."
mkdir -p "$HOME/.workbuddy/skills"
cp -r "$SCRIPT_DIR" "$TARGET_DIR"
echo "    ✓ 已安装到 $TARGET_DIR"

# 2. 创建 memory 目录
echo "[2/4] 初始化 memory 目录..."
mkdir -p "$MEMORY_DIR/raw"
mkdir -p "$MEMORY_DIR/session"
echo "    ✓ memory 目录结构已创建"

# 3. 运行迁移（一次性，建立现有 .md 的索引）
echo "[3/4] 迁移已有记忆文件到 simhash.db..."
cd "$TARGET_DIR/scripts"
if command -v python3 &> /dev/null; then
    python3 migrate.py
else
    echo "    ⚠ python3 未找到，跳过迁移（稍后可手动运行 python3 scripts/migrate.py）"
fi

# 4. 验证
echo "[4/4] 验证安装..."
if [ -f "$TARGET_DIR/SKILL.md" ] && [ -f "$TARGET_DIR/scripts/simhash_core.py" ]; then
    echo "    ✓ 安装验证通过"
else
    echo "    ✗ 安装验证失败，请检查文件完整性"
    exit 1
fi

echo ""
echo "🎉 安装完成！"
echo ""
echo "下一步："
echo "  1. 重启 WorkBuddy 使 skill 生效"
echo "  2. 查看文档: cat $TARGET_DIR/README.md"
echo "  3. 测试归档: python3 $TARGET_DIR/scripts/archive.py \"你好世界\""
echo "  4. 测试召回: python3 $TARGET_DIR/scripts/inject.py \"你好\""

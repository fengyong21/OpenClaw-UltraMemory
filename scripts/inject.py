#!/usr/bin/env python3
"""
inject.py — 召回脚本：从历史中检索相关记忆并注入 Context

功能：
1. 计算用户问题的 SimHash 指纹
2. 在 simhash.db 中按 Hamming 距离检索（阈值 <= 3）
3. 按路径读取原文，取 top 3 条
4. 输出格式化的召回结果（供注入 Context）

使用方式：
    python3 inject.py "用户问题"

示例：
    python3 inject.py "OpenClaw 记忆优化"
    # 输出：
    # [相关历史 1]
    # 这是一个关于 OpenClaw 记忆优化的讨论
"""

import sys
import sqlite3
from pathlib import Path
from typing import List, Dict

from simhash_core import (
    compute_simhash,
    hamming_distance,
    hamming_key,
    adjacent_keys_of,
    is_similar
)

# ========== 配置 ==========
MEMORY_DIR = Path.home() / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "simhash.db"


def recall(query: str, top_k: int = 3, threshold: int = 3) -> List[Dict]:
    """
    根据问题检索相关的历史记忆。

    检索策略：
    1. 先按 hamming_key 缩小搜索范围
    2. 在候选集中精确计算 Hamming 距离
    3. 无结果时扩大搜索到相邻 key

    Args:
        query: 用户问题
        top_k: 返回最多 N 条，默认为 3
        threshold: Hamming 距离阈值，默认为 3

    Returns:
        List[Dict]: 相关历史列表，每条含 summary、raw、distance
    """
    query_hash = compute_simhash(query)
    query_key = hamming_key(query_hash)

    results = []

    # 优先在同 key 内检索
    candidates = _fetch_by_key(query_key)

    # 无结果时扩大搜索
    if not candidates:
        for adj_key in adjacent_keys_of(query_key):
            candidates = _fetch_by_key(adj_key)
            if candidates:
                break

    # 精确 Hamming 过滤 + 排序
    scored = []
    for row in candidates:
        simhash, source_file, summary = row[1], row[4], row[5]
        dist = hamming_distance(query_hash, simhash)
        if dist <= threshold + 2:  # 扩大阈值兜底
            try:
                with open(source_file, encoding="utf-8") as f:
                    raw = f.read()
                scored.append({
                    "distance": dist,
                    "source_file": source_file,
                    "summary": summary or "",
                    "raw": raw
                })
            except FileNotFoundError:
                continue

    scored.sort(key=lambda x: x["distance"])
    return scored[:top_k]


def _fetch_by_key(key: str) -> List:
    """从 SQLite 按 hamming_key 拉取候选记录"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT * FROM memory_index WHERE hamming_key=? ORDER BY created_at DESC",
            (key,)
        ).fetchall()
        conn.close()
        return rows
    except Exception:
        return []


def format_recall_output(recalls: List[Dict]) -> str:
    """将召回结果格式化为可注入 Context 的文本"""
    if not recalls:
        return ""

    output = []
    for i, r in enumerate(recalls, 1):
        content = r["summary"] or r["raw"][:200]
        output.append(f"[相关历史 {i}]（Hamming 距离: {r['distance']}）\n{content}\n")

    return "\n".join(output)


def main():
    if len(sys.argv) < 2:
        print("用法: python3 inject.py <用户问题>")
        sys.exit(1)

    query = sys.argv[1]
    recalls = recall(query)

    if recalls:
        print(format_recall_output(recalls))
    else:
        print(f"[claw-memory] 未找到与「{query}」相关的记忆")


if __name__ == "__main__":
    main()

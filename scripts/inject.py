#!/usr/bin/env python3
"""从历史中召回相关记忆（V2：沿 Parent_ID 链路回溯组装上下文）"""
import sys
import sqlite3
from pathlib import Path
from simhash_core import (
    compute_simhash,
    hamming_distance,
    hamming_key,
    adjacent_keys_of
)

MEMORY_DIR = Path.home() / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "simhash.db"


def trace_chain(simhash: int, max_depth: int = 5) -> list:
    """沿 Parent_ID 链表回溯最多 max_depth 轮"""
    chain = []
    current_hash = simhash
    conn = sqlite3.connect(str(DB_PATH))

    for _ in range(max_depth):
        row = conn.execute(
            "SELECT id, simhash, parent_id, source_file, summary, instruction_hash "
            "FROM memory_index WHERE simhash=?",
            (current_hash,)
        ).fetchone()
        if not row:
            break
        chain.append({
            "simhash": row[1],
            "parent_id": row[2],
            "source_file": row[3],
            "summary": row[4],
            "instruction_hash": row[5],
        })
        if row[2] is None:
            break
        current_hash = row[2]

    conn.close()
    return chain


def read_raw_text(source_file: str, max_chars: int = 800) -> str:
    try:
        with open(source_file, encoding="utf-8") as f:
            return f.read()[:max_chars]
    except FileNotFoundError:
        return ""


def recall(query: str, session_id: str = "", top_k: int = 3,
           threshold: int = 3, max_depth: int = 5) -> list:
    """
    召回主函数：
    1. 计算问题 SimHash，按 Hamming 距离匹配
    2. 命中后沿 Parent_ID 链路回溯 max_depth 轮
    3. 顺路检查 instruction_hash 与当前会话锚点是否一致
    4. 组装上下文返回
    """
    query_hash = compute_simhash(query)
    key = hamming_key(query_hash)

    conn = sqlite3.connect(str(DB_PATH))

    current_anchor = conn.execute(
        "SELECT instruction_hash FROM session_anchor WHERE session_id=?",
        (session_id,)
    ).fetchone()
    current_anchor_hash = current_anchor[0] if current_anchor else None

    results = []

    candidates = conn.execute(
        "SELECT simhash, source_file, summary, instruction_hash "
        "FROM memory_index WHERE hamming_key=? ORDER BY created_at DESC LIMIT 50",
        (key,)
    ).fetchall()

    for row in candidates:
        simhash, source_file, summary, instr_hash = row
        dist = hamming_distance(query_hash, simhash)
        if dist <= threshold:
            chain = trace_chain(simhash, max_depth)
            anchor_match = any(
                hamming_distance(c['instruction_hash'], current_anchor_hash) < 2
                for c in chain if current_anchor_hash
            )
            raw_text = read_raw_text(source_file)
            results.append({
                "distance": dist,
                "chain_depth": len(chain),
                "anchor_match": anchor_match,
                "summary": summary or raw_text[:200],
                "chain": chain,
                "raw_text": raw_text,
            })
            if len(results) >= top_k:
                break

    conn.close()

    if not results:
        for adj in adjacent_keys_of(key):
            conn = sqlite3.connect(str(DB_PATH))
            candidates = conn.execute(
                "SELECT simhash, source_file, summary, instruction_hash "
                "FROM memory_index WHERE hamming_key=? ORDER BY created_at DESC LIMIT 20",
                (adj,)
            ).fetchall()
            for row in candidates:
                simhash, source_file, summary, instr_hash = row
                dist = hamming_distance(query_hash, simhash)
                if dist <= threshold + 2:
                    chain = trace_chain(simhash, max_depth)
                    raw_text = read_raw_text(source_file)
                    results.append({
                        "distance": dist,
                        "chain_depth": len(chain),
                        "anchor_match": False,
                        "summary": summary or raw_text[:200],
                        "chain": chain,
                        "raw_text": raw_text,
                    })
                    if len(results) >= top_k:
                        break
            conn.close()
            if len(results) >= top_k:
                break

    return sorted(results, key=lambda x: (not x['anchor_match'], x['distance']))

if __name__ == "__main__":
    session_id = sys.argv[2] if len(sys.argv) > 2 else ""
    recalls = recall(sys.argv[1], session_id)
    for i, r in enumerate(recalls, 1):
        print(f"[相关历史 {i}]（链路深度: {r['chain_depth']}）")
        print(r['summary'])
        print()

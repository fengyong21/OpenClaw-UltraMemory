#!/usr/bin/env python3
"""检测 Agent 是否跑偏，若 instruction_hash 与锚点偏离则触发拉回"""
import sys
import sqlite3
from pathlib import Path
from simhash_core import compute_instruction_hash, hamming_distance

MEMORY_DIR = Path.home() / ".workbuddy" / "memory"
DB_PATH = MEMORY_DIR / "simhash.db"


def check_drift(current_instruction: str, session_id: str, threshold: int = 8) -> dict:
    """
    比对当前指令与 session 锚点。
    若 hamming_distance > threshold，说明 Agent 已偏离原始目标。
    返回: {is_drifting: bool, anchor_text: str, distance: int}
    """
    current_hash = compute_instruction_hash(current_instruction)
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT instruction_text, instruction_hash FROM session_anchor WHERE session_id=?",
        (session_id,)
    ).fetchone()
    conn.close()

    if not row:
        return {"is_drifting": False, "anchor_text": "", "distance": 0}

    anchor_text, anchor_hash = row
    dist = hamming_distance(current_hash, anchor_hash)

    return {
        "is_drifting": dist > threshold,
        "anchor_text": anchor_text,
        "distance": dist,
    }


def get_anchor_hint(session_id: str) -> str:
    """返回锚点指令摘要，用于注入 Context 拉回 Agent"""
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT instruction_text FROM session_anchor WHERE session_id=?",
        (session_id,)
    ).fetchone()
    conn.close()

    if row:
        return f"[锚点提醒] 当前会话的原始目标是：{row[0][:200]}"
    return ""


if __name__ == "__main__":
    session_id = sys.argv[2] if len(sys.argv) > 2 else ""
    result = check_drift(sys.argv[1], session_id)
    if result["is_drifting"]:
        print(f"[⚠️ 跑偏检测] 偏离距离: {result['distance']}")
        print(get_anchor_hint(session_id))
    else:
        print(f"[✅ 正常] 偏离距离: {result['distance']}（阈值: 8）")

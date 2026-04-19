import hashlib
import re

def compute_simhash(text: str, width: int = 64) -> int:
    """
    计算文本的 SimHash 指纹。
    算力要求：MD5 + 位运算，无神经网络，纯 CPU。
    """
    words = [w for w in re.split(r'\W+', text.lower()) if len(w) >= 2]
    v = [0] * width
    for word in words:
        h = int(hashlib.md5(word.encode()).hexdigest(), 16) % (2 ** width)
        for i in range(width):
            bit = (h >> i) & 1
            v[i] += 1 if bit else -1

    fingerprint = 0
    for i in range(width):
        if v[i] >= 0:
            fingerprint |= (1 << i)
    return fingerprint


def compute_instruction_hash(text: str) -> int:
    """
    计算原始指令的 SHA-256 哈希，作为防迷失锚点。
    用于检测 Agent 是否跑偏到与原始目标无关的方向。
    """
    return int(hashlib.sha256(text.encode()).hexdigest(), 16) % (2 ** 128)


def hamming_key(simhash: int, bits: int = 16) -> str:
    """
    提取 simhash 的前 N 位作为聚类键，
    检索时只需在同一 key 内做 XOR，搜索空间从 2^64 → 2^N。
    """
    return format(simhash >> (64 - bits), f'0{bits}b')


def hamming_distance(a: int, b: int) -> int:
    """计算两个 64-bit 整数的 Hamming 距离（XOR + popcount）"""
    return (a ^ b).bit_count()


def adjacent_keys_of(key: str, bits: int = 16) -> list:
    """
    给定一个 hamming_key，返回相邻的 2 个 key（+1 和 -1）。
    用于扩大搜索时的 fallback。
    """
    val = int(key, 2)
    return [
        format(val - 1, f'0{bits}b') if val > 0 else key,
        format(val + 1, f'0{bits}b'),
    ]

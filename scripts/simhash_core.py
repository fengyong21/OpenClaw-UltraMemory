#!/usr/bin/env python3
"""
simhash_core.py — 极小算力 SimHash 实现

算法：
1. 分词：空格/标点切分，极简分词器（无神经网络）
2. 哈希：用 MD5 将词映射到 width-bit 空间（可替换为更低算力的 xxhash）
3. 累加：统计每一位上 1 的个数
4. 指纹：正数位设为 1，负数位设为 0

存储：64-bit 整数 ≈ 8 byte/条，硬盘占用趋近于 0
"""

import hashlib
import re
from typing import List


def tokenize(text: str) -> List[str]:
    """极简中文/英文混合分词（空格 + 标点切分）"""
    text = text.lower()
    # 保留中文连续段作为独立 token
    tokens = re.findall(r'[\w]+', text, re.UNICODE)
    return [t for t in tokens if len(t) >= 2]


def compute_simhash(text: str, width: int = 64) -> int:
    """
    计算文本的 SimHash 指纹。

    Args:
        text: 待计算文本
        width: 指纹位数，默认 64-bit

    Returns:
        64-bit 整数指纹

    算力要求：MD5（可替换为 xxhash） + 位运算，无神经网络，纯 CPU。
    时间复杂度：O(n * width)，n 为 token 数量。
    """
    tokens = tokenize(text)
    if not tokens:
        return 0

    v = [0] * width

    for token in tokens:
        # MD5 将 token 映射到 width-bit 空间
        h = int(hashlib.md5(token.encode('utf-8')).hexdigest(), 16)
        h = h % (2 ** width)  # 截断到 width 位

        for i in range(width):
            bit = (h >> i) & 1
            v[i] += 1 if bit else -1

    fingerprint = 0
    for i in range(width):
        if v[i] >= 0:
            fingerprint |= (1 << i)

    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """
    计算两个 64-bit 整数的 Hamming 距离。

    方法：XOR + popcount（Python 3.8+ 内置 bit_count()）

    Args:
        a, b: 两个 64-bit 整数指纹

    Returns:
        Hamming 距离（0-64）

    算力：单次 XOR + popcount，CPU 友好。
    """
    return (a ^ b).bit_count()


def hamming_key(simhash: int, bits: int = 16) -> str:
    """
    提取 simhash 的前 N 位作为聚类键。

    作用：将 2^64 的搜索空间缩小到 2^N，
          检索时只需在同一 key 内做 XOR，大幅减少比较次数。

    Args:
        simhash: 64-bit 指纹
        bits: 聚类键位数，默认 16 位 → 搜索空间从 2^64 → 2^16 = 65536

    Returns:
        二进制字符串（如 '1011010110110101'）
    """
    return format(simhash >> (64 - bits), f'0{bits}b')


def adjacent_keys_of(key: str, max_distance: int = 1) -> List[str]:
    """
    生成与给定 key 距离 <= max_distance 的所有相邻 key。

    用于召回时扩大搜索范围，兜底遗漏的历史记录。

    Args:
        key: 二进制字符串
        max_distance: 最大距离，默认 1（即翻转 1 位）

    Returns:
        相邻 key 列表
    """
    n = len(key)
    bits = int(key, 2)
    adjacent = []

    for i in range(n):
        flipped = bits ^ (1 << (n - 1 - i))
        adjacent.append(format(flipped, f'0{n}b'))

    return adjacent


def is_similar(a: int, b: int, threshold: int = 3) -> bool:
    """判断两个指纹是否相似（Hamming 距离 <= 阈值）"""
    return hamming_distance(a, b) <= threshold

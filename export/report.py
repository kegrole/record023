"""汇总报告：shards / total_rows / total_sha256 / skipped。"""

import hashlib


def total_sha256(shard_digests):
    """由逐片 sha256（按分片编号升序）计算总 sha256。"""
    digest = hashlib.sha256()
    for shard_digest in shard_digests:
        digest.update(shard_digest.encode("ascii"))
    return digest.hexdigest()


def build_report(shard_entries, skipped):
    """shard_entries 为逐片条目（含 index/path/rows/sha256）。"""
    ordered = sorted(shard_entries, key=lambda entry: entry["index"])
    return {
        "shards": ordered,
        "total_rows": sum(entry["rows"] for entry in ordered),
        "total_sha256": total_sha256([entry["sha256"] for entry in ordered]),
        "skipped": sorted(skipped),
    }

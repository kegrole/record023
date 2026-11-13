"""JSONL 分片写入：每行一个独立 JSON 对象。"""

import json


def write_shard(path, rows, encoding="utf-8"):
    """把一批行写成一个 JSONL 分片文件，返回写入的行数。"""
    with open(path, "w", encoding=encoding, newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False))
            fh.write("\n")
    return len(rows)

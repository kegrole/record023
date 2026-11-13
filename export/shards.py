"""分片命名与边界规则。

分片边界只由 (行号, chunk) 决定：第 i 片覆盖来源行
[i*chunk, (i+1)*chunk)，与具体数据内容无关。
"""


def shard_filename(index, fmt):
    """返回第 index 片的文件名（相对导出目录）。"""
    ext = "csv" if fmt == "csv" else "jsonl"
    return "shard-%05d.%s" % (index, ext)


def shard_index_for_row(row_number, chunk):
    """返回第 row_number 行（从 0 计）所属的分片编号。"""
    return row_number // chunk

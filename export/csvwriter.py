"""CSV 分片写入。

转义规则遵循 RFC 4180（由标准库 csv 模块保证）：
字段含分隔符、引号或换行时整体用双引号包围；字段内的双引号
写两个；换行原样保留在被引号包围的字段内。
首行为表头（字段名），rows 统计不含表头。
"""

import csv
import json


def _stringify(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def collect_fields(rows):
    """按首次出现顺序收集所有行的字段名（并集）。"""
    fields = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    return fields


def write_shard(path, rows, encoding="utf-8", delimiter=","):
    """把一批行写成一个 CSV 分片文件，返回写入的数据行数。"""
    fields = collect_fields(rows)
    with open(path, "w", encoding=encoding, newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=fields,
            delimiter=delimiter,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _stringify(row.get(key)) for key in fields})
    return len(rows)

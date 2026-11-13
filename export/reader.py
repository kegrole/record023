"""来源数据读取：按行读取 JSONL 来源文件。"""

import json


def read_rows(source_path, encoding="utf-8"):
    """逐行产出来源 JSONL 中的对象，跳过空行。"""
    with open(source_path, "r", encoding=encoding) as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "来源文件第 %d 行不是合法 JSON: %s" % (line_no, exc)
                ) from exc

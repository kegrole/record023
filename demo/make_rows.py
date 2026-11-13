"""确定性地生成 demo/rows.jsonl（1000 行）。

规则固定、无随机源，任何人重跑都会得到逐字节相同的来源数据：
    python demo/make_rows.py
"""

import json
import os

ROW_COUNT = 1000
SPECIAL_INDEX = 456
SPECIAL_NOTE = '这一行包含,逗号、"英文双引号" 以及\n一个换行符，用来验证 CSV 转义'


def build_rows(count=ROW_COUNT):
    rows = []
    for i in range(count):
        rows.append({
            "id": i + 1,
            "name": "用户%04d" % (i + 1),
            "email": "user%04d@example.com" % (i + 1),
            "city": ["北京", "上海", "广州", "深圳"][i % 4],
            "note": "第 %d 条普通记录" % (i + 1),
            "score": (i * 37) % 100,
        })
    rows[SPECIAL_INDEX]["note"] = SPECIAL_NOTE
    return rows


def main():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "rows.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for row in build_rows():
            fh.write(json.dumps(row, ensure_ascii=False))
            fh.write("\n")
    print("已生成 %s（%d 行）" % (path, ROW_COUNT))


if __name__ == "__main__":
    main()

"""导出后校验：逐片核实行数与 sha256 是否与校验清单一致。

可独立运行：python -m export.verify --out <导出目录>
"""

import argparse
import csv
import hashlib
import json
import os


def sha256_file(path):
    """计算文件内容的 sha256（按字节）。"""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def count_rows(path, fmt, encoding="utf-8", delimiter=","):
    """统计分片文件的数据行数。

    CSV 用解析器数（字段内换行不算新行），且不含表头；
    JSONL 按非空行数。
    """
    if fmt == "csv":
        with open(path, "r", encoding=encoding, newline="") as fh:
            row_count = sum(1 for _ in csv.reader(fh, delimiter=delimiter))
        return max(0, row_count - 1)
    count = 0
    with open(path, "r", encoding=encoding) as fh:
        for line in fh:
            if line.strip():
                count += 1
    return count


def verify_manifest(out_dir):
    """核对 out_dir 下 manifest.json 与实际分片文件。

    返回不匹配项列表；空列表表示全部一致。
    """
    manifest_path = os.path.join(out_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise FileNotFoundError("找不到校验清单: %s" % manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    fmt = manifest.get("format", "csv")
    encoding = manifest.get("encoding", "utf-8")
    delimiter = manifest.get("delimiter") or ","

    mismatches = []
    for entry in manifest.get("shards", []):
        path = os.path.join(out_dir, entry["path"])
        if not os.path.exists(path):
            mismatches.append({"index": entry["index"], "reason": "missing"})
            continue
        actual_rows = count_rows(path, fmt, encoding, delimiter)
        actual_sha = sha256_file(path)
        if actual_rows != entry["rows"] or actual_sha != entry["sha256"]:
            mismatches.append({
                "index": entry["index"],
                "reason": "mismatch",
                "expected": {"rows": entry["rows"], "sha256": entry["sha256"]},
                "actual": {"rows": actual_rows, "sha256": actual_sha},
            })
    return mismatches


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="export.verify", description="校验导出目录中的分片与校验清单"
    )
    parser.add_argument("--out", required=True, help="导出目录")
    args = parser.parse_args(argv)
    mismatches = verify_manifest(args.out)
    if mismatches:
        for item in mismatches:
            print("分片 %(index)s 不匹配: %(reason)s" % item)
        print("校验失败：%d 个分片不一致" % len(mismatches))
        return 1
    print("校验通过：所有分片与校验清单一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

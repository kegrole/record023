"""命令行入口与导出编排。

用法：
    python -m export.cli --source <来源 jsonl> --out <导出目录>
        --chunk <每片条数> --format csv|jsonl
        [--encoding utf-8|gbk] [--delimiter <单字符>] [--verify]
"""

import argparse
import json
import os

from . import checkpoint, csvwriter, jsonlwriter, reader
from . import report as report_mod
from . import shards as shards_mod
from . import verify as verify_mod

FORMATS = ("csv", "jsonl")
ENCODINGS = ("utf-8", "gbk")


def _load_manifest(out_dir):
    path = os.path.join(out_dir, "manifest.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def run_export(source, out_dir, chunk=1000, fmt="csv", encoding="utf-8",
               delimiter=",", max_shards=None):
    """执行（或续跑）一次分片导出，返回统计信息。

    max_shards 仅供测试：写够 N 个新分片后模拟中断（不写报告）。
    """
    os.makedirs(out_dir, exist_ok=True)
    progress = checkpoint.Checkpoint(os.path.join(out_dir, "progress.json"))
    manifest_path = os.path.join(out_dir, "manifest.json")
    manifest = _load_manifest(out_dir) or {
        "format": fmt,
        "encoding": encoding,
        "delimiter": delimiter if fmt == "csv" else None,
        "chunk": chunk,
        "shards": [],
    }
    shard_entries = {entry["index"]: entry for entry in manifest["shards"]}

    skipped = []
    written = 0
    interrupted = False

    def handle_shard(index, rows):
        nonlocal written, interrupted
        if progress.is_done(index):
            skipped.append(index)
            return False
        filename = shards_mod.shard_filename(index, fmt)
        path = os.path.join(out_dir, filename)
        if fmt == "csv":
            csvwriter.write_shard(path, rows, encoding=encoding,
                                  delimiter=delimiter)
        else:
            jsonlwriter.write_shard(path, rows, encoding=encoding)
        shard_entries[index] = {
            "index": index,
            "path": filename,
            "rows": len(rows),
            "sha256": verify_mod.sha256_file(path),
        }
        manifest["shards"] = [
            shard_entries[i] for i in sorted(shard_entries)
        ]
        checkpoint.write_json_atomic(manifest_path, manifest)
        # 批量提交：整片写完、校验入清单后，一次性把该片标记完成
        progress.mark_done(index)
        written += 1
        if max_shards is not None and written >= max_shards:
            interrupted = True
            return True
        return False

    buffer = []
    index = 0
    stop = False
    for row in reader.read_rows(source):
        buffer.append(row)
        if len(buffer) == chunk:
            stop = handle_shard(index, buffer)
            index += 1
            buffer = []
            if stop:
                break
    if buffer and not stop:
        handle_shard(index, buffer)

    if interrupted:
        return {"interrupted": True, "written": written, "skipped": skipped}

    report = report_mod.build_report(list(shard_entries.values()), skipped)
    checkpoint.write_json_atomic(os.path.join(out_dir, "report.json"), report)
    return {"interrupted": False, "written": written, "report": report}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="export.cli",
        description="分片导出工具（CSV / JSONL，支持断点续导）",
    )
    parser.add_argument("--source", help="来源 JSONL 文件路径")
    parser.add_argument("--out", required=True, help="导出目录")
    parser.add_argument("--chunk", type=int, default=1000, help="每片条数")
    parser.add_argument("--format", choices=FORMATS, default="csv",
                        help="输出格式")
    parser.add_argument("--encoding", choices=ENCODINGS, default="utf-8",
                        help="输出编码")
    parser.add_argument("--delimiter", default=",",
                        help="CSV 分隔符（单字符）")
    parser.add_argument("--verify", action="store_true",
                        help="只校验 --out 目录的校验清单，不导出")
    parser.add_argument("--max-shards", type=int, default=None,
                        help="（测试用）写够 N 个新分片后模拟中断")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.verify:
        mismatches = verify_mod.verify_manifest(args.out)
        if mismatches:
            for item in mismatches:
                print("分片 %(index)s 不匹配: %(reason)s" % item)
            print("校验失败：%d 个分片不一致" % len(mismatches))
            return 1
        print("校验通过：所有分片与校验清单一致")
        return 0

    if not args.source:
        build_parser().error("导出模式必须提供 --source")
    if args.chunk <= 0:
        build_parser().error("--chunk 必须为正整数")
    if len(args.delimiter) != 1:
        build_parser().error("--delimiter 必须是单个字符")

    result = run_export(
        args.source, args.out, chunk=args.chunk, fmt=args.format,
        encoding=args.encoding, delimiter=args.delimiter,
        max_shards=args.max_shards,
    )

    if result["interrupted"]:
        print("导出中断：本次新完成 %d 个分片，重跑同一命令即可续导"
              % result["written"])
        return 0

    report = result["report"]
    print("导出完成，统计摘要：")
    print("  分片数: %d" % len(report["shards"]))
    print("  总行数: %d" % report["total_rows"])
    print("  本次新导出: %d 片, 跳过(已完成): %s"
          % (result["written"], report["skipped"]))
    print("  总 sha256: %s" % report["total_sha256"])
    print("  报告文件: %s" % os.path.join(args.out, "report.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""export 包的验收测试，逐条覆盖任务判定口径。

运行方式（仓库根目录）：
    cd tests && python -m unittest test_export -v
或：
    python -m unittest discover -s tests -v
"""

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from export import verify  # noqa: E402
from export.report import total_sha256  # noqa: E402
from export.shards import shard_filename  # noqa: E402

ROW_COUNT = 1000
CHUNK = 100
SHARD_COUNT = 10
SPECIAL_INDEX = 123
SPECIAL_NOTE = '字段里带,逗号、"双引号" 和\n换行符的一行'


def make_source_rows(count=ROW_COUNT):
    """按固定规则构造来源数据：1000 行，至少一行含逗号/引号/换行。"""
    rows = []
    for i in range(count):
        rows.append({
            "id": i,
            "name": "user_%04d" % i,
            "note": "普通备注 %d" % i,
            "score": i % 9,
        })
    rows[SPECIAL_INDEX]["note"] = SPECIAL_NOTE
    return rows


def write_source(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False))
            fh.write("\n")


def stringify(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


class ExportTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = os.path.join(self.tmp.name, "source.jsonl")
        self.rows = make_source_rows()
        write_source(self.source, self.rows)
        self.out = os.path.join(self.tmp.name, "out")

    def run_cli(self, *extra_args, expect_code=0):
        cmd = [sys.executable, "-m", "export.cli",
               "--source", self.source, "--out", self.out,
               "--chunk", str(CHUNK)] + list(extra_args)
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True,
                                text=True)
        self.assertEqual(result.returncode, expect_code,
                         msg="stdout=%s stderr=%s"
                             % (result.stdout, result.stderr))
        return result

    def read_report(self):
        with open(os.path.join(self.out, "report.json"),
                  encoding="utf-8") as fh:
            return json.load(fh)

    def read_csv_shard(self, index, encoding="utf-8", delimiter=","):
        path = os.path.join(self.out, shard_filename(index, "csv"))
        with open(path, "r", encoding=encoding, newline="") as fh:
            return list(csv.DictReader(fh, delimiter=delimiter))

    # 口径 1+2：1000 行来源（含特殊行），导出正好 10 片、每片 100 行、
    # 总行数 1000，且内容与来源逐行一致。
    def test_01_csv_shards_count_rows_and_content(self):
        self.assertEqual(len(self.rows), ROW_COUNT)
        self.assertIn("\n", self.rows[SPECIAL_INDEX]["note"])
        self.run_cli("--format", "csv")

        files = sorted(f for f in os.listdir(self.out) if f.endswith(".csv"))
        self.assertEqual(len(files), SHARD_COUNT)

        report = self.read_report()
        self.assertEqual(len(report["shards"]), SHARD_COUNT)
        self.assertEqual(report["total_rows"], ROW_COUNT)
        for entry in report["shards"]:
            self.assertEqual(entry["rows"], CHUNK)

        for index in range(SHARD_COUNT):
            parsed = self.read_csv_shard(index)
            expected = self.rows[index * CHUNK:(index + 1) * CHUNK]
            self.assertEqual(len(parsed), CHUNK)
            for got, want in zip(parsed, expected):
                for key, value in want.items():
                    self.assertEqual(got[key], stringify(value),
                                     msg="shard %d key %s" % (index, key))

    # 口径 3：CSV 下带引号/逗号/换行的行解析回来必须与原值完全相同。
    def test_02_csv_special_field_roundtrip(self):
        self.run_cli("--format", "csv")
        shard_index = SPECIAL_INDEX // CHUNK
        parsed = self.read_csv_shard(shard_index)
        got = [row for row in parsed if row["id"] == str(SPECIAL_INDEX)]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["note"], SPECIAL_NOTE)

    # 口径 4：导到第 4 片中断，重跑后仍是 10 片 / 1000 行，
    # 已完成的 4 片内容与时间戳都不变。
    def test_03_resume_after_interruption(self):
        self.run_cli("--format", "csv", "--max-shards", "4")
        done = sorted(os.listdir(self.out))
        self.assertEqual([f for f in done if f.endswith(".csv")],
                         [shard_filename(i, "csv") for i in range(4)])

        snapshot = {}
        for i in range(4):
            path = os.path.join(self.out, shard_filename(i, "csv"))
            with open(path, "rb") as fh:
                snapshot[i] = (fh.read(), os.stat(path).st_mtime_ns)

        self.run_cli("--format", "csv")

        files = [f for f in os.listdir(self.out) if f.endswith(".csv")]
        self.assertEqual(len(files), SHARD_COUNT)
        report = self.read_report()
        self.assertEqual(report["total_rows"], ROW_COUNT)
        self.assertEqual(report["skipped"], [0, 1, 2, 3])

        for i in range(4):
            path = os.path.join(self.out, shard_filename(i, "csv"))
            with open(path, "rb") as fh:
                content = fh.read()
            self.assertEqual(content, snapshot[i][0],
                             msg="shard %d 内容被重写" % i)
            self.assertEqual(os.stat(path).st_mtime_ns, snapshot[i][1],
                             msg="shard %d 时间戳变了" % i)

    # 口径 5：校验清单与实际文件一致；篡改某片后校验必须报不匹配。
    def test_04_manifest_matches_and_detects_tampering(self):
        self.run_cli("--format", "csv")
        with open(os.path.join(self.out, "manifest.json"),
                  encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.assertEqual(len(manifest["shards"]), SHARD_COUNT)
        for entry in manifest["shards"]:
            path = os.path.join(self.out, entry["path"])
            self.assertEqual(entry["sha256"], verify.sha256_file(path))
            self.assertEqual(
                entry["rows"],
                verify.count_rows(path, "csv", "utf-8", ","))
        self.assertEqual(verify.verify_manifest(self.out), [])

        victim = os.path.join(self.out, shard_filename(3, "csv"))
        with open(victim, "a", encoding="utf-8") as fh:
            fh.write("tampered\n")
        mismatches = verify.verify_manifest(self.out)
        self.assertEqual([m["index"] for m in mismatches], [3])

        result = subprocess.run(
            [sys.executable, "-m", "export.cli", "--out", self.out,
             "--verify"],
            cwd=REPO_ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("3", result.stdout)

    # 口径 6：JSONL 每行一个独立 JSON 对象，条数与来源相同。
    def test_05_jsonl_export(self):
        self.run_cli("--format", "jsonl")
        files = sorted(f for f in os.listdir(self.out)
                       if f.endswith(".jsonl"))
        self.assertEqual(len(files), SHARD_COUNT)

        decoded = []
        for name in files:
            with open(os.path.join(self.out, name),
                      encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        obj = json.loads(line)
                        self.assertIsInstance(obj, dict)
                        decoded.append(obj)
        self.assertEqual(len(decoded), ROW_COUNT)
        self.assertEqual(decoded, self.rows)

    # 口径 7：报告四段齐全；续导时 skipped 列出跳过的分片编号。
    def test_06_report_fields_and_skipped(self):
        self.run_cli("--format", "csv")
        report = self.read_report()
        for key in ("shards", "total_rows", "total_sha256", "skipped"):
            self.assertIn(key, report)
        self.assertEqual(report["skipped"], [])
        expected_total = total_sha256(
            [entry["sha256"] for entry in report["shards"]])
        self.assertEqual(report["total_sha256"], expected_total)

        out2 = os.path.join(self.tmp.name, "out2")
        self.out = out2
        self.run_cli("--format", "csv", "--max-shards", "4")
        self.run_cli("--format", "csv")
        report2 = self.read_report()
        self.assertEqual(report2["skipped"], [0, 1, 2, 3])
        self.assertEqual(report2["total_rows"], ROW_COUNT)
        self.assertEqual(len(report2["shards"]), SHARD_COUNT)

    # 附加：编码（gbk）与分隔符（;）可配，且特殊字段仍可往返。
    def test_07_configurable_encoding_and_delimiter(self):
        self.run_cli("--format", "csv", "--encoding", "gbk",
                     "--delimiter", ";")
        shard_index = SPECIAL_INDEX // CHUNK
        parsed = self.read_csv_shard(shard_index, encoding="gbk",
                                     delimiter=";")
        got = [row for row in parsed if row["id"] == str(SPECIAL_INDEX)]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["note"], SPECIAL_NOTE)
        self.assertEqual(verify.verify_manifest(self.out), [])


if __name__ == "__main__":
    unittest.main()

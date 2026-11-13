"""断点进度记录：progress.json 原子替换写入。

每导完一个分片，把该片编号一次性标记进进度文件（批量提交，
不逐行标记）。中断后重跑时，已完成的分片直接跳过。
"""

import json
import os
import tempfile


def write_json_atomic(path, payload):
    """先写临时文件再 os.replace，保证进度文件任一时刻要么旧要么新。"""
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-",
                                    suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class Checkpoint:
    """记录已完成分片编号的进度文件。"""

    def __init__(self, path):
        self.path = path
        self.completed = set()
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.completed = set(data.get("completed", []))

    def is_done(self, index):
        return index in self.completed

    def mark_done(self, index):
        """把一个完整分片标记为完成并立即落盘（原子替换）。"""
        self.completed.add(index)
        write_json_atomic(self.path, {"completed": sorted(self.completed)})

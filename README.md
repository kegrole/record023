# export：分片导出工具

纯 Python 标准库实现，把 JSONL 来源数据按固定条数分片导出为 CSV 或
JSONL，支持断点续导、逐片校验与总校验。

## 快速开始

    # 导出（demo 入口）
    python -m export.cli --source demo/rows.jsonl --out out/export --chunk 100

    # 指定格式 / 编码 / 分隔符
    python -m export.cli --source demo/rows.jsonl --out out/export \
        --chunk 100 --format jsonl --encoding gbk --delimiter ";"

    # 只校验已有导出
    python -m export.cli --out out/export --verify
    python -m export.verify --out out/export

    # 重新生成 demo 来源数据（确定性，1000 行）
    python demo/make_rows.py

    # 跑测试
    cd tests && python -m unittest test_export -v

## 分片语义

- 分片边界只由行号与 --chunk 决定：第 i 片覆盖来源行
  [i*chunk, (i+1)*chunk)，与数据内容无关；重新生成同样的来源数据
  再跑，分片边界与校验值必然一致。
- 分片文件命名为 shard-00000.csv / shard-00000.jsonl，编号从 0 开始。
- 流式读取来源，内存中只缓冲一个分片的行。

## 断点续导语义

- 每导完一个分片，先把该片的 rows/sha256 写入 manifest.json，再把
  该片编号一次性记入 progress.json（批量提交，不逐行标记）。
- progress.json 与 manifest.json 都是原子替换写入（临时文件 +
  os.replace），中断不会留下半个文件。
- 重跑同一命令时，progress.json 里已完成的分片直接跳过（不重写
  文件），只补没导完的分片；跳过的编号会进报告的 skipped 段。

## 两种格式的转义规则

### CSV

- 遵循 RFC 4180（标准库 csv 模块）：字段含分隔符、双引号或换行时
  整体用双引号包围；字段内的双引号写成两个；换行原样保留在被
  引号包围的字段内。
- 首行为表头（字段名按首次出现顺序取并集）；rows 统计不含表头。
- 分隔符由 --delimiter 指定（单字符，默认逗号）。

### JSONL

- 每行一个独立 JSON 对象（json.dumps, ensure_ascii=False），
  特殊字符由 JSON 自身的转义负责。

两种格式的输出编码都由 --encoding 指定（utf-8 或 gbk）。

## 校验清单格式

manifest.json（每片写完即更新）：

    {
      "format": "csv",
      "encoding": "utf-8",
      "delimiter": ",",
      "chunk": 100,
      "shards": [
        {"index": 0, "path": "shard-00000.csv", "rows": 100,
         "sha256": "<该片文件内容的 sha256>"}
      ]
    }

report.json（全部分片完成后写出）：

    {
      "shards": [同上逐片条目],
      "total_rows": 1000,
      "total_sha256": "<逐片 sha256 按编号升序拼接后再取 sha256>",
      "skipped": [因已完成而跳过的分片编号]
    }

行数统计口径：CSV 用解析器数（字段内换行不算新行）且不含表头；
JSONL 按非空行数。sha256 均按文件字节计算。

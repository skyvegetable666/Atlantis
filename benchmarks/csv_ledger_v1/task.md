# 修复 CSV 账单统计程序

任务编号：`csv-ledger-repair-v1`。Python 3.11+，仅使用标准库。

## 交付目标

修复 `ledgerlab`，使它按照以下规范读取账单、筛选并汇总金额、输出 JSON 报告。提交完整的 `ledgerlab/` 目录，保留公开函数与命令行接口。

工作区还提供 `public_tests/`。可以增加自己的测试；公开测试仅覆盖部分要求。最后使用独立用例评价相同规范下的行为。

在工作区根目录运行：

```sh
python3 -m unittest discover -s public_tests -v
python3 -m ledgerlab examples/basic.csv
python3 -m ledgerlab examples/basic.csv --start 2026-01-02 --end 2026-01-02
```

## 1. CSV 读取

接口：`ledgerlab.reader.read_records(text: str) -> list[dict]`。

输入使用 CSV 格式，表头必须恰好为 `date,category,amount`，顺序固定；除允许文本开头的 UTF-8 BOM 外，表头不做空格清理。空字符串、只有空行的文本、只有合法表头时返回空列表。空行忽略；有内容的数据行必须恰好三列。带引号的类别支持逗号与引号。CSV 格式错误时抛出 `ValueError`。

三列的值先去掉首尾空白，然后按以下规则解释：

- `date`：严格的 `YYYY-MM-DD` 格式，且是有效公历日期。
- `category`：非空字符串，保留大小写及中间空白。
- `amount`：可选 `+` 或 `-`、至少一个 ASCII 数字、可选小数部分，小数为一位或两位。允许前导零；拒绝指数、千位逗号、下划线、NaN、Infinity 与三位以上小数。

金额转换为整数分，禁止因二进制浮点误差丢失精度。负数代表退款；`-0.00` 转为 `0`。

返回的每条记录只有这三个字段：

```python
{"date": "2026-01-02", "category": "Food", "amount_cents": 113}
```

任一非空行无效时，整个调用抛出 `ValueError`；不能静默跳过错误行或返回部分结果。异常具体文字不限。

## 2. 汇总

接口：`ledgerlab.aggregate.summarize(records: list[dict], start: str | None = None, end: str | None = None) -> dict`。

`records` 使用读取接口生成的结构。`start` 与 `end` 可以独立省略；提供时使用同样的严格日期格式，包含起止两端。起止日期无效或 `start > end` 时抛出 `ValueError`，即使记录列表为空也一样。

按筛选后记录求数量与金额总和；每个类别单独汇总。相同记录重复出现时分别计数。类别区分大小写，按 Python 字符串升序排列；没有入选记录的类别不出现在结果中。

空结果：

```python
{"count": 0, "total_cents": 0, "categories": []}
```

非空结果：

```python
{
    "count": 2,
    "total_cents": 100,
    "categories": [
        {"category": "Food", "count": 1, "total_cents": 113},
        {"category": "Travel", "count": 1, "total_cents": -13}
    ]
}
```

汇总不能修改输入记录或输入列表。

## 3. 报告

接口：`ledgerlab.report.render_report(summary: dict) -> str`。

输入为汇总接口的合法结果。输出可由 `json.loads` 解析的 JSON 文本，只有以下字段；数值字段 `count` 保持整数，所有金额改为精确的两位小数字符串。JSON 对象键顺序、空格和 Unicode 转义方式不限，类别列表顺序保持汇总结果的顺序。

```json
{
  "count": 2,
  "total": "1.00",
  "categories": [
    {"category": "Food", "count": 1, "total": "1.13"},
    {"category": "Travel", "count": 1, "total": "-0.13"}
  ]
}
```

零显示为 `"0.00"`，不能输出 `"-0.00"`；负金额正常保留负号。报告不能修改输入。

## 4. 命令行

接口：`python3 -m ledgerlab INPUT [--start YYYY-MM-DD] [--end YYYY-MM-DD]`。

- 读取 UTF-8 文件，支持文件开头的 BOM。
- 成功时向 stdout 输出上述 JSON 及结尾换行，stderr 为空，退出码为 0。
- 输入文件不存在、无法读取、不是有效 UTF-8、CSV 数据无效或日期区间无效时，stdout 为空，stderr 给出非空错误说明，退出码为 2；不能向用户展示 Python traceback。
- 无记录时成功输出空报告。
- 不访问网络，不使用第三方包，不依赖工作区以外的文件。

## 验收

读取、汇总、报告与命令行四类各占 25 分。每类用例等权，允许记录部分得分；全部必需用例通过才记为通过。测试同时检查模块接口与整体连接，修改公开测试不会改变独立评分。

完成方式由你自行选择。提交的成果必须包含能按上述接口运行的完整项目。

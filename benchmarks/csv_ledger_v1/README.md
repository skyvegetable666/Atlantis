# CSV 账单修复候选任务包

本包用于验证首个非平凡任务的需求与评分。它尚未接入实验调度器，不会改变现有数字统计任务。任务类型、评分与付款条件目前是候选方案，相关工作单见 `docs/issues/001-csv-repair-task.md`。

## 目录与数据归属

| 路径 | 用途 | 居民是否可见 |
| --- | --- | --- |
| task.md | 完整需求、固定接口、通过条件 | 是 |
| starter/ | 带缺陷的初始项目与示例输入 | 是 |
| public_tests/ | 可运行的公开示例测试 | 是 |
| evaluator/ | 独立用例、评分与开发运行器 | 否 |
| reference/ | 供开发者验证评分器的参考修复 | 否 |
| manifest.json | 候选版本、文件 SHA-256 | 否 |
| verify.py | 公开投影与可信 fixture 验证工具 | 否 |

“不可见”指居民的工作区和模型观察；本地项目开发者仍能查看这些文件。正式运行需要按白名单导出工作区，不能挂载整个项目目录。

## 开发验证

从 Atlantis 项目根目录执行：

```sh
python3 -B benchmarks/csv_ledger_v1/verify.py
python3 -B benchmarks/csv_ledger_v1/evaluator/run.py --fixture reference
python3 -B benchmarks/csv_ledger_v1/evaluator/run.py --fixture starter
```

原始版本评分未通过时，最后一条命令按约定退出 1。参考修复应为 100 分；verify 同时检查原始版本有部分分、两种版本重复评分一致，并逐一重新引入读取、汇总、报告、命令行缺陷，确认相应组分下降。

评分器以固定输入和期望值检查输出，不使用参考实现计算答案。四类各 8 项、各占 25 分；一项包含多个边界检查时必须全部通过才计分。函数输入也检查未被修改。总分等于各组得分之和，所有项通过才为 passed。

开发运行器仅接受 starter 和 reference 两个仓库内可信 fixture，不接受居民提交目录。子进程与超时不构成代码隔离；该运行器尚不是可以处理不可信代码的 EvaluationPort。下一阶段需要在获授权的隔离工作区执行代码、隔离独立测试及参考答案，并通过控制器登记成果与用量。

## 导出居民可见材料

传入一个尚不存在的新目录：

```sh
python3 -B benchmarks/csv_ledger_v1/verify.py --export-public .atlantis/csv-task-preview
cd .atlantis/csv-task-preview
python3 -B -m unittest discover -s public_tests -v
```

导出使用固定文件白名单，不复制评测器、参考实现、任务包开发文档或运行配置。默认导出带缺陷的初始项目，公开测试失败是预期结果；不修改来源文件或已有目标目录。

## 版本管理

修改本候选包后，由开发者重新验证并更新 manifest：

```sh
python3 -B benchmarks/csv_ledger_v1/verify.py --write-manifest
python3 -B benchmarks/csv_ledger_v1/verify.py
```

正式实验开始前需冻结任务、用例、计价、模型及运行限制。正式版本的内容变化应创建新版本，不能通过重写 manifest 让历史实验变成另一套条件。

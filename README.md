# Atlantis

用于观察 AI 居民独立工作、通信和委托的本地实验台。当前是可运行的模块化原型。

需要 Python 3.11 或更新版本；当前版本只使用标准库，无需安装依赖。

## 启动

在本项目目录运行：

```sh
python3 -m atlantis serve --port 8765
```

打开 http://127.0.0.1:8765 。新建实验，再点击“启动实验”；后台控制器持续调度，关闭浏览器不会停止实验。使用 Ctrl+C 停止服务，重启后未结束的实验保持暂停。

命令行也能运行和检查：

```sh
python3 -m atlantis run --mode demo --agents 2
python3 -m atlantis run --mode live --agents 1 --max-calls 8
python3 -m atlantis list
python3 -m atlantis inspect RUN_ID
python3 -m unittest discover -s tests -v
```

修改前端时另运行 `node --test tests/test_web.cjs`（需要 Node.js 22 或更新版本），验证费用汇总、动作结果和行为摘要。

运行数据保存在 `.atlantis/city.db`，已排除在 Git 之外。使用 `python3 -m atlantis --db OTHER_PATH serve` 可以隔离数据。

## 两种执行方式

| 方式 | 作用 | 能证明什么 |
| --- | --- | --- |
| demo | 本地脚本安排一次协作与结算 | 验证模块接口和完整流程 |
| live | 真实模型根据相同规则自主决策 | 观察这次运行的行为和交付；需要独立重复实验才能比较效果 |

真实模型通过 `.env` 或环境变量配置 `ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_MODEL`。当前适配器使用现有网关的 Messages 流式协议。配置只在服务端读取，页面和居民观察中没有密钥。`.env` 已在 `.gitignore` 中。

原型第一种工作是对公开数字列表产生 `count`、`sum`、`min`、`max` 的 JSON 成果。工作工具仅支持有限的统计计算；没有任意代码执行、外部收款或任意文件访问。

首个代码修复候选任务包见 [benchmarks/csv_ledger_v1/README.md](benchmarks/csv_ledger_v1/README.md)，本地工作单见 [docs/issues/001-csv-repair-task.md](docs/issues/001-csv-repair-task.md)。包内包含需求、初始项目、公开测试、独立用例与参考修复；尚未接入居民运行工具。运行 `python3 -B benchmarks/csv_ledger_v1/verify.py` 可验证材料及评分器。

## 模块

```text
web/                  研究者界面，仅访问实验 API
server.py             本地 HTTP 入口与后台调度循环
controller.py         观察、决策、执行、评测的流程编排
runtime.py            Observation -> ModelReply，无城市或存储依赖
city.py               身份校验、动作分派、跨模块事务与事件
domain/               任务、账户、通信、成果等规则
contracts.py          数据契约与可替换的执行、评测、存储接口
adapters/             脚本模型、模型网关、统计工具与独立评分
storage.py            SQLite 事务与带版本的实验快照
bootstrap.py          统一装配具体实现
```

接口与失败行为见 [docs/contracts.md](docs/contracts.md)。临时实现选择见 [docs/implementation.md](docs/implementation.md)。项目目标与已确认范围见 [design.md](design.md)。

## 当前边界

- 支持 1 或 2 名居民、公共群、私聊、付费委托、成果、付款和独立评分。
- 原型按每次模型或工具尝试 1 credit 扣除内部费用；这是可配置的临时计价。托管与调用预留不会重复花费。
- 调用次数、单次输出和观察大小有上限。真实供应商货币费用尚未核实，显示“待确认”；调用次数上限不等于货币预算上限。
- 演示的合作是预先编排的。真实模式没有预设领导、分工或合作要求。
- 进程中断时，已发出但结果未知的调用会保留预留并阻止自动重放；当前需要人工核查。没有自动对账和异常调用恢复界面。
- 尚未实现通用超时、返工与退款策略；主任务评分失败时保留任务及托管资金供检查。M1 的完整费用核实和 M3 的对照实验尚未完成。

## GitHub 开发方式

本地 Git 仓库已初始化；未创建远程仓库、提交或推送。仓库包含模块 Issue 模板、PR 模板和自动测试工作流。

建议每项工作先写 Issue，注明接口、约束和验收；在独立分支实现，经 PR 检查后合入。初次发布前先确定仓库名称、可见性和许可证。

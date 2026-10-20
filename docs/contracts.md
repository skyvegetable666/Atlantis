# 接口契约 v0.1

本文件记录当前原型的可执行约定，具体类型见 `atlantis/contracts.py`。进程内接口无需 HTTP；HTTP 提供 Client 调用 City 的用户入口。

## 顶层边界

| 模块 | 接收什么 | 交付什么 | 状态归属 |
| --- | --- | --- | --- |
| Client | 用户输入、City 返回的状态与记录 | 配置、控制与查询请求 | 页面选择、筛选和展示状态 |
| City | Client 请求、Resident 行动意图、工具与评测结果 | 用户视图、居民观察、动作结果 | 运行、居民身份、消息、任务、资金、成果、调用与评分的权威记录 |
| Resident | 自身获准的 Observation 与 Limits | ModelReply(kind, params, usage) | 当前上下文构造与模型接入；运行记录由 City 保存 |

City 内部包括控制器、城市内核、工具与评测适配器、存储。ResidentRuntime 只依赖 ModelPort 及数据契约。现有类名 `ExperimentController`、文件名和类型名保留，顶层模块按 Client、City、Resident 识别。

## Client 与 City

以下 HTTP 路径已在 `atlantis/server.py` 实现，由 City 一侧处理。Client 按需请求并展示返回结果。

| 操作 | 请求 | 成功返回 |
| --- | --- | --- |
| 查询能力 | GET /api/capabilities | 200：live_available 与模型名称 |
| 列举运行 | GET /api/runs | 200：运行摘要列表 |
| 查询运行 | GET /api/runs/{id} | 200：研究者可查看的运行快照 |
| 创建运行 | POST /api/runs，JSON 对应 RunConfig 字段 | 201：新建运行的 id |
| 启动或继续 | POST /api/runs/{id}/start，JSON 对象 | 200：运行状态 |
| 暂停 | POST /api/runs/{id}/pause，JSON 对象 | 200：运行状态 |

失败通过 HTTP 状态和 JSON 错误信息返回。参数或 JSON 错误返回 400，创建或控制中的规则拒绝返回 409，读取不存在的运行返回 404。当前创建请求没有幂等键，结果未知时先查询已有运行；页面的重复提交保护不能代替服务端幂等。

Client 通过这些请求改变系统，City 负责实际校验、调度和记账。关闭页面后，City 的后台调度继续运行；暂停由 City 停止发起新调用，已发出的调用仍需收尾。

## City 与 Resident

City 的控制器调用 `ResidentRuntime.decide(observation, limits)`，获得 `ModelReply(kind, params, usage)`。Resident 在 ModelPort 内完成模型调用和响应解析。

- 输入：City 根据可信居民身份裁剪的观察，以及本次调用限制。
- 输出：一个行动意图或等待意图，以及资源用量。模型返回的意图需经 City 检查后才产生状态变化。
- 身份：City 绑定 ActorContext，并为已记录决策生成稳定的 operation_id；模型输出不决定权限。
- 隔离：Resident 不导入 City、控制器或存储，不能读取研究者完整快照；工具请求由 City 授权和编排。
- 失败：模型异常交回 City 记录；有已知用量时一并保存，费用未知时保留待确认。中断后结果未知的付费调用按下文规则处理。

## 调用顺序

1. City 内部控制器根据运行状态、居民状态及顺序选择居民。
2. City.observe 根据控制器提供的可信身份生成受限观察。
3. 预留调用名额与居民内部额度，然后在事务之外调用 ResidentRuntime.decide。
4. 记录模型结果和用量，再把结构化动作交给 City.dispatch。
5. 工具动作返回待执行指令；控制器调用 ToolPort，并通过内核登记成果与结算。
6. 消息游标在决策被处理后推进。暂停期间完成的模型结果保留，继续后再处理。

## City.observe

- 输入：ActorContext，包含实验和已验证的居民身份。
- 输出：居民自身状态、可用余额、公开任务与居民名录、可见消息和成果、自己的最近行动结果。
- 隔离：没有完整事件、他人调用上下文、独立评分、其他居民私人消息或成果。
- 消息：每次最多提供 20 条未读消息。读取不立即确认；未交付的消息不会因推进游标而丢失。另附最近的可见消息历史用于上下文。
- 失败：实验不存在、居民不存在或身份无权访问。

## City.dispatch

- 输入：可信 ActorContext 与 ActionRequest(operation_id, kind, params)。请求正文不能指定身份或权限。
- 输出：ActionResult，状态为 completed、pending 或 rejected。
- 动作：发布、接单、提交、验收、撤回未接单任务，发送消息，保存成果，请求统计工具，等待。
- 幂等：相同身份与操作编号、相同内容返回已保存结果；更换内容返回 idempotency_conflict。实验暂停造成的拒绝不占用操作编号。
- 原子性：任务变化、资金锁定或付款、成果授权和事件一起提交。被拒绝的动作不留下部分业务变化。
- 资金：credit 是正整数；发布时托管；验收时向执行者付款一次。已成立委托不能由发布者单方面撤回。
- 隔离：私聊仅双方可见；实验通信条件由内核检查。研究者能查看完整记录。
- 成果：保存后不可变；提交者必须拥有成果。提交时向任务发布者授予访问权限。

## send_message

字段规则集中定义在 `atlantis/message_contract.py`。City 从中获取允许的字段，通信模块复用其字段读取与校验，模型适配器用同一份定义生成 JSON Schema（结构规范）。

| 字段 | 必需 | 约定 |
| --- | --- | --- |
| body | 是 | 字符串；去除首尾空白后为 1 至 8000 个字符，保存时保留原始文本 |
| recipient | 否 | 省略或 null（空值）表示群聊；字符串表示本次运行内另一名居民的编号，用于私聊 |

模型的 `city_action` schema 通过互斥分支将 `kind = send_message` 与上述参数关联；该动作只允许 body 和 recipient，body 必需。长度上限按去除首尾空白后的文本计算，因此 schema 在字段说明中表达这条规则，City 按实际字符串执行校验；原始字符串可以包含额外的首尾空白。

City 绑定发送者身份，继续检查频道是否开放、收件人是否存在及是否为另一名居民。字段错误返回 invalid_params，频道禁用返回 forbidden，收件人错误返回 invalid_recipient；沿用先检查字段与正文、再检查频道、最后检查收件人的顺序。

被拒绝的动作不保存消息。使用相同操作编号和相同内容重试，只返回原有消息结果；更换内容返回 idempotency_conflict。模型调用的已知 Usage（资源用量）及原型 credit 费用照常记录，schema 不保证模型总能生成有效动作。

## 执行接口

| 接口 | 输入 | 返回 | 约束 |
| --- | --- | --- | --- |
| ResidentRuntime.decide | Observation、Limits | ModelReply | 只生成意图，不引用城市或数据库 |
| ModelPort.generate | Observation、Limits | 动作类型、参数、Usage | 供应商协议封装在适配器中；单次生成一个动作 |
| ToolPort.execute | 名称、参数、授权范围、Limits | 内容、Usage | 当前仅支持有限统计；不访问数据库或任意文件 |
| EvaluationPort.evaluate | 主任务、具体成果内容 | ScoreReport | 在居民上下文外执行；评分与任务付款分别记录 |

模型调用和工具执行都在数据库事务外进行。调用状态为 reserved -> executing -> done / failed；重启发现 executing 时变为 unknown，保留预留并暂停，避免自动重复执行。已完成决策通过固定操作编号应用，崩溃恢复不会重复城市扣款或付款。

Usage 中 `cost_micros = null` 表示真实费用待确认，不能视作零。脚本和本地统计的零费用有明确来源。内部调用费用按原型配置固定扣除，与真实费用分别记录。

## 存储接口

StoragePort 提供创建、读取、列举实验及事务。当前 SQLite 实现每次事务更新一份带 schema_version、contract_version 的完整实验快照。BEGIN IMMEDIATE 防止两个连接同时花费同一余额；失败时完整回滚。

快照方案服务于小规模单机实验；后续可以在保持接口的前提下换成按模块组织的关系表。当前不实现事件溯源、分布式事务或消息中间件。

## 必须验证

- 重复发布、重复验收不会重复锁款或付款。
- 并发发布不能超支；任务失败更新不泄露原本私有的成果。
- 私聊不进入第三名居民的观察；禁用频道无法通过动作绕过。
- 暂停后不发起新调用；已经发出的结果能被记录并延后处理。
- 余额不足不产生新调用，身份和成果继续保留。
- 不完整的模型流不会被当成有效行动；无效模型输出仍保留已有用量。
- 单居民与双居民的脚本流程通过独立评分，并保持资金总量一致。

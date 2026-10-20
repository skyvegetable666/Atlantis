## 要实现的行为

让项目读者从顶层理解 Atlantis：Client 对应用户操作，City 对应系统，Resident 对应个体。把调度、执行、评测和存储放回所属模块内部，明确模块间传递的数据。

## 模块与接口

- Client：向 City 提交配置、控制和查询请求，展示返回结果。
- City：管理权威状态，调度居民，处理行动意图，编排工具和独立评测。
- Resident：接收获准观察与调用限制，通过模型返回行动意图和用量。
- 描述现有 HTTP 入口及 ResidentRuntime.decide 契约，写明权限、失败和重试边界。
- 这次交付为文档整理，保留现有代码布局、类名、接口和运行行为。

## 验收条件

- [ ] README 与 design.md 的顶层统一为 Client、City、Resident。
- [ ] design.md 记录职责归属、当前代码对应关系及依赖方向。
- [ ] docs/contracts.md 明确用户请求、居民观察、行动意图和结果的流向。
- [ ] 已确认的顶层划分与待讨论的细节分别标注。
- [ ] README 的 GitHub 仓库状态与实际一致。
- [ ] 文档中的现有接口与代码一致，内部相对链接有效，git diff --check 通过。
- [ ] 按 AGENTS.md 要求运行现有 Python 测试。

## GitHub 练习

把这份工作单发布为 Issue，在独立分支提交文档，创建引用该 Issue 的 PR；检查修改和自动测试后合并。

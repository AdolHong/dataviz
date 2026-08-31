# Dataviz 实施计划

更新时间：2026-08-31

稳定设计见 [DESIGN](DESIGN.md)，代码入口见 [当前实现索引](docs/product-architecture.md)，使用者入口见 [README](README.md)，已完成的版本工作见 [CHANGELOG](CHANGELOG.md)。本文件只记录当前基线、尚未完成的工作与按真实需求触发的候选项，不再重复保存历史迁移清单。

## 当前基线

| 领域 | 状态 | 当前结论 |
| --- | --- | --- |
| 数据执行架构 | 已完成 | Query DAG、Interactive DAG、Control/View 影响关系、Named Output、两种 Interactive Runtime、状态隔离和导出边界共用一份版本化 Dependency Contract。 |
| Control 与 Linked Views | 已完成 | `{value, revision, intent?}` 是统一 Control state；Control Panel、Plotly、Table、Custom Renderer、tab 恢复、HTML 与两种 Interactive Runtime 共用 reducer，View selection gesture 只是 writer。 |
| Input State / Consumer Binding | 已完成 | Query Parameter 与 Control 保留两个生命周期入口并共用 typed state；Control 删除 `kind`，View/Interactive Transform 通过 `control_inputs.mode: filter | value` 显式消费。 |
| Layout 与最终配置 | 已完成 | Dashboard v11 拥有结构；Layout Contract v1、Semantic Validation、`inspect layout`、Server、HTML 与 AI context 使用同一编译结果。 |
| Renderer 与组件 | 当前范围已完成 | Plotly 是唯一作者图表接口；普通 Table 使用 TanStack Table Core；Perspective 只用于终端用户现场多维探索；21 个 Component Package 均为 package-owned。 |
| AI Analysis Plane | 当前范围已完成 | `catalog → run → result → evidence`、物理 Target Reference、不可变 Result、Overlay、Evidence 与 Promote dry-run 已落地。 |
| AI 开发效率评测 | 工具完成，真实试验暂缓 | 维护者评测工具已与正式产品隔离；没有真实成对试验前不发布 Token 或效率结论。 |
| 规模与浏览器可靠性 | 当前范围已完成 | 固定 10K/100K/1M 基准和三浏览器契约矩阵已有可复现证据；快速迭代发布默认执行 Chromium 全套，稳定发布、跨浏览器敏感变更或明确要求时再执行 Firefox/WebKit。 |
| Query Parameter 与 Domain | 当前范围已完成 | Query 前置 Domain 提供有界候选、同表多字段去重与直接级联；成功 Query 封存 `{values, intents}`，Revert 通过当前拓扑事务式恢复并保留 unavailable committed value，不执行 Query。候选过多时重构参数或使用 `multiple_input`。 |
| 当前发行基线 | 0.15.0 本地发行完成 | Input State / Consumer Binding 断代、browser-python 删除、Domain Revert 与三浏览器 Runtime 回归已完成；wheel、sdist、ZIP 均通过独立安装与 `init → strict validate → report` 验收。 |

当前开发基线：Package `0.15.0`、Python 3.11–3.14、Dashboard `dataviz/dashboard/v11`、Parameter Domain `dataviz/parameter-domain/v1`、Presentation `dataviz/presentation/v2`、Source/Dataset/Interactive Transform `v3`、Dependency Contract `v7`、Layout Contract `v1`、State Snapshot `v2`、Browser Runtime `dataviz/runtime/v6`、Component Registry `5.6.0`。这些破坏式契约只接受当前严格字段，不保留旧字段兼容名、自动迁移或第二套 Runtime。

## 当前优先级

### P1：Input State 与 Consumer Binding 重构

- [x] 冻结目标概念：不新增作者可见的通用 `states:`；Query Parameter 与 scoped Control 共用 canonical value、候选型集合 intent、revision 和恢复规则，但继续隔离 Query/Interactive 生命周期。
- [x] 冻结最小 binding：projection 只有 `value / present / intent`，consumer mode 只有 `value / filter`；filter 必须声明字段、目标输入与 `empty: passthrough | match_none`，当前不增加 exclude、任意 predicate 或 Filter Group。
- [x] 同步升级 Dashboard v11、Source/Dataset/Interactive Transform v3、Dependency Contract v7、State Snapshot v2 与 Browser Runtime v6：Control 删除 `kind`，`selection_inputs / compute_inputs` 合并为 `control_inputs`，不保留双协议 Runtime。
- [x] 扩展 Query/Control input projection：实现 `present`；候选型集合使用可选 intent，自由集合 `multiple_input` 只保存 list value。
- [x] Compiler 生成唯一 producer/state/consumer binding graph；`inspect dependencies` 展示 mode、projection、field、empty、trigger 与影响闭包，并保持稳定错误码。
- [x] 补齐每个 consumer 的 effective/applied revision 证据：Runtime 原始 `applied_revisions` 由当前 Dependency Contract 规范化为 `consumer_revisions`，State Snapshot、HTML/Share、CLI Browser/Server 执行、Result inspect 与 Evidence 使用同一审计结构；未知或超前 revision 不进入封存事实。
- [x] View/Plotly/Table/Custom Renderer 的点击、框选与行选只发送类型化 writer action；Bound View selected projection 与其他 consumer filter 分离，继续拒绝第二 writer、旧 generation 和反馈循环。
- [x] 一次性迁移示例、Scaffold、CLI docs、`dataviz-skill.md`、分析运行上下文、非浏览器测试与 Chromium/Firefox/WebKit 行为回归，并完成 applied revision 证据收口。

### P2：验证 AI 开发效率

- [x] 正式 CLI 文档和 Scaffold 已按 `minimal / interactive / custom-renderer` 渐进披露；每条路径有独立的 validate/report/visual-check 回归。
- [x] 成对评测实现已迁入独立 [tools/authoring-evaluation](tools/authoring-evaluation/README.md)，不进入正式 `dataviz --help`、README 用户路径或发行归档。
- [ ] 使用相同模型、客户端、权限和时间预算，对五类固定任务执行多次 Dataviz / standalone HTML 随机顺序成对试验。
- [ ] 发布原始 JSONL、环境说明、逐项验收证据、真实 input/output Token、首次成功率、修正轮次和耗时。
- [ ] 根据真实 friction 压缩 focused context、CLI docs 和 Scaffold；不预设固定 Token 上限或节省比例。

### 开源发布

- [ ] 维护者决定许可证并添加正式 `LICENSE`；许可证未定不阻塞本地开发，但阻塞正式对外授权。
- [ ] 添加 `CONTRIBUTING.md`，说明安装、validate/test、Runtime/Component 变更和 PR 验收。
- [ ] 正式 GitHub Release 发布 wheel、sdist、pip ZIP、SHA-256 和远端 CI 记录。

## 按真实需求触发

以下能力不进入当前承诺：

- 通用服务端分页或按需 Record Batch；需要由原始大表 View 的独立基准触发。
- `number-range`、month/quarter/year 日期控件、Transfer、Entity Picker 或 Drawer。
- 多套命名 Presentation、HTML Analysis Capsule、HTML Output 提取或远程分享链接分析。
- 多进程共同写一个 Workspace、内建账号体系、多租户资源配额或不可信代码沙箱。
- 自动 Apply Promote、自动 certified，或绕开人工审阅的知识写回。

## 明确非目标

- 旧实验契约兼容层、自动迁移或双协议 Runtime。
- 可编辑数据逻辑、依赖、布局或样式的通用网页开发器；Mosaic、坐标布局和旧 Widget 协议。
- 让 Python 直接操作 DOM 或成为第二套 View Renderer。
- Interactive Transform 隐式访问 Adapter 或重新查询 Source。
- 为 Analysis Plane 复制 Dependency Contract、Query Executor、InteractionExecutor 或 Browser Runtime。
- 让 AI 通过图像像素反推本可直接读取的 Base/Derived Output。
- 在没有真实需求和证据前增加空接口、Runtime、图表引擎或重复组件。

## Definition of Done

公开能力必须同时具备：严格 Schema 与稳定错误码、`validate` 提前发现、机器可读 CLI 文档、默认样式和扩展 hook、契约与真实浏览器测试、Server/HTML 一致行为、局部更新与状态隔离，以及准确的 README、DESIGN、plan 和 CHANGELOG。

Analysis Plane 还必须证明 Output 语义和可信度可审查、Catalog 可重建且并发安全、CLI 复用 Server/Browser Runtime 的同一执行语义、Result/Evidence 携带可验证 provenance，且 Promote 只产生可 validate 和 Git 审查的普通 Workspace 变更。计划项只有在实现、测试和文档都完成后才能勾选。

# Dataviz 实施计划

更新时间：2026-08-30

稳定设计见 [DESIGN](DESIGN.md)，代码入口见 [当前实现索引](docs/product-architecture.md)，使用者入口见 [README](README.md)，已完成的版本工作见 [CHANGELOG](CHANGELOG.md)。本文件只记录当前基线、尚未完成的工作与按真实需求触发的候选项，不再重复保存历史迁移清单。

## 当前基线

| 领域 | 状态 | 当前结论 |
| --- | --- | --- |
| 数据执行架构 | 已完成 | Query DAG、Interactive DAG、Control/View 影响关系、Named Output、三种 Interactive Runtime、状态隔离和导出边界共用一份版本化 Dependency Contract。 |
| Selection 与 Linked Views | 已完成 | `{intent, values}` 是唯一 Selection 状态；Control Panel、Plotly、Table、Custom Renderer、tab 恢复、HTML 与三种 Interactive Runtime 共用 resolver。 |
| Layout 与最终配置 | 已完成 | Dashboard v9 拥有结构；Layout Contract v1、Semantic Validation、`inspect layout`、Server、HTML 与 AI context 使用同一编译结果。 |
| Renderer 与组件 | 当前范围已完成 | Plotly 是唯一作者图表接口；普通 Table 使用 TanStack Table Core；Perspective 只用于终端用户现场多维探索；21 个 Component Package 均为 package-owned。 |
| AI Analysis Plane | 当前范围已完成 | `catalog → run → result → evidence`、物理 Target Reference、不可变 Result、Overlay、Evidence 与 Promote dry-run 已落地。 |
| AI 开发效率评测 | 工具完成，真实试验暂缓 | 维护者评测工具已与正式产品隔离；没有真实成对试验前不发布 Token 或效率结论。 |
| 规模与浏览器可靠性 | 当前范围已完成 | 固定 10K/100K/1M 基准和三浏览器契约矩阵已有可复现证据；快速迭代发布默认执行 Chromium 全套，稳定发布、跨浏览器敏感变更或明确要求时再执行 Firefox/WebKit。 |
| 0.12.2 发布 | 本地发布完成 | 421 项非浏览器测试、52 项 Chromium E2E、四个 Workspace、21 个 Component Package、三种归档内容审计与独立 Python 3.12 安装冒烟均通过。 |

当前开发基线：Package `0.12.2`、Python 3.11–3.14、Dashboard `dataviz/dashboard/v9`、Presentation `dataviz/presentation/v2`、Source/Dataset/Interactive Transform `v2`、Dependency Contract `v5`、Layout Contract `v1`、State Snapshot `v1`、Browser Runtime `dataviz/runtime/v5`、Component Registry `5.5.0`。这些破坏式契约只接受当前严格字段，不保留旧字段兼容名、自动迁移或第二套 Runtime。

## 当前优先级

### P0：完成 0.12.2 本地发行门禁

- [x] 检查生成资产没有漂移：Canvas Runtime 与 TanStack Table Runtime 均通过构建器 `--check`，生成 JavaScript 通过语法检查。
- [x] 运行 Ruff 与完整 Python 测试套件；失败必须修复或记录为明确阻塞，不能沿用旧版本测试数字。
- [x] 按快速迭代门禁在 Chromium 运行完整 E2E 契约套件；Firefox/WebKit 留给稳定发布、跨浏览器敏感变更或明确要求的发布轮次。
- [x] 对全部示例 Workspace 执行 strict validate，并运行 21 个 Component Package 检查。
- [x] 重新构建 wheel、sdist 与 pip ZIP，审计归档不包含 `.dataviz`、凭据、虚拟环境、维护者评测实现或构建缓存。
- [x] 在干净 Python 3.12 环境完成 `install → version → components → init → validate → report` 冒烟，记录 SHA-256，并确认三种归档均报告 0.12.2。
- [x] 同步 CHANGELOG 的最终门禁结果；以上证据完成后，将 0.12.2 标记为本地发布完成。

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
- 单文件内联 Pyodide、多套命名 Presentation、HTML Analysis Capsule、HTML Output 提取或远程分享链接分析。
- 多进程共同写一个 Workspace、内建账号体系、多租户资源配额或不可信代码沙箱。
- 自动 Apply Promote、自动 certified，或绕开人工审阅的知识写回。

## 明确非目标

- 旧实验契约兼容层、自动迁移或双协议 Runtime。
- 可编辑数据逻辑、依赖、布局或样式的通用网页开发器；Mosaic、坐标布局和旧 Widget 协议。
- 让 Pyodide/Python 直接操作 DOM 或成为第二套 View Renderer。
- Interactive Transform 隐式访问 Adapter 或重新查询 Source。
- 为 Analysis Plane 复制 Dependency Contract、Query Executor、InteractionExecutor 或 Browser Runtime。
- 让 AI 通过图像像素反推本可直接读取的 Base/Derived Output。
- 在没有真实需求和证据前增加空接口、Runtime、图表引擎或重复组件。

## Definition of Done

公开能力必须同时具备：严格 Schema 与稳定错误码、`validate` 提前发现、机器可读 CLI 文档、默认样式和扩展 hook、契约与真实浏览器测试、Server/HTML 一致行为、局部更新与状态隔离，以及准确的 README、DESIGN、plan 和 CHANGELOG。

Analysis Plane 还必须证明 Output 语义和可信度可审查、Catalog 可重建且并发安全、CLI 复用 Server/Browser Runtime 的同一执行语义、Result/Evidence 携带可验证 provenance，且 Promote 只产生可 validate 和 Git 审查的普通 Workspace 变更。计划项只有在实现、测试和文档都完成后才能勾选。

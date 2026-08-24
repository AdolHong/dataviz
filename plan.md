# Dataviz 实施计划

更新时间：2026-08-24

稳定设计见 [DESIGN](DESIGN.md)，代码入口见 [当前实现索引](docs/product-architecture.md)，使用者入口见 [README](README.md)。本文件只保留当前结论和仍需完成的工作，不重复记录历史迁移过程。

## 当前结论

| 领域 | 状态 | 结论 |
| --- | --- | --- |
| P0 数据执行架构 | 已完成 | Query DAG、Interactive DAG、Named Output、三种 Interactive Runtime、状态隔离、导出边界和严格验证已形成一套当前契约。 |
| P1 Component Package | 当前范围已完成 | Registry v3 已覆盖常用 View、Section、Selector、Renderer、Repeat 和 Presentation 组件；继续扩张必须由真实场景触发。 |
| P1 AI 开发效率评测 | 工具已完成，真实试验待进行 | 成对任务、输入完整性、逐项验收和真实 Token 记录均已实现，但不能用仓库测试伪造真实 AI 使用结论。 |
| P2 规模与浏览器矩阵 | 进行中 | 已有 Arrow、局部更新、150K 行回归、七状态 Gallery、真实 10/100/1,000 Selector Story 和三浏览器契约套件；仍缺固定 10K/100K/1M 数据，以及 Firefox/WebKit 的扩展组合矩阵。 |
| 开源发布 | 进行中 | 构建与安装门禁已具备；许可证尚未决定。 |

当前基线：Package `0.3.1`、Python 3.11–3.14、Dashboard `dataviz/dashboard/v3`、Browser Runtime `dataviz/runtime/v2`、Component Registry `3.0.0`。项目尚未投入生产，因此只接受当前严格契约，不保留旧字段 alias、自动迁移或第二套 Runtime。

## 已完成的核心能力

### 数据、计算与状态

- [x] Dashboard v3 只有 Query Parameter 与 scoped Controls 两个入口；Control 在 Dashboard/Section/View 统一声明，并以 `kind: selection | compute` 保留不同 delta、提交周期和失效路径。
- [x] `selection_inputs` 是 Runtime 数据边界而非普通参数；三种 Interactive Runtime 都先对字段契约匹配的表输入应用 include Selection，再进入 Compute 逻辑。
- [x] Source/Dataset Transform 与 Interactive Transform 使用两个 DAG、显式 Named Output、Schema Contract、provenance 和分支级并发。
- [x] 独立分支完成后立即发布；局部失败、超时或取消不会等待或覆盖无关分支。
- [x] `server-python`、`browser-python`、`browser-js` 共用输入、输出、错误、缓存、generation 和 dispose 契约。
- [x] 同一 tab 可恢复状态；不同 tab、Dashboard、用户、Run 和 Interaction generation 相互隔离。
- [x] Query Run Artifact 统一保存在 Workspace `.dataviz/`；可达 Server Interactive 输入在计划阶段显式分类，按 tab + Dashboard + Run + canonical Output 复用且绝不重查 Source。
- [x] SQL 默认 120 秒超时并立即额外重试一次；Dashboard 可覆盖 timeout/retry。

### Runtime 与 HTML Export

- [x] Server 与 HTML 共用 Renderer、Control、Overlay 和内容绑定实现。
- [x] View 具有 ready/loading/stale/empty/error/cancelled/unavailable 终态；取消或失败的 Run 可重新打开检查，不再因缺失 Output 返回 500。
- [x] View 空 descriptor 进入 `empty`，不再永久停在 rendering；Arrow Table 的 Metric 聚合不再显示 `[object Object]`。
- [x] 浏览器聚合改为线性 reducer，150K 行上的 min/max/mean/sum 不再使用会触发 JavaScript 参数上限的 spread。
- [x] HTML Export 明确 `interactive | snapshot | unavailable`；server-python 不伪装成离线交互。
- [x] browser-python 支持 Pyodide CDN 与 `HTML + assets + manifest` bundle；未使用 Pyodide 时不携带相关 Runtime。

### 模板、验证与 AI 入口

- [x] Component Registry v3 提供物理 Package、机器可读 manifest、Story、测试声明、语义 DOM 和 CSS token；`components --check` 检查包结构，行为由 pytest/E2E 实际执行。
- [x] 13 个 Component Package 全部为 package-owned；`data.pipeline`、`view.declarative`、`section.declarative`、`presentation.shell` 已迁出 Runtime bridge，删除 `declarative-runtime.js` 和重复实现。
- [x] Select、Segmented、Checkbox Group、Date Range、Cascader、Tree Select 支持搜索、级联 reconciliation、全选/反选、弹层关闭及基础键盘行为。
- [x] Query 与 Dashboard/Section/View Controls 使用 `control-panel.adaptive`：同一面板按 DATA/LOGIC 分组、默认响应式分栏、视口内滚动，并允许 Presentation 覆盖模板、宽度、列数和密度而不分叉状态逻辑。
- [x] Gallery 提供 Selector、Control、View、Section 的七状态矩阵，以及实际包含 10、100、1,000 个原生选项的 Select Story；1,000 选项搜索覆盖全量且增强 DOM 有界。
- [x] Table/Perspective、Plotly/ECharts、Repeat Small Multiples/Selection Gallery 和自定义 Renderer 都走统一 Runtime 边界。
- [x] `validate` 是零查询静态门禁；`docs`、`schemas`、`components`、`context`、`scaffold` 为新 AI 会话提供当前契约。
- [x] Sources 面板提供参数化 statement、Resolved SQL、bound parameters、Adapter、timeout/retry、hash、日志和结构化错误，不暴露凭证。
- [x] `authoring prepare/verify/assess/start/finish/compare` 固定任务身份、输入哈希、验收证据和真实 Token；缺失 Token 保持 unmeasured。

### 2026-08-24 核心审计与加固

- [x] Workspace 热刷新只发布完整快照；活动 Query worker 保留启动快照，开发态新 Interactive/Presentation 只有在 Query Contract 指纹兼容时才能复用既有 Base Output。
- [x] Scaffold、AI trial、持久缓存、HTML/manifest/assets 与发行 ZIP/checksum 使用预检、原子发布和失败回滚。
- [x] Adapter 配置、Pydantic/YAML 诊断、Python progress/log/traceback 和执行证据统一做凭据脱敏；提交到 Git 的 Adapter 文件拒绝直接凭据。
- [x] Artifact 与缓存命中验证 content hash；大文件改为流式哈希和原子流式复制，不再整文件读入内存。
- [x] Runtime/Output/Pyodide 路径限制在受控根目录；portable Pyodide bundle 拒绝符号链接和不完整依赖闭包。
- [x] 删除重复的公开 `templates` CLI 入口；AI 统一从 `components`、`schemas`、`docs` 和 `scaffold` 发现能力。
- [x] `components --check` 的报告明确只验证 Package 元数据、资产和测试声明，不再暗示已经执行行为测试。
- [x] Interaction endpoint 不再等待整次 Query 完成；快 Base Output 可以驱动 Server/Browser Interactive 分支，Query 终态通过 frame handshake 原地同步而不重载 Canvas。
- [x] Selection-kind、Compute-kind 与 Output delta 明确区分“全部/部分/无变化”；无关 Output 不再重启 active Transform，未变化 Output 不再重复传播或重绘。
- [x] 删除旧 Server capability fallback；导航显示名严格来自 Dashboard 文件夹，运行态不再用页面 title 冒充 Canvas 名称。
- [x] 保留策略保护活动 Query 及其活动 Interaction 仍在消费的 Run/Cache；长计算不再被后台清理误取消。
- [x] wheel、sdist 与 pip 源码 ZIP 均在隔离环境完成 `install → version → components → init → validate → report`；归档不包含 `.dataviz`、本地凭据、虚拟环境或构建缓存。
- [x] 同一 wheel 已在 Python 3.11、3.12、3.13、3.14 完成干净安装与 CLI/报告冒烟；完整 Python 测试矩阵由 CI 持续执行。
- [x] `0.3.1` 修复动态 Selection 启动环：option domain 只来自 Base Output，首次水合、Control reconciliation、View 渲染与 Interactive 调度有唯一顺序；`canvas-ready` 只在首次 canonical state 提交后发布，父页面不再用早到的 tab 状态覆盖初始化中的用户操作。
- [x] Browser Interactive 七状态通过 frame identity 回传 `Pipeline`；Base View 不再因其他动态 Selector 或 Interactive 分支而停在 `Waiting for dataset`，Server 与独立 HTML 均有回归。

## 下一步优先级

### P1：验证 AI 开发效率

这是当前最高优先级的产品证据工作，不需要继续扩张 DSL。

- [ ] 使用相同模型、客户端、权限和时间预算，对五类固定任务执行多次 Dataviz / standalone HTML 随机顺序成对试验。
- [ ] 发布原始 JSONL、环境说明、逐项验收证据、真实 input/output Token、首次成功率、修正轮次和耗时。
- [ ] 根据真实 friction 压缩 focused context、CLI docs 和 Scaffold；不预设固定 Token 上限或节省比例。

评测协议见 [AI Authoring 成对评测](docs/authoring-evaluation.md)。

### P2：规模与性能证据

- [x] Arrow 传输记录行数、字节和耗时；Renderer 记录 mount/update/empty/failure/耗时。
- [x] `benchmark --browser-runtime` 等待传输、Interactive Transform、Repeat reconciliation 和已挂载 View 进入稳定状态，并分别记录 Query、报告生成和页面就绪时间。
- [x] 150K 行真实浏览器回归覆盖声明式 Metric、browser-js Worker 与 Custom Canvas 聚合。
- [ ] 固定并持续运行 10K、100K、1M 行 Query → Arrow → Interactive → Renderer 基准，记录峰值内存和重复运行回落。
- [ ] 根据证据决定是否实现服务端分页、按需 Record Batch、浏览器列式 Selection 或更严格的大输入降级；不预先扩张 DSL。

### P2：浏览器可靠性

- [x] Chromium 覆盖独立分支渐进发布、失败隔离、取消后终态、空 View、大数据 Arrow 和局部重绘。
- [x] 当前完整 E2E 契约套件在 Chromium、Firefox、WebKit 通过，覆盖渐进 Query/Interactive 分支、Selection 级联、局部更新、Perspective 与 HTML Export。
- [ ] 扩展 Firefox/WebKit 的窄视口、弹层几何、滚动、键盘、ARIA、Perspective 恢复和重复 dispose 矩阵。
- [x] Selector、Control、View、Section 七状态矩阵和 Select 10/100/1,000 真实选项 Story 已进入 Gallery 与 Chromium 契约测试。

### P2：内部归属与可维护性

这些工作不改变当前 DSL，但会降低下一次替换前端框架或拆分 Runtime 的迁移成本。

- [x] `view.declarative`、`section.declarative`、`data.pipeline` 和 `presentation.shell` 已迁入 owner Package；13 个 Package 均为 package-owned，Runtime 内没有同功能副本。
- [ ] 按 Runtime Manifest、Output Store、Interactive Scheduler、Selection Binding、Renderer Lifecycle 拆分大型 `canvas-runtime.js`，并通过构建步骤输出单一浏览器资产。
- [ ] 按 parse/load、cross-file contract、asset validation、catalog/navigation 拆分大型 `workspace/loader.py`；稳定错误 code 和 CLI 输出不得随物理拆分漂移。

### 开源发布

- [x] 完成 `0.3.0` 本地发行门禁：wheel、sdist、pip ZIP 构建，并分别在干净 Python 3.12 环境完成 `version → schemas → components → init → validate → report` 冒烟。
- [x] 完成 `0.3.1` 本地发行门禁：三种归档构建、内容审计，并分别在干净 Python 3.12 环境完成安装与 CLI/报告冒烟。
- [ ] 维护者决定许可证并添加正式 `LICENSE`；许可证未定不阻塞开发，但阻塞正式对外授权。
- [ ] 添加 `CONTRIBUTING.md`，说明安装、validate/test、Runtime/Component 变更和 PR 验收。
- [ ] 正式 GitHub Release 发布 wheel、sdist、pip ZIP、SHA-256 和远端 CI 记录。

## 按真实需求触发

以下能力不进入当前承诺：`number-range`、month/quarter/year 日期控件、Transfer/Entity Picker/Drawer、单文件内联 Pyodide 和多套命名 Presentation。只有真实 Dashboard 或框架替换证明现有边界不足时才实现。

当前是可信单机工具，不做多租户 CPU/内存配额或不可信代码沙箱。

当前只支持一个 Dataviz Server 进程写一个 Workspace/报告目标；进程内锁不承诺跨进程协调。Runtime 并发上限在 Server 启动时创建，修改后需要重启。可信 Python Source 可以主动把任意值写入 Output，因此框架的凭据脱敏是错误/日志防线，不替代看板作者的数据最小化责任。

## 明确非目标

- 旧实验契约兼容层、自动迁移或双协议 Runtime。
- 可视化编辑器、Mosaic/坐标布局和旧 Widget 协议。
- 让 Pyodide/Python 直接操作 DOM 或成为第二套 View Renderer。
- Interactive Transform 隐式访问 Adapter 或重新查询 Source。
- 在没有真实需求和评测证据前增加空接口、Runtime 或重复组件。

## Definition of Done

公开能力必须同时具备：严格 Schema 与稳定错误码、`validate` 提前发现、机器可读 CLI 文档、默认样式和扩展 hook、契约与真实浏览器测试、Server/HTML 一致行为、局部更新与状态隔离，以及准确的 README/DESIGN/CHANGELOG。计划项只有在实现、测试和文档都完成后才能勾选。

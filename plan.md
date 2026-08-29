# Dataviz 实施计划

更新时间：2026-08-29

稳定设计见 [DESIGN](DESIGN.md)，代码入口见 [当前实现索引](docs/product-architecture.md)，使用者入口见 [README](README.md)。本文件只保留当前结论和仍需完成的工作，不重复记录历史迁移过程。

## 当前结论

| 领域 | 状态 | 结论 |
| --- | --- | --- |
| P0 数据执行架构 | 已完成 | Query DAG、Interactive DAG、Control/View 影响关系、Named Output、三种 Interactive Runtime、状态隔离和导出边界已统一为一份版本化 Dependency Contract。 |
| P0 Selection 状态一致性 | 已完成 | `{intent, values}` 是唯一 canonical state；明确空集、动态全选、optional Single Clear、tab/HTML/三种 Interactive Runtime 使用同一 resolver。 |
| P0 Control Binding / Linked Views | 已完成 | 一个 Selection Control 最多绑定一个可读写 View Adapter；Plotly/ECharts/Table/Custom 与面板共用 canonical state。 |
| P0 Layout Contract | 已完成 | Dashboard v9 拥有结构；Layout Contract v1 统一确定性行列、span、custom mount、Renderer、Server/HTML、AI context 与 validate。 |
| P0 最终配置有效性 | 已完成 | Semantic Validation、`inspect layout`、状态摘要、Runtime-aware trigger、紧凑 CLI、Chart Service 与 visual-check 已统一消费最终契约。 |
| P0 Renderer 生命周期 | 已完成 | Plotly、ECharts、Perspective 在 Server/HTML 共用 mount→update→empty→restore→interaction→resize→dispose→export 行为矩阵；首屏 bootstrap 也进入 View ID 状态表。 |
| P1 Component Package | 当前范围已完成 | Registry v5 已覆盖常用 Data Entry、View、Section、Renderer、Repeat 和 Presentation 组件；继续扩张必须由真实场景触发。 |
| P1 人工参数编辑 | 已完成 | Server 可编辑 Query/Dashboard/Section/View 的默认值、静态候选项和同级顺序；revision、round-trip YAML、Schema 校验与原子写入保证只修改 `dashboard.yaml` 的受限子集。 |
| P1 AI Analysis Plane | A–F 已完成 | Output 语义、可信度、Catalog 发现、批量 Describe、物理 Target Reference、不可变 Result、无重跑分页/检查/导出、Evidence/Promote 与 Browser/Pyodide 边界均已落地并通过完整套件。 |
| P2 AI 开发效率评测 | 工具已完成，真实试验暂缓 | 成对任务、输入完整性、逐项验收和真实 Token 记录均已实现；试验方案尚未决定，不用仓库测试伪造结论。 |
| P3 规模与浏览器矩阵 | 当前范围已完成 | 固定 10K/100K/1M 基准、流式 groupBy 优化，以及 Chromium/Firefox/WebKit 的窄屏与 Perspective 恢复组合矩阵均已有可复现证据。 |
| 开源发布 | 本地发行完成 | `0.12.0` 已通过完整代码、三引擎浏览器、示例 strict validate 与三种归档门禁；正式对外授权仍等待许可证决定。 |

当前开发基线：Package `0.12.0`、Python 3.11–3.14、Dashboard `dataviz/dashboard/v9`、Presentation `dataviz/presentation/v2`、Source/Dataset/Interactive Transform `v2`、Dependency Contract `v5`、Layout Contract `v1`、State Snapshot `v1`、Browser Runtime `dataviz/runtime/v5`、Component Registry `5.4.0`。这些破坏式契约只接受当前严格字段，不保留旧字段兼容名、自动迁移或第二套 Runtime。

Authoring P0 的 A–G 已进入当前 Schema/Compiler/Runtime。复杂实现必须留在 Compiler/Runtime：普通 Dashboard 不手写依赖图、事务、revision 或回调；常见跨图联动最多新增一条声明。

## 已完成的核心能力

### 数据、计算与状态

- [x] Dashboard v9 只有 Query Parameter 与 scoped Controls 两个入口；Control 在 Dashboard/Section/View 统一声明，并以 `kind: selection | compute` 保留不同 delta、提交周期和失效路径。
- [x] Source、Dataset Transform 与 Interactive Transform 统一使用 `query_inputs` 将 canonical Query Parameter 映射到节点本地 alias；删除节点级 `query_params`。SQL placeholder 与三种 Python/Browser Context 只能读取本节点声明的 alias。
- [x] `range_input/date` 可通过 `{parameter, part: start|end}` 投影为两个标量；Dependency Contract、Planner、Server/Browser Runtime、缓存证据、Resolved SQL、CLI Context 和 HTML Export 使用同一映射。
- [x] Query Parameter 的 `single_input/date` 与 `range_input/date` 支持基于 Workspace IANA 时区的严格相对默认值；Range 由两个独立 Date Atom 组成，固定/相对端点可混用。编辑器每个端点只显示模式与当前值，Run 创建前解析为具体 ISO 日期并固化，Compute/Selection 不接受相对默认值。
- [x] Select 候选域用严格的 `options.mode=static|infer` 区分封闭枚举与 Source 推导；Query/Selection/Compute Select 统一使用 `initial`，动态候选优先保留有效交集，完全失效才回退初始策略。
- [x] `selection_inputs` 是 Runtime 数据边界而非普通参数；三种 Interactive Runtime 都先对字段契约匹配的表输入应用 include Selection，再进入 Compute 逻辑。
- [x] Source/Dataset Transform 与 Interactive Transform 使用两个 DAG、显式 Named Output、Schema Contract、provenance 和分支级并发。
- [x] 独立分支完成后立即发布；局部失败、超时或取消不会等待或覆盖无关分支。
- [x] `server-python`、`browser-python`、`browser-js` 共用输入、输出、错误、缓存、generation 和 dispose 契约。
- [x] 同一 tab 可恢复状态；不同 tab、Dashboard、用户、Run 和 Interaction generation 相互隔离。
- [x] Query Run Artifact 统一保存在 Workspace `.dataviz/`；可达 Server Interactive 输入在计划阶段显式分类，按 tab + Dashboard + Run + canonical Output 复用且绝不重查 Source。
- [x] SQL 默认 120 秒超时并立即额外重试一次；Dashboard 可覆盖 timeout/retry。
- [x] `dataviz/dependency-contract/v5` 成为 Query、Interactive、Control、Output 与 View 关系的唯一编译结果；Planner、Loader、Server、Browser、Export、CLI 和 AI context 不再各自推导 DAG。v5 还为每个 View 编译拓扑序 `pipeline_nodes`，Header 只投影 Query 层，View 在类型标签左侧按需显示活动/失败的上游节点与 Renderer 灯；Ready/Not run 不制造常驻噪音。
- [x] 每个不可变 Dashboard load snapshot 以并发安全方式只编译并缓存一个 Dependency Contract；热更新创建新快照，并行首访也只返回同一个对象。
- [x] Query Parameter 契约给出直接消费者及最终受影响 Query 节点、Interactive 分支、option Control、内容字段和 View；Query 节点同时给出下游 View/Control。
- [x] Dependency Contract 以“可执行才存在”为不变量：环、未知 Output、browser → server-python 非法依赖和越界 Control consumer 在编译期拒绝；Loader 仅对无效图做 recovery diagnostics。
- [x] Query/Interactive 节点只读取显式声明的 Query/Selection/Compute 参数；Browser Transform/View 注册会核对 data inputs、Control inputs、Query Parameter inputs 与 Output names，注册 payload 只作 drift assertion，调度与 View 取数仍由契约拥有。
- [x] Control 通过 `depends_on` 只声明直接 Selection 父节点；Dependency Compiler 校验作用域、未知引用、父节点类型和环，生成 canonical 直接边、传递祖先/后代与 `control_order`。Browser 按同一拓扑原子协调候选域，支持 Dashboard→Section→View 和同 View 多级链，不再按 DOM 层级猜测级联。
- [x] `dataviz inspect dependencies WORKSPACE DASHBOARD [--format json]` 为人和 AI 输出同一份可审查依赖图；HTML manifest 同时保存完整契约作为运行证据。

### Runtime 与 HTML Export

- [x] Server 与 HTML 共用 Renderer、Control、Overlay 和内容绑定实现。
- [x] Renderer 作者接口保持 `validate/mount/update/dispose`；平台统一验证 `mount/update/empty/restore/interaction/resize/dispose/export`，并记录 mount/update/empty/restore/interaction/resize/dispose/failure 指标。
- [x] View 具有 ready/loading/stale/empty/error/cancelled/unavailable 终态；取消或失败的 Run 可重新打开检查，不再因缺失 Output 返回 500。
- [x] View 空 descriptor 进入 `empty`，不再永久停在 rendering；Arrow Table 的 Metric 聚合不再显示 `[object Object]`。
- [x] 浏览器聚合改为线性 reducer，150K 行上的 min/max/mean/sum 不再使用会触发 JavaScript 参数上限的 spread。
- [x] HTML Export 明确 `interactive | snapshot | unavailable`；可达 Interactive DAG 只要包含 `server-python` 就拒绝导出，并引导使用分享链接，绝不伪装成离线交互。
- [x] browser-python 支持 Pyodide CDN 与 `HTML + assets + manifest` bundle；未使用 Pyodide 时不携带相关 Runtime。
- [x] Server Header 将 Export 收敛为简洁 SHARE 菜单，只保留“分享链接 / 导出 HTML”。分享结果原子落盘到 `workspace/shared_caches/<dashboard>_<timestamp>_<run>/`，保存 manifest、Query Result 和哈希校验 Artifact，不污染 Dashboard 目录。
- [x] `/shared/<share-id>` 固定 Query Parameter 和 Base Output、禁止 Run；Browser JS/Pyodide 继续端侧执行，Server Python Interactive Transform 复用 Server Interaction 协议。Server 重启后按分享目录恢复会话；v1 暂不自动过期或联动清理。
- [x] Server 与 HTML/分享页共用 `presentation.shell` 的 Header、Query Card、字段字体和输入尺寸；浏览器回归比较最终 computed style，而非仅比较 CSS 文本。

### 模板、验证与 AI 入口

- [x] Component Registry v5.4 提供物理 Package、机器可读 manifest、Story、测试声明、语义 DOM 和 CSS token；`components check` 检查包结构，行为由 pytest/E2E 实际执行。
- [x] 21 个 Component Package 全部为 package-owned；`data.pipeline`、`view.declarative`、`section.declarative`、`presentation.shell` 已迁出 Runtime bridge，删除 `declarative-runtime.js` 和重复实现。
- [x] 14 个独立 `control.*` Data Entry Package 对齐 Ant Design 的 Input、InputNumber、AutoComplete、Checkbox、Switch、Radio.Group、Select、Checkbox.Group、Cascader、TreeSelect、DatePicker、RangePicker、Slider 与 Form.List + Input；Query/Selection/Compute 共用 Registry 和 Renderer。Checkbox Group 只承担 2–5 个并列选项的直接多选，不显示 All/Invert/Clear 工具栏；更大的平面候选域交给 Select，层级域交给 Cascader/TreeSelect。DatePicker/RangePicker 统一使用可编辑 `YYYY-MM-DD` 文本、同款图标和 Dataviz 日历；连续八位数字自动按 yyyy/mm/dd 分段，标题区可直接选年/月，Range 两端位于一个连续边框内，空 preset 与无动作 footer 都不产生占位或重复文字。
- [x] 默认 Table 不显示独占一行的行数元信息；`options.show_count: true` 作为显式证据开关保留，空数据继续进入统一 Empty 状态。
- [x] Query 与 Dashboard/Section/View Controls 使用 `control-panel.adaptive`：Selection/Compute 在 Runtime 内保持语义分组，但默认托盘只展示业务字段与组件，不重复显示 DATA/LOGIC、作用域和影响 View 数量；面板保持视口内滚动。Query 托盘只保留字段，宽屏最多六轨并响应式降列；每轨默认保持 280 px 目标宽度，参数较少时右侧自然留白，不用 `1fr` 拉满整行，控件可显式 `span: 2`。Presentation 覆盖排版时不分叉状态逻辑。
- [x] Server 与导出 HTML 将 Query Parameters 收敛为同一内联 Query Card：Header 最右侧固定为“查询 + ▼”分段按钮，查询执行与 Card disclosure 分离；不新增 Parameters 按钮，Card 内也不重复运行按钮。Card 只保留紧凑的“查询参数”标题和标题在上、输入在下的有界网格，移除标题分割线；Server 默认展开并按 tab/Dashboard 记忆，导出 HTML 默认折叠。Card 与 Canvas 共用 `clamp(22px, 3vw, 48px)` 水平 gutter，不再用独立 `max-width` 造成宽屏错位；展开后参与文档流并推开 Canvas，滚动时自然离开视口，外部点击与 `Esc` 仅关闭临时 Controls/诊断浮层。
- [x] Server Shell Scroll Bridge 统一外层 Header 与 Canvas iframe 的滚动优先级：向下先隐藏 Header、向上先回到 Canvas 顶部，避免参数区必须等 Canvas 滚到底后才离开视口。
- [x] 原生 Shell 文案收敛为必要的操作名和状态；删除重复编号、口号及教学句，业务 title/subtitle/description 仍由 Dashboard 自己决定。
- [x] Server 与导出 HTML 使用安静白色 Shell：Header、Sidebar、Workbench 与默认 Canvas 形成连续表面，去掉 Canvas 外层卡片、灰色沟槽和强边框；`presentation.shell` 统一 Header 高度、基础字体、Query/Control Panel、字段和输入尺寸，避免导出后发生 Host 样式跳变。Shell token 与 Dashboard Theme token 分离，靛蓝负责当前导航与主操作，绿色只负责 Ready/成功状态。
- [x] Server Header 将 Controls 作为明确按钮紧邻 Run 左侧；Query Pipeline 从操作区迁为品牌右侧的 Source/Dataset 状态灯。View 通过 Dependency Contract v5 的 `pipeline_nodes` 在类型标签左侧按需显示自己的上游与 Renderer，完成后自动隐藏，失败节点可点击查看执行证据。
- [x] Gallery 提供 Control、View、Section 的七状态矩阵，以及实际包含 10、100、1,000 个原生选项的 Select Story；1,000 选项搜索覆盖全量且增强 DOM 有界。
- [x] Table/Perspective、Plotly/ECharts、Repeat Small Multiples/Selection Gallery 和自定义 Renderer 都走统一 Runtime 边界。
- [x] `validate` 是零查询静态门禁；`docs`、`schemas`、`components`、`inspect context`、`scaffold` 为新 AI 会话提供当前契约。
- [x] Sources 面板提供参数化 statement、Resolved SQL、bound parameters、Adapter、timeout/retry、hash、日志和结构化错误，不暴露凭证。
- [x] 独立维护工具 `dataviz-authoring-eval` 固定任务身份、输入哈希、验收证据和真实 Token；缺失 Token 保持 unmeasured，正式产品 CLI 不暴露该能力。
- [x] Server 提供统一的受限参数编辑器：右键 Run 或 Dashboard/Section/View Controls 打开对应作用域；面板不常驻编辑工具条。编辑器只修改默认值、静态候选项和同级顺序；推断候选项只读，当前分析状态不被覆盖，导出 HTML 不暴露编辑入口。
- [x] 参数编辑使用 Dashboard 文件 revision、进程内写锁、保留注释/顺序的 YAML round-trip、完整 Schema 校验和原子替换；AI 或外部编辑造成 revision 漂移时拒绝覆盖。

### 2026-08-24 核心审计与加固

- [x] Workspace 热刷新只发布完整快照；活动 Query worker 保留启动快照，开发态新 Interactive/Presentation 只有在 Query Contract 指纹兼容时才能复用既有 Base Output。
- [x] Scaffold、AI trial、持久缓存、HTML/manifest/assets 与发行 ZIP/checksum 使用预检、原子发布和失败回滚。
- [x] Adapter 配置、Pydantic/YAML 诊断、Python progress/log/traceback 和执行证据统一做凭据脱敏；提交到 Git 的 Adapter 文件拒绝直接凭据。
- [x] Artifact 与缓存命中验证 content hash；大文件改为流式哈希和原子流式复制，不再整文件读入内存。
- [x] Runtime/Output/Pyodide 路径限制在受控根目录；portable Pyodide bundle 拒绝符号链接和不完整依赖闭包。
- [x] 删除重复的公开 `templates` CLI 入口；AI 统一从 `components`、`schemas`、`docs` 和 `scaffold` 发现能力。
- [x] `components check` 的报告明确只验证 Package 元数据、资产和测试声明，不再暗示已经执行行为测试。
- [x] Interaction endpoint 不再等待整次 Query 完成；快 Base Output 可以驱动 Server/Browser Interactive 分支，Query 终态通过 frame handshake 原地同步而不重载 Canvas。
- [x] Selection-kind、Compute-kind 与 Output delta 明确区分“全部/部分/无变化”；无关 Output 不再重启 active Transform，未变化 Output 不再重复传播或重绘。
- [x] 删除旧 Server capability fallback；导航显示名严格来自 Dashboard 文件夹，运行态不再用页面 title 冒充 Canvas 名称。
- [x] 保留策略保护活动 Query 及其活动 Interaction 仍在消费的 Run/Cache；长计算不再被后台清理误取消。
- [x] wheel、sdist 与 pip 源码 ZIP 均在隔离环境完成 `install → version → components → init → validate → report`；归档不包含 `.dataviz`、本地凭据、虚拟环境或构建缓存。
- [x] 同一 wheel 已在 Python 3.11、3.12、3.13、3.14 完成干净安装与 CLI/报告冒烟；完整 Python 测试矩阵由 CI 持续执行。
- [x] 动态 Selection 启动顺序固定：option domain 只来自 Base Output，首次水合、Control reconciliation、View 渲染与 Interactive 调度有唯一顺序；`canvas-ready` 只在首次 canonical state 提交后发布，父页面不再用早到的 tab 状态覆盖初始化中的用户操作。
- [x] Browser Interactive 七状态通过 frame identity 回传 `Pipeline`；Base View 不再因其他动态 Selector 或 Interactive 分支而停在 `Waiting for dataset`，Server 与独立 HTML 均有回归。
- [x] Workspace 文件监听使用 debounced revision、SSE 通知和 `canvas / analysis / query` 影响分类；Presentation 自动重载，Interactive 基于现有 Base Output 重算，Query Contract 变化只进入 Outdated 并要求显式查询。
- [x] 热更新保留 tab 的 Run、Control 与 Canvas 滚动位置；无效中间写入不替换当前 iframe，Header 提供诊断和显式 Reload。分类只跟踪实际声明/引用资产；保存 Source 后立即 Query 会先同步 revision。页面重开及查询运行途中发生定义变化时，也会重新核验 Query Contract，旧快照不能被误标为当前结果。
- [x] Data Entry 的值语义、Control scope 与 UI component 三轴解耦；14 个 `control.*` Package 逐项对齐 Ant Design 组件边界，不保留已移除组件或 Presentation 结构字段的兼容入口。
- [x] Query Parameter、Selection 与 Compute 复用同一 Control Renderer；Gallery 与浏览器契约覆盖新文本、建议、数值、布尔、日期、范围、平面/层级单多选和 Slider 的真实水合、输入、键盘、浮层、状态与虚拟列表行为。

## 下一步优先级

### P0：CLI 领域收敛与统一 Result（已完成）

目标是以 0.12.0 正式产品对象模型提供 Analysis Plane，不复制 Runtime；Catalog、Target、Result 和 Evidence 只使用一套公开契约。设计见 DESIGN 的“0.12 CLI 与运行事实模型”。

#### A. 冻结公开契约

- [x] 确定公开链路为 `catalog → run → result → evidence`，内部保留可变 Execution Run 与不可变 Result 的边界。
- [x] 确定 `dataviz/target-reference/v1` grammar（Dashboard、Source、Source/Dataset/Interactive Output、View）；删除生成式 `src_/base_/drv_/view_` alias，不提供隐藏兼容解析。
- [x] 确定显式 CLI Execution 的终态封存规则：ready/partial/failed/cancelled 均可形成 Result，preflight 失败不形成 Result；Server 高频交互不自动封存。
- [x] 确定正式文档的“构建与验证”及“探索与执行”两条渐进路径，并把 Authoring Evaluation 定义为非产品工具。

#### B. 隔离维护者评测工具

- [x] 将 `authoring prepare/verify/assess/start/note/finish/show/tasks/protocol/compare`、评测试题和日志实现迁入独立 `tools/authoring-evaluation/` 项目。
- [x] 独立工具使用 `dataviz-authoring-eval` 入口和自己的依赖/测试；正式包、归档、README 与 `dataviz --help` 不包含评测命令或实现。
- [x] 将 context/token benchmark 移入维护者工具；正式 `benchmark runtime` 只测 Query、Report、浏览器渲染、内存和释放。

#### C. 重构公开命令树

- [x] 公开命令域稳定为 `catalog list/search/describe`、`result list/show/inspect/export`、`evidence create/promote`。
- [x] `dataviz run WORKSPACE TARGET` 是唯一公开执行入口，支持 Dashboard 与所有 Target Reference v1 物理坐标。
- [x] `tree` 提供真实文本树与结构化 JSON；`inspect context/dependencies/layout` 统一承载只读编译结构。
- [x] `gallery → components gallery`，组件命令拆为 list/show/check/gallery；`renderer-test → renderer test`；`clean → prune`；`benchmark → benchmark runtime`。

#### D. Target 与 Catalog 物理引用

- [x] 新增并 Schema 化 `dataviz/target-reference/v1` parser/serializer，Catalog、Describe、Run、Result、Evidence 与 next actions 共用同一实现。
- [x] Catalog SQLite 和 JSON Contract 只存储规范物理 reference，不维护第二套引用索引；搜索默认输出以语义为主体、物理引用为可复制次级信息。
- [x] 批量 Describe 和 Result Output 选择只接受 canonical 物理引用；迁移示例、Scaffold、文档和测试。

#### E. Result 成为统一运行事实

- [x] 显式 CLI Dashboard/局部执行共享 Result Store；终态封存 ready/partial/failed/cancelled，并保存错误、DAG、参数、definition hash、provenance 与 renderability。
- [x] 实现 `result list`；show/inspect/export 对所有终态安全工作，且绝不重跑或改写 Result。
- [x] Report/Share/Evidence 优先消费 Result；Dashboard convenience report 只执行一次，并在同一发布事务中封存数据 Artifact、Presentation 快照和 Result，后续报告不重复执行。
- [x] `prune` 统一预览并清理过期 Result、Execution Artifact 和缓存；显式 `--apply` 才修改文件，shared cache 暂不自动清理。

#### F. 文档、回归与发行门禁

- [x] 更新 README、focused docs、Schema catalog、CHANGELOG 和 CLI help；内置 `dataviz docs` 分为“构建与验证”“探索与执行”“运行维护与扩展”，完整披露 Catalog、Target、Result、Overlay、Evidence/Promote，旧命令不再出现。
- [x] 为 Target grammar、物理引用 Catalog、统一 run、所有 Result 终态、并发封存/读取/清理和下游消费建立契约测试。
- [x] 完成 Ruff、完整 Python 测试、Chromium/Firefox/WebKit E2E、全部示例 strict validate、组件检查、三种归档内容审计及干净安装冒烟后再发布。

### P0：Selection、Linked Views 与最终配置有效性

这一阶段解决“配置合法，但最终效果并非作者预期”的核心缺口。它是下一次破坏式发行的前置工作；项目尚未进入生产，不为当前实验性 Presentation 布局字段保留兼容 alias、迁移分支或双协议 Renderer。

P0 不是以“底层支持了更多边”为完成，而以作者复杂度没有增加为门禁：普通看板不写 JS；跨图单选联动只写一条 binding；默认值无需重复声明；当前 `validate`、`inspect dependencies` 与 `inspect layout` 能解释已落地行为；高级逃生口不能绕过 canonical state。任一实现若要求作者维护第二份筛选值、直接连接两个 View 或理解事务细节，均不验收。

#### A. Selection State Contract 一致性（已完成）

- [x] 唯一有效 Selection 状态由 `intent + values + current option domain` 投影；消费者不再根据 `[]` 猜测 All 或 None。
- [x] `all_available` 表示当前全部候选并随候选域扩张；`explicit + values` 表示显式子集；`explicit + []` 表示明确空集。
- [x] 选择基数、`required` 与 `clearable` 解耦：optional `single_select` 合法值为 0..1；required single 恰好一个值并禁止 clearable。
- [x] 可清空单选默认使用 Select；Validator 拒绝 `radio-group + clearable: true` 和 `required + clearable: true`。静态/infer optional Single 的初始空、选择、Clear 与恢复共用状态机。
- [x] Control summary、内容绑定、普通 View、Repeat/Selection Gallery、Browser/Server `selection_inputs`、缓存指纹、tab 恢复与 HTML Export 共用 Selection resolver。
- [x] 父页面/Canvas 按 owner 同步：首次恢复完整 snapshot，之后 Header 只发送 Dashboard Control patch；Canvas 回传完整 canonical state，并以 selection epoch + frame identity 拒绝双向迟到消息。
- [x] 删除 `data-empty-means-all` 和 Selection Gallery 的 raw empty 分叉；Component 只渲染 resolver 结果。
- [x] `store-performance` 初始 `explicit + []` 不创建卡片；全选显示 `All (100)` 并创建 100 个 group；清空恢复零 group。
- [x] 回归覆盖 subset、select-all、clear、tab restore、候选域收缩/扩张、Server/HTML，以及 browser-js/browser-python/server-python Selection-before-Compute。

#### B. Control Binding / Linked Views（已完成）

- [x] Control 是唯一变量 owner；View 侧最小 DSL 为 `control_binding`。Control 不声明 Renderer、highlight/filter、row/cell 或 callback。
- [x] 一个 Selection Control 最多一个可读写 Bound View；标准 Control Component 仍可写入，任意数量 View/Transform 可只读消费；一个 View 最多一个可读写 Selection Binding。
- [x] View Adapter 负责真实 point/row/cell 事件写入与 selected projection；Bound View 保留目标 Control 自身过滤前的候选上下文。
- [x] 作用域依赖保持或收窄；Compiler 校验未知引用、越界、重复边、环，以及更窄 Selection 反向决定更宽 Control 候选域。
- [x] Dependency Contract 分别编译 `Control → Control` 候选边、`View event → Control` writer 边与 `Control → View/Transform` consumer/projection 边。
- [x] Control Component、Bound View、tab restore 与 API 共用 canonical commit/delta；按 `control_order` 协调，以 revision/generation 丢弃过期结果，no-op 不推进 revision。
- [x] Table、Plotly、ECharts 归一化 `select / select_many / clear`；Custom Renderer 只能通过类型化 View Adapter 出口发送 datum。
- [x] `dependencies` 解释 target、唯一 writer、候选祖先、consumers 与 projection；Validator 拒绝第二 writer、缺失字段和不支持的 Renderer。
- [x] 浏览器回归覆盖 Plotly/ECharts/Table 写入、面板/consumer 同步、Clear、no-op、旧 generation、candidate-preserving Bound View 与导出 HTML 中的同一绑定路径。
- [x] 第一版不支持写 Query Parameter/Compute、多个 writer、一个 View 写多个 Controls、任意 callback、程序化事件链、跨 Dashboard 或任意跨 Section 子集。

#### C. Layout Contract 与结构单一所有权（已完成）

- [x] Section/View 顺序、结构模板、columns 和 View span 属于 `dashboard.yaml`；`presentation.yaml` 只保留视觉与 Controls 托盘内部排版。
- [x] `dataviz/layout-contract/v1` 记录 declarative/custom mode、Section/View 顺序、模板、列数、最终 span、确定性行分配和来源。
- [x] 默认 Renderer、Server、HTML Export、AI context 与 Validator 消费 Layout Contract；结构不再由 Python、CSS、Component 和 DOM 重复推导。
- [x] `single`、`grid`、`split`、`comparison`、`chart-and-table`、`band` 与 Repeat 模板拥有明确 cardinality 和默认 span；显式 span 不被模板静默吞掉。
- [x] 自定义 Canvas 使用 `mode: custom` 并只暴露稳定挂载点，不伪造任意 CSS 的静态布局。
- [x] 示例、Gallery、Scaffold、内置文档和测试夹具已迁移；Dashboard v9 / Presentation v2 删除旧 Presentation 结构字段且无兼容 alias。

#### D. Semantic Validation 与静态布局检查

- [x] 在最终 Dashboard + Presentation + Component/Renderer manifest + Layout/Dependency Contract 上运行一次 Semantic Validation，不维护第二套图。
- [x] 增加稳定 `error / warning / advice` 三级诊断；`--strict` 只因 error/warning 失败，主观 advice 不阻塞发布。
- [x] 检查确定性冲突/no-op：模板 cardinality、超出 columns、无效 span、未被使用的 View、没有任何 consumer 的 Control、Renderer 不支持的属性和被覆盖的配置。
- [x] 对 band 中大型明细、可疑 `min_height`、Browser Transform 使用 apply 等启发式问题只给 advice，不假装静态工具了解数据规模或审美。
- [x] 实现 `dataviz inspect layout WORKSPACE DASHBOARD [--format json]`，输出最终行列、span、来源、冲突和 custom 边界；为 CLI 输出建立稳定 Schema 和 Contract tests。

#### E. 可见的当前分析状态

- [x] 定义 `dataviz/state-snapshot/v1`，统一 committed Query Parameter、applied Selection、committed/draft Compute、stale 和作用域信息。
- [x] 状态摘要改为 Presentation 显式启用；默认画布不再机械复述 Query/Control 值。启用后可在 Dashboard/Section/View 对应作用域展示并展开长多选。
- [x] 明确区分“产生当前结果的已提交值”和“待应用草稿”，避免标题、摘要和报告证据提前使用 draft。
- [x] Server 与导出 HTML 共用同一摘要组件、formatter、事件和状态快照；允许作者调整 label/顺序/隐藏项，不要求手写 JS。

#### F. Runtime/CLI 默认体验

- [x] 将默认 trigger 改为 Runtime-aware：browser-js/browser-python 默认 auto，server-python 默认 apply；保留显式 auto/apply/manual、debounce、取消和 stale 语义。
- [x] 为 Runtime-aware trigger 补齐 Schema、Dependency Contract、Server/HTML、CLI docs、Scaffold 和三浏览器回归；静态工具不猜测计算成本。
- [x] `run` 默认输出稳定、高密度 Result summary；SQL、bindings、Artifact、Node、provenance 和完整 diagnostics 由 `result inspect` 渐进披露。
- [x] 精简模式保留稳定错误 code、必要失败上下文和下一步建议，并用真实 AI context 快照测试防止输出再次膨胀。

#### G. Chart Service 与真实浏览器视觉检查

- [x] 从内置 View Adapter 抽取 `context.charts.plotly` / `context.charts.echarts`，统一 Theme、responsive、scrollZoom、resize、update、dispose、错误状态与 Export。
- [x] 让 Scaffold、Gallery 和内置 Custom Renderer 默认使用 Chart Service；保留直接底层调用作为显式逃生口，并通过 Renderer manifest 声明可验证能力。
- [x] 实现 `dataviz visual-check`：在固定 viewport 的真实浏览器中检查横向溢出、重叠、零尺寸、弹层裁切、永久 Loading、Perspective 容器高度和 Console error。
- [x] visual-check 输出 Screenshot、机器可读 geometry report、稳定诊断 code 和复现参数，并覆盖 Server 与导出 HTML、Chromium/Firefox/WebKit 以及窄视口。
- [x] 明确 visual-check 不判断配色、业务图表选择或主观美感；这些继续由视觉模型/人工审阅和 Gallery 负责。

完成顺序固定为：Selection State Contract → View Event/Control transaction → Layout Contract → Semantic Validation → `inspect layout` → State Snapshot/摘要 → Runtime/CLI 默认体验 → Chart Service → visual-check。Linked Views 必须建立在共享 Selection resolver 上；后续步骤不得先复制一套临时 Selection、事件、布局或状态推导。

排序原因是：Selection resolver 决定“当前到底选了什么”；Linked Views 只是增加同一状态的 writer；Layout/Semantic Validation 决定作者写的结构是否真的生效；State Snapshot 让用户看见当前上下文；CLI、Chart Service 与浏览器视觉检查最后再压缩试错成本。这样每一步都建立在前一份唯一契约上，而不是用 UI 补丁掩盖状态问题。

### P1：AI Analysis Plane（当前范围已完成）

目标不是增加一套“给 AI 用的查询引擎”，而是让 AI 能搜索、理解并执行现有 Dashboard 的 Named Output，再把经过人审阅的试验结果晋升为普通 Workspace 资产。Dashboard Schema、Compiler 与 Dependency Contract 仍是事实来源；Catalog 只是可重建索引，Evidence 不变成第二个知识数据库。

当前已完成“发现 → 描述执行契约 → 执行并封存 Result → 无重跑查看/导出 → 临时试验 → Evidence → Promote dry-run”，并完成使用统计、搜索概览压缩、Browser/Pyodide 边界与发行门禁。A–F 均已完成。

#### A. Output 语义、可见性与可信度

- [x] 在每个 Base/Derived Named Output 附近增加 Output 级 `semantics`：`visibility: public|internal`、`title`、`purpose`、`grain`、`caveats`；不再从 Dashboard context 统一继承 grain，也不再把所有 Output 默认当作 public。
- [x] 增加独立 `assurance.status: draft|reviewed|certified|deprecated`；visibility 只表示可发现性，不冒充可信度。reviewed/certified 必须记录 owner、reviewed_at 和可定位 evidence，deprecated 必须说明原因或替代 Output。
- [x] 按适用性补充时间字段/时区/口径、指标单位与聚合语义、可关联字段与 cardinality；不强迫不含这些概念的 Output 填写空表单。
- [x] public Output 缺少 title/purpose/grain 时不进入默认 Catalog 搜索；draft/deprecated 不进入 AI 默认的可信复用结果，但可通过精确引用检查。
- [x] 作者文档、Scaffold 和示例 SQL 在每个阶段显式列出 Output 字段；对 public 或 reviewed/certified SQL Output 中的 `SELECT *` / `table.*` 提供稳定诊断，不误伤 `count(*)`。
- [x] 更新 Scaffold、focused docs、示例与 validate；存量 Dashboard 先给出稳定迁移诊断，不因缺少新语义破坏原执行路径。

#### 使用统计与搜索概览压缩

- [x] 在 `.dataviz/usage.sqlite` 实现通用聚合表，以 `subject_kind + subject_ref + action_kind + actor_kind` 为主键，只保存 `use_count` 和 `last_used_at`。行为类型不做成专用列，以后增加行为无需迁移表结构。
- [x] 当前只统计两种成功行为：人明确执行 Dashboard Query 成功后累加 `dashboard/query_succeeded/human`；AI 执行 `run TARGET` 成功后累加 `output/run_succeeded/ai`。`catalog list/search/describe`、Result 查看、打开/刷新、失败与取消暂不记录。
- [x] 使用 SQLite WAL、每进程独立 connection、单条 UPSERT、有界 `busy_timeout` 和短事务保证 Server/CLI 多进程不丢计数。统计写入是 best-effort，失败只记 warning，不得改变 Query/Analysis 成功结果；该库不进入 fingerprint 或 hot reload。
- [x] Catalog 结果只按实现资产 hash、Source/Runtime、Adapter 逻辑引用、Query bindings 和 Output Contract 的完全一致性做精确折叠，返回 representative、occurrence count 和可展开 references；不做 SQL 语义等价推断。
- [x] `top N` 在折叠后输出。当前先继续使用稳定确定性顺序，只暴露使用次数和最后使用时间；等累积真实数据后再决定排序公式。

#### B. 机器契约与 provenance

- [x] 为已使用的 `dataviz/analysis-entry/v1`、`dataviz/analysis-catalog/v1`、`dataviz/analysis-result/v1` 补齐可发布 JSON Schema、稳定错误码和 summary/debug/full 边界。
- [x] 结果完整记录 reference/definition hash、Query Parameter、effective Controls、输入 Artifact/hash、Output kind/schema/rows/hash、duration、lineage、truncation 与可复制下一步；大结果默认只预览。
- [x] 不同 detail 只改变证据量，不改变执行逻辑；Base/server-python/browser-js/browser-python 失败使用同一错误包络和可机器判断的恢复建议。

#### 已落地的执行基础

- [x] generation Catalog 使用 `CURRENT.json`、跨进程 lock 和不可变 SQLite generation；以 Workspace 相对路径 + SHA-256 定义闭包检查 freshness，可删除后重建。
- [x] `catalog list/search/describe` 与统一 `run` 支持规范物理 Target Reference、结构化过滤、grep-like 搜索、批量 Invocation Contract、最小 Query DAG、Base/Derived/View 目标与三种 Interactive Runtime；不复制 Runtime。
- [x] `dataviz/analysis-overlay/v1` 支持 SQL/File/Python/JS 实现替换、dry-run、不可变 Analysis Variant、独立 cache salt 与 run manifest；不写回 Dashboard/Catalog。
- [x] Overlay 只允许契约不变时的 what-if；新增 DAG、组合多 Output 或改变 Schema 进入 Analysis Draft，不继续扩张 Overlay。

#### C. Result、Evidence 与 Promote

- [x] 定义 `dataviz/analysis-evidence/v1`，记录问题/假设、结论或断言、Result hash、lineage、生成者、审阅者和审阅状态；不默认复制大型结果。
- [x] 提供 Promote dry-run/explain，把一次 Result/Evidence 转为可预览、可 validate、可 Git diff 审查的 Workspace 补丁；未经人确认不写入正式资产。
- [x] Promote 支持三类结果：新的 Transform/Named Output、现有 semantics/caveat/deprecation 修订、契约测试/数据断言/小型证据 snapshot。
- [x] 新 Output 一律从 draft 开始；Promote 不自动 certified，不绕开 owner/reviewer/evidence，不建立第二份 DAG 或知识库。

#### D. 原生 Artifact 与批量执行

- [x] `run` 完整封存 Runtime 原生 Parquet/Arrow Artifact；stdout 不直接打印二进制大结果，Result summary 只返回路径、hash、rows、truncation 和紧凑预览，Schema 按需由 `result inspect` 提供。
- [x] 支持一次请求执行/提取多个 Output，共用 Query 闭包、Artifact 和浏览器会话；结果仍逐 Output 保留 reference、hash 和 lineage。
- [x] browser-js/browser-python 按需加载 Pyodide、优先 Arrow 传输；先记录 cold start、Runtime ready、transform 和 extraction 分段耗时，再决定 browser pool 策略。

#### E. 回归与交付门禁

- [x] 覆盖 Catalog 增删改、并发写/读、构建失败回退、稳定快照重试、Target Reference 严格解析和 hash 精确折叠，并验证 Catalog 可删除重建。
- [x] 用并发 Server/CLI 进程验证 usage UPSERT 不丢计数、`last_used_at` 单调保留较晚值、busy 有界退让和统计故障不污染成功执行。
- [x] 端到端覆盖 SQL/File Base Output、Dataset Transform、三种 Interactive Runtime、默认/覆盖 Control、Overlay、Evidence/Promote、Arrow/Parquet、失败/超时/取消和无网络 Pyodide 提示。
- [x] 用 feature-showcase 提供 reviewed/certified/deprecated 口径示例，通过 `validate → catalog search → catalog describe → run → evidence create → evidence promote --dry-run`。
- [x] 更新 README、DESIGN、focused docs、CLI `--help` 和 CHANGELOG；完成 Python/三浏览器套件、全部示例 strict validate、归档构建与干净安装冒烟后再发布。

#### F. 语义发现与 Result-centric CLI（已完成）

- [x] `catalog list/search` 共用语义密集的默认文本输出：title、purpose、grain、assurance 是主体，kind、Dashboard 和物理 reference 是次级索引；紧凑附带 Query Parameter 契约、Output 摘要、相关 View、精确折叠 occurrence count 和 search 命中原因。Source/View 命中默认投影到可复用 Output；完整候选池、Schema、SQL、代码和 occurrence 列表继续按需展开，单行索引表只保留为 `--compact`。
- [x] 运行前探索统一为 `catalog describe WORKSPACE REFERENCE...`。一次可描述多个物理引用，固定在同一 Catalog generation，保持输入顺序并去重；逐项返回语义、参数闭包、类型、required/default、候选摘要、Control/Output 摘要、紧凑 lineage、代码位置和可复制的 Run 命令。单项失败不吞掉其他项，但整体退出码非零；该命令不执行 Source、候选查询或 Transform，也不创建 Result。
- [x] 公共 CLI、Catalog 文本/JSON、示例和 `next_actions` 统一使用 `dataviz/target-reference/v1` 规范物理引用；Catalog 不生成或解析 `src_/base_/drv_/view_` hash alias，也不保留隐藏兼容语法。
- [x] `run WORKSPACE TARGET` 一次完整执行并封存不可变 Result：默认写入 `.dataviz/results/<result-id>/`，stdout 只显示 Result ID/路径、紧凑闭包、标量或各最终表格 Output 的 head 10 和下一步命令；`--preview-rows` 只影响预览，run 不承担格式转换或任意目的路径导出。
- [x] `result list/show/inspect/export` 只消费已封存 Result：show 分页且绝不重跑；inspect 渐进披露 Schema、DAG、lineage、hash、时序和 provenance；export 只复制明确选择的一个原生 Artifact，不改变格式、manifest 或内部路径。直接 File Source 只封存已读 path/hash 收据；`prune` 统一预览和显式清理 Result、Execution Artifact 与缓存，读取租约保护并发消费者。
- [x] 新增 `dataviz/target-reference/v1` 与现行 Catalog/Result Schema，并同步 README、focused docs 和 CLI help；回归覆盖语义密度、正则命中原因、批量 describe、物理引用解析、Result 四种终态、原子发布、无重跑分页、原样导出、索引重建、显式 prune、File Source 变更检测和 Browser Result 导出。完整 Python + Chromium/Firefox/WebKit 套件和四个示例 strict validate 通过。

HTML Analysis Capsule、HTML Output 提取和远程分享链接分析不在当前路线图，也不预埋对应 Manifest、执行协议或安全层。现有 HTML 导出和分享链接仍只作为人类消费看板的已有能力；未来如有真实需求，再重新立项。

### P2：验证 AI 开发效率

评测工具已经完成，但真实成对试验按产品决定暂缓；这不阻塞 Runtime 工程工作，也不允许预设 Token 节省结论。

- [x] 把架构上的封装转化为真正傻瓜式的作者体验：CLI 文档与 Scaffold 按任务渐进披露能力。普通声明式看板默认只提供 `Adapter → Source → View → Layout` 最小路径；只有任务实际需要时，才加载 Control、Interactive Transform、Custom Renderer 及其传递依赖契约，避免 AI 或人类为简单看板阅读完整 Runtime 上下文。
- [x] 为渐进披露建立机器可读路由与回归：CLI 能根据任务/组件返回最小闭包，Scaffold 提供 minimal、interactive、custom-renderer 等明确层级；每条路径独立通过 `validate → report → visual-check`，并检查文档没有引用未进入当前层级的内部概念。
- [ ] 使用相同模型、客户端、权限和时间预算，对五类固定任务执行多次 Dataviz / standalone HTML 随机顺序成对试验。
- [ ] 发布原始 JSONL、环境说明、逐项验收证据、真实 input/output Token、首次成功率、修正轮次和耗时。
- [ ] 根据真实 friction 压缩 focused context、CLI docs 和 Scaffold；不预设固定 Token 上限或节省比例。

评测协议已从正式产品文档移入仓库维护工具 [tools/authoring-evaluation/README.md](tools/authoring-evaluation/README.md)。

### P3：规模与性能证据

- [x] Arrow 传输记录行数、字节和耗时；Renderer 记录 mount/update/empty/failure/耗时。
- [x] `benchmark runtime` 等待传输、Interactive Transform、Repeat reconciliation 和已挂载 View 进入稳定状态，并分别记录 Query、报告生成和页面就绪时间。
- [x] 150K 行真实浏览器回归覆盖声明式 Metric、browser-js Worker 与 Custom Canvas 聚合。
- [x] 固定并运行 10K、100K、1M 行 Query → Arrow → Interactive → Renderer 基准，记录 CLI 峰值 RSS、浏览器进程树 RSS、页面耗时和三轮 dispose 回落；原始结果见 `benchmarks/results/`。
- [x] 依据 1M 证据把 Worker/Data API 的 groupBy 改为单遍流式聚合：页面就绪中位数约降低 23%，浏览器峰值增量约降低 20%。当前不实现通用服务端分页或 Record Batch DSL；原始明细 View 另行基准触发。

### P3：浏览器可靠性

- [x] Chromium 覆盖独立分支渐进发布、失败隔离、取消后终态、空 View、大数据 Arrow 和局部重绘。
- [x] 当前完整 E2E 契约套件在 Chromium、Firefox、WebKit 通过，覆盖渐进 Query/Interactive 分支、Selection 级联、局部更新、Perspective 与 HTML Export。
- [x] Chromium、Firefox、WebKit 均通过 390×520 Query Header 内联面板、显式开合、单列响应式、内部滚动、Select 键盘/ARIA，以及 Perspective 三轮 dispose/reload/wheel 恢复矩阵。
- [x] Control、View、Section 七状态矩阵和 Select 10/100/1,000 真实选项 Story 已进入 Gallery 与 Chromium 契约测试。

### P3：内部归属与可维护性

这些工作不改变当前 DSL，但会降低下一次替换前端框架或拆分 Runtime 的迁移成本。

- [x] `view.declarative`、`section.declarative`、`data.pipeline` 和 `presentation.shell` 已迁入 owner Package；21 个 Package 均为 package-owned，Runtime 内没有同功能副本。
- [ ] 按 Runtime Manifest、Output Store、Interactive Scheduler、Selection Binding、Renderer Lifecycle 拆分大型 `canvas-runtime.js`，并通过构建步骤输出单一浏览器资产。
- [ ] 按 parse/load、cross-file contract、asset validation、catalog/navigation 拆分大型 `workspace/loader.py`；稳定错误 code 和 CLI 输出不得随物理拆分漂移。

### 开源发布

- [x] 完成 `0.12.0` 本地发行门禁：402 项非浏览器测试、Chromium/Firefox/WebKit 各 52 项 E2E、四个示例 Workspace strict validate、21 个 Component Package 检查，以及 wheel/sdist/pip ZIP 内容审计和独立 Python 3.12 全流程安装冒烟全部通过。
- [x] 正式产品帮助、README 与三种发行归档不包含 Authoring Evaluation 命令或实现；维护工具只存在于 `tools/authoring-evaluation/`。
- [ ] 维护者决定许可证并添加正式 `LICENSE`；许可证未定不阻塞开发，但阻塞正式对外授权。
- [ ] 添加 `CONTRIBUTING.md`，说明安装、validate/test、Runtime/Component 变更和 PR 验收。
- [ ] 正式 GitHub Release 发布 wheel、sdist、pip ZIP、SHA-256 和远端 CI 记录。

## 按真实需求触发

以下能力不进入当前承诺：`number-range`、month/quarter/year 日期控件、Transfer/Entity Picker/Drawer、单文件内联 Pyodide 和多套命名 Presentation。只有真实 Dashboard 或框架替换证明现有边界不足时才实现。Analysis Plane 的范围单独以 P1 末尾的本地 Workspace 闭环为准。

当前是可信单机工具，不做多租户 CPU/内存配额或不可信代码沙箱。

当前只支持一个 Dataviz Server 进程写一个 Workspace/报告目标；进程内锁不承诺跨进程协调。Runtime 并发上限在 Server 启动时创建，修改后需要重启。可信 Python Source 可以主动把任意值写入 Output，因此框架的凭据脱敏是错误/日志防线，不替代看板作者的数据最小化责任。

## 明确非目标

- 旧实验契约兼容层、自动迁移或双协议 Runtime。
- 可编辑数据逻辑、依赖、布局或样式的通用可视化开发器；Mosaic/坐标布局和旧 Widget 协议。
- 让 Pyodide/Python 直接操作 DOM 或成为第二套 View Renderer。
- Interactive Transform 隐式访问 Adapter 或重新查询 Source。
- 为 Analysis Plane 复制 Dependency Contract、Query Executor、InteractionExecutor 或 Browser Runtime。
- 让 AI 通过图像像素反推本可直接读取的 Base/Derived Output。
- 为 HTML Analysis Capsule 或远程分析预埋空 Manifest、执行协议、安全层或第二套 Runtime。
- 在没有真实需求和评测证据前增加空接口、Runtime 或重复组件。

## Definition of Done

公开能力必须同时具备：严格 Schema 与稳定错误码、`validate` 提前发现、机器可读 CLI 文档、默认样式和扩展 hook、契约与真实浏览器测试、Server/HTML 一致行为、局部更新与状态隔离，以及准确的 README/DESIGN/CHANGELOG。Analysis Plane 还必须证明 Output 语义和可信度可审查、Catalog 可重建且并发安全、CLI 复用 Server/Browser Runtime 的同一执行语义、Result/Evidence 携带可验证 provenance，且 Promote 只产生可 validate 和 Git 审查的普通 Workspace 变更。计划项只有在实现、测试和文档都完成后才能勾选。

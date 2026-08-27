# Changelog

Dataviz 的 package、DSL、Component Registry 与浏览器 Runtime 分别版本化。这里记录使用者可观察到的变化；字段细节以 `dataviz schemas` 和 `dataviz components` 为准。

## Unreleased

## 0.8.0 — 2026-08-26

### Unified Renderer lifecycle

- Plotly、ECharts 与 Perspective 统一遵守平台行为矩阵：`mount → update → empty → restore → interaction → resize → dispose → export`；Custom Renderer 作者接口仍保持精简的 `validate → mount → update → dispose`。
- 首屏 Server/HTML bootstrap 不再绕过 View Package，而是按真实 View ID 注册到同一实例状态表；后续更新、空集、恢复、Resize 与销毁因此只有一个生命周期 owner。
- 空数据成为同步终态：View 立即发布 Empty 并释放旧实例；数据恢复时创建唯一的新实例，不保留旧坐标轴、图例、透视状态或事件监听器。
- Perspective Worker、Table 与 Viewer 改由单个 Renderer 实例共同拥有和释放，不再跨 View 生命周期共享 Canvas 全局 Worker；加载、建表、恢复、更新与销毁均有有界终态，外部资产或引擎停滞时回退普通 Table，不会永久 Loading。
- Plotly/ECharts 交互监听和 ResizeObserver 由平台 Chart Service 管理，重复 update 不会叠加回调；Perspective 的 resize/dispose 也进入同一指标与错误边界。
- Runtime 暴露 mount、update、empty、restore、interaction、resize、dispose、failed 与耗时指标，便于 Gallery、Visual Check 和浏览器回归定位生命周期缺口。

### Component contract and verification

- Component Registry 升级为 `4.2.0`，新增 `view.renderer-lifecycle` 契约；`view.declarative` 与 `renderer.custom` manifest 明确区分作者 hooks 和平台矩阵。
- Chromium、Firefox、WebKit 在 Server Canvas 与 portable HTML 中共同覆盖 Plotly、ECharts、Perspective 的八阶段矩阵，并保留 ECharts 图例更新与 Perspective 空集恢复专项回归。
- 373 项当前测试契约、全部示例 Workspace strict validate、20 个 Component Package（60 个组件、38 个 Story、72 个测试声明）检查，以及 wheel/sdist/pip ZIP 独立 Python 3.12 安装与报告导出冒烟通过。
- CLI Renderer 文档、Design、Product Architecture 和 Plan 同步记录唯一生命周期 owner、空集语义及 Export 同构要求。

## 0.7.2 — 2026-08-26

### Perspective empty-state lifecycle

- 当最后一个 Selection 值被取消、结果变为空集时，Perspective View 立即发布统一的 Empty 状态，不再等待 Perspective 内部 `replace([])` / `flush()` 超时并残留旧透视结果。
- 旧 Perspective 实例改为后台释放；数据重新出现时按 Empty → create 生命周期建立唯一的新实例，避免异步清理覆盖恢复后的 View。
- Server 与导出 HTML 共用同一 View Package 行为。

### Verification

- Chromium、Firefox、WebKit 均覆盖最后一个选项取消后 2 秒内显示空状态，以及重新选择后恢复唯一 Perspective 实例。
- 导出 HTML 覆盖相同的空集与恢复流程；既有 Perspective 滚动、样式、重复 dispose/restore 回归通过。

## 0.7.1 — 2026-08-26

### Runtime Control impact

- Dashboard Selection 的影响计数不再把编译期作用域上限误报为实际受影响 View 数量。Schema 尚不可判定时显示 `Up to N views`，Base Output 加载后按真实字段契约收敛为准确计数。
- View 局部重绘与影响计数共用同一套运行时适用性判断；Server 页面和导出 HTML 行为一致。
- Table Schema 随 JSON/Arrow Output 一起发布到浏览器，0 行结果也能可靠判断 Selection 是否适用。

### Verification

- Source Study 浏览器回归确认查询前显示 `Up to 3 views`、查询后及导出 HTML 均显示 `2 views`。

## 0.7.0 — 2026-08-26

### Breaking Selection, Control Binding and Layout contracts

- Dashboard 升级为 `dataviz/dashboard/v7`、Presentation 升级为 v2、Dependency Contract 升级为 v4、Browser Runtime 升级为 v5，并新增 Layout Contract v1；不提供兼容分支。
- Selection 统一保存 `{intent, values}`；`explicit + []` 是明确空集，`all_available` 随候选域扩张。optional Single Select 支持 Clear，required Single 禁止 clearable。
- View 可用一条 `control_binding` 双向绑定现有 Selection Control；一个 Control 最多一个 writer View，Plotly/ECharts/Table/Custom 共用类型化 Action 和 canonical commit。
- Section/View 顺序、模板、columns 与 span 全部属于 Dashboard；Presentation v2 删除结构布局字段。默认 Renderer、Server/HTML、AI context 与 validate 共用 `dataviz/layout-contract/v1`。
- Selection 使用 `depends_on: [dashboard.<id> | section.<id> | view.<id>]` 只声明直接父节点。Compiler 相对当前 owner 解析 canonical key，生成传递祖先/后代和稳定拓扑顺序，并拒绝未知引用、Compute 父节点、越界和完整环路径。
- 支持同一 View 内的显式多级候选关系，例如 `dates depends_on view.dow`；Dashboard、Section 与 View 的跨层依赖继续遵守结构作用域，不能跨兄弟 Section/View。
- Server 与导出 HTML 统一按 `control_order` 协调候选域并一次提交 canonical Selection 快照；上游收缩/扩张保留 `all_available` 与 `explicit` 用户意图，只重绘实际受影响的 View。
- `dataviz validate` 在查询前检查 Control DAG 与可静态确认的候选关系字段；浏览器对 Schema 未声明的实际行关系保留运行时错误边界。

### Verification

- Dependency Contract、Value Contract、Validate 与 Runtime 定向测试覆盖直接边、传递链、同 View 依赖、非法作用域、未知父节点、Compute 父节点和环。
- 真实 Chromium 覆盖既有 Dashboard→Section→View 级联，以及同 View `dow → dates` 在 Server 和导出 HTML 中的收缩、恢复与全选意图。

### Semantic authoring and state evidence

- `validate` 升级为 `dataviz/validation/v3`，在最终 Layout/Dependency/Renderer 配置上输出稳定 error/warning/advice；非确定性 advice 不阻塞 strict。
- 新增 `inspect-layout` 和 `dataviz/layout-inspection/v1`，公开最终 rows、span、来源与 custom mount 边界。
- 新增 `dataviz/state-snapshot/v1`；默认 Dashboard、Section、View 自动展示 committed/applied 状态，Query/Compute draft 明确标记为待应用，未提交 Query 不会伪装成当前 Dataset 的上下文。

### Runtime, CLI and browser verification

- browser-js/browser-python 未显式声明时默认 `trigger: auto`，server-python 默认 `apply`；Scaffold 与文档使用同一规则。
- `query`、`output`、`compute` 默认输出紧凑 `dataviz/cli-result/v1`，`--detail debug|full` 才展开执行证据。
- Component Registry 升级为 4.1.0；Custom Renderer 可通过 `context.charts.plotly/echarts` 复用平台 Theme、滚轮、Resize、Update 与 Dispose。
- 新增 `visual-check`，真实加载 Server/Report 并输出 `dataviz/visual-check/v1`、截图和稳定几何/Loading/Console 诊断；不判断主观美感。
- Interactive Runtime 按完整输入指纹合并同一时刻的重复请求，消除 Base Output 与父页面同步竞态造成的无意义 Worker 重启；输入真正变化时仍按 generation 取消旧任务。

### Verification

- 335 项 Python 契约测试、Chromium 32 项及 Firefox/WebKit 各 31 项真实浏览器回归通过；5 个代表性 Workspace 严格校验为 0 error / 0 warning。
- 20 个 Component Package（59 个组件、38 个 Story、71 个测试声明）通过 Registry 检查；wheel、sdist 与 pip ZIP 通过内容审计和独立 Python 3.12 全流程安装冒烟。
- 同一 wheel 在 Python 3.11、3.12、3.13、3.14 完成干净安装、版本、Component Registry、Scaffold 与严格校验冒烟。

## 0.6.1 — 2026-08-25

### Query Parameter layout

- Header Query Parameters 的默认网格从无限 `auto-fit` 改为最多 4 个可读轨道；超宽页面不再把 7–8 个控件挤在同一行，窄容器会自然降为 3、2、1 列。
- `control_panels.query.columns` 现在明确表示响应式最大列数。`control_components.<key>.span: 1|2` 可显式安排宽控件，但 RangePicker 默认仍只占一列，避免在 2K 屏幕上被放大到接近半个页面。

### Verification

- 312 项 Python 契约测试、Chromium/Firefox/WebKit 各 26 项真实浏览器回归、Ruff、Component Package 检查与全部示例 Workspace 严格校验通过。
- wheel、sdist 与 pip ZIP 均通过内容审计，并分别在独立 Python 3.12 环境完成安装与 CLI/报告冒烟。

## 0.6.0 — 2026-08-25

### Breaking Query Input contract

- Dashboard 升级为 `dataviz/dashboard/v5`，Source、Dataset Transform 与 Interactive Transform 升级为 v2，Dependency Contract 升级为 v2，Browser Runtime 升级为 v3。
- 删除所有执行节点的 `query_params`。SQL/Python Source、Dataset Transform 和三种 Interactive Transform 统一使用 `query_inputs`，把 Dashboard canonical Query Parameter 映射为节点私有 alias；未声明的全局参数不能从执行上下文读取。
- Dependency Contract 明确区分节点间 `data_inputs` 与参数 `parameter_inputs`。Planner、Server/Browser Runtime、HTML Export、Resolved SQL 证据、缓存键和 AI Context 都消费同一个编译结果，不再各自猜测参数边。

### Date range and relative defaults

- `date_range` Query Parameter 可以通过 `{parameter: <id>, part: start|end}` 投影为两个标量，直接绑定 SQL 的两个 named placeholders，或进入 `context.query_inputs`。
- Query Parameter 的 `date` 与 `date_range` 支持结构化相对默认值：`anchor: today` 加整数日偏移。`today` 严格按 `workspace.context.timezone` 解析，不依赖 Server 操作系统时区。
- 相对表达式在页面初始化或 CLI Run 创建时转换为具体 ISO 日期；Query Run、tab 状态、缓存和导出 HTML 保存具体值，不会在报告打开时重新求值。Compute/Selection Control 不接受相对默认值。
- `dataviz validate` 会在查询前拒绝未知 Query Parameter、错误的 `part` 类型、非法时区、偏移语法、反向日期范围和旧字段。

### Tooling and migration

- Schema Catalog、CLI docs/context/dependencies、Scaffold、示例 Workspace、Benchmark、测试 fixture 和设计文档整体迁移到当前严格契约，不提供兼容 alias 或自动迁移器。
- 新增 Server 集成、真实 SQL 与 Browser JS Worker 回归，覆盖相对日期固化、`date_range` start/end 投影及节点本地 alias 隔离。

### Verification

- 312 项 Python 契约测试、Chromium/Firefox/WebKit 各 25 项真实浏览器回归、Ruff、20 个 Component Package（58 个组件、38 个 Story、70 个测试声明）全部通过。
- 8 个 Workspace、11 个 Dashboard 通过严格 `validate`，合计 0 error、0 warning；wheel、sdist 与 pip ZIP 均通过内容审计和独立 Python 3.12 干净安装的 `version → schemas → components → init → validate → dependencies → report` 冒烟，报告离线可用且 0 warning。

## 0.5.4 — 2026-08-25

### Documentation and scaffolding

- 明确 Custom Renderer 直接调用 `Plotly.newPlot` / `Plotly.react` 时不会继承声明式模板配置，必须默认传入 `scrollZoom: false`；AI 文档、组件契约与 Scaffold 仅在用户明确要求图内滚轮缩放时才允许设为 `true`。

### Verification

- 336 项 Python/真实浏览器 Runtime 测试、Ruff、Component Package 检查和四个代表性 Workspace strict validate 通过。
- wheel、sdist 与 pip-installable ZIP 均在全新 Python 3.12 环境完成安装、版本/Schema/组件检查、Workspace 初始化、严格校验与无警告离线 HTML 报告导出。

## 0.5.3 — 2026-08-25

### Changed

- Plotly 声明式模板默认关闭滚轮缩放，让图表区域内的滚轮继续滚动 Dashboard 页面；确有探索需求的 View 仍可通过 `config.scrollZoom: true` 显式开启。

## 0.5.2 — 2026-08-25

### Fixed

- Overlay Runtime 使用浏览器 top layer 脱离 `filter` / `transform` containing block，并为不支持 top layer 的浏览器保留坐标补偿；修复 Header Controls、Pipeline 和 Selector 浮层向右溢出，以及原生 `details` 首帧闪到未定位位置的问题。
- 无 Query Parameter 的 Dashboard 继续隐藏空参数区，但 Run 控件会明确显示 `No parameters`；有参数的 Dashboard 仍默认展开 Header 内联参数区并按 tab/Dashboard 记忆状态。

### Verification

- Chromium、Firefox、WebKit 覆盖桌面和窄视口浮层边界、内部滚动、键盘关闭及参数区可发现性；完整 Python 契约测试、Component Package 检查和 Feature Showcase strict validate 通过。

## 0.5.1 — 2026-08-25

### Dependency architecture

- 新增 `dataviz/dependency-contract/v1`，一次编译 Query inputs/outputs/order、Interactive data/Query/Selection/Compute edges、Control scope/cascade/domain/impact、Named Output consumers 与 View inputs。
- 每个不可变 Dashboard load snapshot 以并发安全方式只编译并缓存一个契约；Query Parameter 新增最终受影响 Query/Interactive/option Control/View 闭包，Query 节点新增下游 View 与 option Control 索引。
- 契约编译直接拒绝环、未知 Output、browser Runtime → `server-python` 非法依赖和越界 Control consumer；Loader 的容错扫描只用于无效配置诊断，不再充当第二张运行时图。
- Query Planner、Interactive Planner、Loader、Server Pipeline、Canvas Runtime、HTML manifest、Web Component Adapter、CLI 和 AI context 改为消费同一契约；删除浏览器按 DOM scope 重建 Control DAG 和 Portable Selection Contract 的重复所有权。
- Query/Interactive 节点只能读取显式声明的参数；Browser Transform/View 注册会核对 data inputs、Control inputs、Query Parameter inputs 与 Output names，注册配置只承担 drift assertion，调度与 View 取数继续消费编译契约。
- 新增 `dataviz dependencies WORKSPACE DASHBOARD [--format json]`，区分 Control scope、候选/已声明数据 View、runtime field check、Interactive consumer、派生 View、内容绑定和级联边。
- static Select 在参与上游级联时也会绑定明确的 Base option domain；修复 static Section Control 永久停在 pending、导致内容绑定不更新的问题。
- Overlay Runtime 改为按 visual/layout viewport 的最小边界和真实 border-box 几何定位，修复 Firefox 中浮层安全边距少 2px 的跨浏览器差异。

### Server Header

- `Run query` 与 Query Parameters 合并为一个 split control；主按钮执行查询，相邻箭头显式展开或收起参数区。
- Query Parameters 默认展开并成为 Header 的内联第二行，参与正常文档流并把 Canvas 向下推；它不再注册到 Overlay Runtime，因此点击外部或按 `Esc` 不会意外收起。
- 参数区的开合状态按浏览器 tab 与 Dashboard 保存；无 Query Parameter 的 Dashboard 自动退化为普通 Run 按钮，参数校验失败时会显式展开参数区。
- Dashboard/Section/View Controls 与 Pipeline 继续作为临时浮层，由外部点击或 `Esc` 关闭；Query Parameters 与临时 Controls 的交互所有权不再混用。

### Verification

- 完整 Python 契约套件与 Chromium、Firefox、WebKit 全量 Runtime 回归通过；覆盖渐进分支、动态与静态级联、局部 View/内容更新、三种 Interactive Runtime、Perspective 和 HTML Export。
- 新增并发首次访问测试，以及“注册后篡改原始 Transform/View inputs 仍只按 Contract 运行”的三浏览器回归，防止配置副本重新成为第二事实源。
- 桌面与 390px 窄屏三浏览器回归覆盖 Header 文档流位移、内部滚动、状态恢复、子级 Select 几何，以及 `Esc` 只关闭临时 Controls。

## 0.5.0 — 2026-08-25

### Breaking Dashboard contract

- Dashboard 严格契约升级为 `dataviz/dashboard/v4`。所有 Select 必须通过 `options.mode` 明确候选域来源；删除顶层 `choices`、`options_from` 和 Dashboard v3 解析分支，不提供兼容 alias。
- `options.mode: static` 表示由 Dashboard 维护封闭 `options.choices`，可声明具体默认值；`options.mode: infer` 表示从不可变 Base Named Output 推导候选域，禁止复制会随数据漂移的 `default` 值列表。
- infer 多选使用 `initial: auto | empty` 表达初始化行为，而不是伪装成业务默认值；`auto` 编译为 `all_available` 意图，Source 域扩大时会继续包含新成员，用户明确选择的子集仍保持 `explicit`。
- Query Parameter 与 Compute Select 当前只接受 static 候选域；Selection Select 可使用 static 或 infer。动态 Selection 未指定 `options.source` 时由 Runtime 沿消费 View 追溯 Base Output，显式来源也只允许 `source:` / `dataset:` 表格 Output。

### Tooling and migration

- Scaffold、CLI Docs、Schema、Gallery、示例 Workspace、测试 fixture 与浏览器 Runtime 已整体迁移到 v4；`dataviz validate` 会在打开页面前拒绝 infer default、未知 option source、Interactive Output 和旧字段。
- Cascade Gallery 不再手工维护城市和区县默认列表；深圳、佛山、厦门、泉州等候选项直接从 Source 推导。

### Verification

- Python contract/unit suite、Ruff、Component Package 检查和五个代表性 Workspace 静态预检通过；真实 Chrome 覆盖 option domain 首次水合、上游收缩/扩张、`all_available` 与 `explicit` 两种级联路径。

## 0.4.1 — 2026-08-25

### Fixed

- 动态多选现在显式保存 `all_available` 与 `explicit` 两种用户意图。父级范围重新扩大时，原先选择全部可用项的下级会自动纳入新增项；用户明确选择的子集则只保留有效交集，不会被擅自扩大。
- Select、Checkbox、Cascader 与 TreeSelect 统一使用 `runtime.control` 的选项域协调算法，避免各组件分别实现级联状态并产生语义漂移。
- 多选意图会随浏览器 tab、Canvas iframe 和交互 HTML 导出持久化；Server 页面与导出报告保持一致。

### Verification

- 新增真实 Chromium 回归，覆盖“取消广东 → 重新选择广东 → 城市恢复三个 → View 恢复六行”及显式子集不扩大的路径。

## 0.4.0 — 2026-08-24

### Breaking component contract

- Data Entry 升级为 Component Registry v4：13 个独立 `control.*` Package 覆盖 Input、InputNumber、AutoComplete、Checkbox、Switch、Radio.Group、Select、Checkbox.Group、Cascader、TreeSelect、DatePicker、RangePicker 与 Slider。Query Parameter、Selection 和 Compute 共用同一 Registry/Renderer。
- 值语义、Dashboard/Section/View scope 与 UI Component 成为三个正交维度；`dashboard.yaml` 保存可验证逻辑，`presentation.yaml.control_components` 只选择交互表现。
- RangePicker 使用一个触发器和一个浮层共同编辑开始/结束日期，支持双月、窄屏单月、范围预览、preset、键盘导航和视口安全定位。
- Radio.Group 只展示真实单选项，不合成 `All` 或 `Clear`；Select/Checkbox.Group 的批量操作仅属于多选，并遵守 `required`、`clearable` 与 `max_selected`。
- 删除实验期 `selector.*` Package、`runtime.selector`、`segmented`、`date-range` 和 Presentation `selectors/template` 接口，不提供兼容 alias。

### AI authoring

- 新增 `dataviz docs data-entry-components`、13 种 `dataviz scaffold control.*` 配方，以及每个 Package 对 Ant Design 语义采用/省略项的机器可读声明。
- Component discovery、Scaffold 与 Validate 共享同一 Registry contract，使 AI 可以只读取当前控件的值类型、字段、示例和错误边界，而不必理解整个浏览器 Runtime。

### Verification

- 完整 Python、Chromium、Firefox、WebKit、Component Package 与真实 Gallery 视觉验收通过；新增 Data Entry 语义、交互与机器可读契约测试。

## 0.3.3 — 2026-08-24

### Presentation

- 新建 Dashboard 默认使用现代靛蓝 `business` Theme：冷灰页面、白色卡片、低阴影与紧凑数据表；`plain`、`editorial`、`terminal` 仍是显式可选风格。
- Server、导出 HTML、Data Entry Control、Plotly、ECharts、普通 Table 与 Perspective 统一消费 Theme token；Renderer 的显式 options/config 继续拥有更高优先级。
- Gallery 增加四种 Theme 的同构预览，并把等待、失效与损坏 Canvas 的状态页统一到 Server 视觉体系。

### Authoring

- 新增内置 `dataviz docs design-language` 与人类可读视觉规范，向 AI 提供信息层级、语义 Token、组件规则、反例和样式验收清单。
- `theme.business` 等 Theme Component contract 公开完整的 30 个稳定视觉 Token，方便 AI 优先做语义覆盖而不是重写组件结构。

### Verification

- 完整 Python、Chromium、Firefox、WebKit、Component Package 与真实 Gallery 视觉验收通过；新增视觉语言与 Theme Token 的机器可读契约测试。

## 0.3.2 — 2026-08-24

### Added

- Python 发行包正式命名为 `ai-dataviz`；Python 模块与终端命令继续保持简洁的 `dataviz`。
- `dataviz serve` 默认监听 Workspace 文件；跨平台 watcher 会忽略 `.dataviz`、虚拟环境和构建缓存，并把编辑器的连续写入防抖合并为单调 revision。
- 新增 tab 校验的 Workspace SSE 事件和 `dataviz/workspace-change/v1` 协议，按 `navigation / canvas / analysis / query / server / invalid` 说明影响范围。
- Server Header 新增显式 `Reload` 与更新状态条；可用 `--no-watch` 关闭主动监听，但请求时重读仍保留。
- `benchmark --browser-runtime` 升级为 v3：支持 Query Parameter override、Chromium/Firefox/WebKit、重复 load/dispose，以及 CLI 峰值 RSS、浏览器进程树 RSS 和可用 JS heap 口径；仓库增加固定 10K/100K/1M fixture、运行脚本和原始结果。

### Runtime

- Presentation、View、CSS/Canvas 改动自动重载 iframe，并保留当前 Query Run、scoped Controls 与 Canvas 滚动位置。
- Interactive Transform 或其 Control Contract 改动复用当前不可变 Base Output 并重建交互分支；不会回退为重新查询 Source。
- SQL、Source 数据文件、Dataset Transform、Adapter、Query Parameter 或 Query 可达图变化只把当前结果标记为 `Outdated`，用户明确点击 Run query 后才执行昂贵查询。
- Workspace Runtime/进程级配置进入独立 `server` 状态并提示重启，不伪装成已经动态应用。
- browser-js Worker 与公开 Data API 的 `groupBy().aggregate()` 改为单遍流式聚合，每组只保留 key 与 count/sum/min/max，不再为大 Arrow 输入物化并长期持有全部分组行。

### Correctness

- 新配置无法加载或引入新的静态错误时不发布候选 Workspace，当前 Canvas 保持可用并显示结构化诊断；下一次有效 revision 会从最后的完整快照恢复。
- 活动 Query 固定使用启动快照；如果运行期间 Query Contract 变化，该 Run 即使成功也不会提交为当前结果。
- 热更新按已解析声明和实际引用资产计算语义签名；Dashboard 目录中的无关临时文件不再重载 Canvas。保存 Source 后立刻点击 Query 时，Server 会先发布该文件 revision，并让 Run 返回它实际捕获的 revision，避免把基于新定义运行的结果误判为 Outdated。
- 页面刷新和 tab Run 恢复会在 Server 再次核验当前 Query Contract，不能因为错过浏览器热更新事件而把旧数据显示为 Ready。

### Verification

- 新增 watcher 分类、无效写入恢复、`--no-watch` fallback、旧 Run 恢复和真实 Chromium 热更新回归；浏览器测试 Server 现在启用真实 lifespan，确保 watcher 启停也进入契约测试。
- Chromium、Firefox、WebKit 新增 390×520 Query Control 几何/单列/内部滚动/键盘/ARIA/外部关闭，以及 Perspective 三轮 dispose/reload/wheel 恢复矩阵；窄屏固定列数现在由 `presentation.shell` 强制降为一列。
- 1M 固定聚合链路的页面就绪中位数由约 1043 ms 降至 804 ms，浏览器进程树峰值增量由约 496 MB 降至 395 MB；该证据不外推为 1M 原始明细 View 预算。

## 0.3.1 — 2026-08-24

### Fixed

- 修复必填动态 View Selection 与其消费的 Browser Interactive Transform 之间的启动环。Selection option domain 现在默认追溯到不可变 Base Output，也可用 `options_from` 显式指定 `source:` / `dataset:` 表格 Output。
- Canvas 首次运行改为 `Base Output hydration → Selection reconciliation → View render → Interactive scheduling`；一个 Selector 的 DOM option 尚未生成时，不再清除 canonical default 或阻断无关 Base View，导出 HTML 与 Server 使用同一顺序。
- Browser Interactive Transform 的 queued/loading/ready/stale/error/cancelled/unavailable 状态会回传当前 frame 的 Server `Pipeline` 面板，不再在实际完成后保持灰色。
- `canvas-ready` 现在只在 Base Output 水合与首次 canonical Control 提交完成后发布；父页面通过该握手恢复 tab-local 状态，不再与初始化并发并覆盖用户刚做出的 Selection。
- Selection 事件在同一事件批次内立即合并提交，不再依赖延迟定时器；浮动 Control 面板的入场动画也不再越过运行时计算的视口安全边距。

### Validation

- `dataviz validate` 会拒绝未知、非表格、字段不匹配、无 Base domain 或引用 Interactive Output 的 `options_from`，避免在用户打开页面后才暴露循环或永久 pending。
- 新增 Server 与独立 HTML 回归，覆盖 `required dynamic View Selection → browser-js → same View`、Base View hydration、父页面 Pipeline 状态同步和 Canvas 初始化握手；完整 Runtime 契约在 Chromium、Firefox、WebKit 通过。

## 0.3.0 — 2026-08-24

### Breaking contract

- Dashboard 严格契约升级为 `dataviz/dashboard/v3`。Query 后只有 Dashboard/Section/View scoped `controls`，每项必须显式声明 `kind: selection | compute`。
- 删除 v2 的 `dashboard_selections`、Section/View `selections`、Dashboard `compute_parameters`，以及 Interactive Transform 的旧 `selections` / `compute_params` 字段；不提供 alias、迁移分支或双协议 Runtime。
- Interactive Transform 通过 `selection_inputs` / `compute_inputs` 把局部 alias 映射到 canonical scoped Control key，调度器仍保留两类独立 delta、提交周期和局部失效路径。

### Changed

- Server 与导出 HTML 只保留 `Parameters` 与 `Controls` 两个一级入口；Controls 在同一自适应托盘内按 DATA/LOGIC 分组，支持 Dashboard/Section/View 局部容器和 Presentation 稀疏视觉覆盖。
- 内容绑定统一为 `{{ controls.dashboard.<id> }}`、`{{ controls.section.<section-id>.<id> }}` 和 `{{ controls.view.<view-id>.<id> }}`；Query 仍使用 `{{ parameters.<id> }}`。
- Scaffold、CLI docs/schema/context、Gallery、仓库示例与 fixture 已全部迁移到 v3，旧字段由 `validate` 直接拒绝。

### Runtime

- `selection_inputs` 成为三种 Interactive Runtime 共享的数据边界：Runtime 先对具有对应字段契约的表输入应用 include Selection，再执行 Compute 逻辑。
- Server Python 的 `context.table()` / `context.input()` 与 browser-js/browser-python 的 `context.inputs` 看到相同的已选样本；`context.selections` 仍可用于日志、标签和确定性分支。
- `data.pipeline` 拥有 Browser Selection-before-Compute 边界，Server 使用同契约的 `ExecutionContext` 筛选；无关表输入保持不变。

### Verification

- 新增 Server 与 Browser 回归，证明 Selection 先裁剪样本、Compute 只在已选数据上运行，且无关 View 不重绘。
- 全量 Python 测试、Browser Runtime E2E、Component Package 检查与仓库示例静态预检纳入发布验收。

## 0.2.0 — 2026-08-24

### Breaking architecture

- Dashboard 与 Browser Runtime 升级为严格的 `dataviz/dashboard/v2`、`dataviz/runtime/v2`；查询阶段使用 Dataset Transform，取数后计算使用 Interactive Transform。
- 新增独立 Compute Parameter，以及 `server-python`、`browser-python`、`browser-js` 三种 Interactive Runtime；三者统一产出 Named Output。
- Query DAG 与 Interactive DAG 分离；Query Run 固化 Base Output，交互结果按 tab、Dashboard、Run、Transform 和 generation 隔离。
- HTML Export 强制声明 `interactive`、`snapshot` 或 `unavailable`，不再把 Server Python 伪装成离线交互。
- 删除旧实验性 Transform 字段、自动迁移命令和 Runtime 兼容分支；仓库示例与测试直接使用当前严格契约。

### Added

- 新增 `dataviz compute`、Compute Control、Interactive Compute API、Pyodide module Worker 和 browser-js Worker。
- Query 与 Interactive Python 节点支持 cancel、progress、`context.log(...)`、结构化执行日志 Artifact 和完整 traceback；日志可通过 session 隔离的 Artifact API 获取，Query 节点可直接在 Sources 证据面板检查。
- 页面导出采集 canonical Canvas snapshot，并清除旧 tab 状态中已经不属于当前 Dashboard 的 Selection key。
- 新增五类固定 AI authoring 对照任务、带任务/prompt/输入哈希的 `authoring prepare`、`authoring verify/assess`、`authoring-event/v3` trial identity 与逐项验收证据，以及 `authoring tasks/protocol/compare` 成对评测；只有身份一致、prompt/输入完整且两边全部验收通过的 pair 进入效率聚合。
- `authoring start` 返回按顺序可执行的 `next_steps`，benchmark 的 finish 提示保留必需的 trial directory，并安全引用包含空格的路径。
- `benchmark --browser-runtime` 升级为浏览器 Runtime v2 基准：分别记录 Query、报告构建、页面稳定时间，以及 Arrow 行数/字节/耗时、Renderer 生命周期和最终 View 状态。
- 核心写入边界增加事务性发布：Scaffold、AI trial、持久缓存、HTML/manifest/assets 与发行 ZIP/checksum 在失败时保留上一份完整结果。
- Artifact、缓存与代码依赖使用流式 SHA-256；大文件复制采用校验后的原子流式写入，避免整文件缓冲。
- Gallery 新增 Selector、Compute、View、Section 的 ready/loading/stale/empty/error/cancelled/unavailable 七状态矩阵，以及实际包含 10、100、1,000 个原生选项的 Select Story。
- Query Run 现在公开 `server_interactive_inputs`，显式列出后续服务端交互计算依赖的 Base Output；Artifact 与缓存只写入 Workspace `.dataviz`，不污染可分享 Dashboard。

### Changed

- 删除与 `components` 重复的公开 `dataviz templates` 命令；模板发现统一走 `components`、`schemas`、`docs` 与 `scaffold`。
- `components --check` 明确只验证 Package 元数据、资产与测试声明；行为测试由 pytest/浏览器 E2E 执行。
- `data.pipeline`、`view.declarative`、`section.declarative`、`presentation.shell` 完整迁入各自 owner Component Package；13 个 Package 现在全部为 package-owned，删除 `declarative-runtime.js` 和 Runtime 中的重复实现。

### Fixed

- Query Run 建立后即可向 Canvas 提供 Interaction endpoint；依赖已就绪 Base Output 的 Server/Browser Interactive 分支不再等待无关慢 Source，Query 完成也不再通过重载 iframe 破坏现有交互状态。
- Selection、Compute Parameter 与 Output 发布使用显式 delta；Selection 不再误触发 compute-only 分支，无关 Output 不再取消并重启 active Transform，值未变化的 Output 不再重复传播。
- 父页面与 Canvas 消息校验 `dashboard_id + run_id + frame_id`，旧 iframe 或其他 Run 的迟到消息不能更新当前 tab 状态。
- 删除旧 Server capability fallback；导航显示名严格由 Dashboard 文件夹末级名称决定，不再回退到页面 title。
- Query/Compute/Selection 在 Python、父页面与 Canvas 共享严格 Value Contract；安全整数保持整数 wire shape，超范围整数不再被浏览器静默截断，空日期范围固定为 `[]`，typed choice、required、min/max/step 使用稳定错误码。
- Named Output 严格校验 required/optional、kind、JSON 与 Table schema；直接返回已有 Artifact 也不能绕过声明契约。
- server-python Interactive 依赖链可复用相同 Query Run 与状态下已经完成的上游 generation；Interaction/event/cache 内存保留量有界。
- Run/Interaction 事件截断使用单调 offset，长时间轮询不会因保留窗口移动而漏掉后续事件。
- snapshot 的可选 Output 不再被误判为缺失并触发重算。
- Pyodide package catalog 对齐固定 Runtime；bundle 核对 `package.json` 版本，并按 Emscripten marker 校验核心文件、lockfile、`micropip`、传递 wheel 闭包与必需 SHA-256 后随 ZIP 分发。没有活动 browser-python 的报告不再携带 Python Worker、Pyodide URL 或 bundle 资产。
- 源码 CLI 文档固定使用 non-editable `uv sync --reinstall-package ai-dataviz`，规避部分 macOS/Python 组合忽略 hidden editable `.pth` 导致的 `ModuleNotFoundError`；发布 smoke 仍使用独立干净环境。
- 声明式 View、browser-js Worker 与 Custom Canvas 的数值聚合改为线性 reducer，大表 min/max 不再因展开数组超过 JavaScript 参数上限而崩溃。
- Arrow Table 作为 Metric 输入时不再被误判成 scalar 并显示 `[object Object]`；没有 descriptor 的 View 进入明确的 `empty` 终态。
- Live Canvas 处理 node/run cancelled；失败或取消的终态 Run 可重新打开并显示分支错误，不再因为缺失 Output 返回 500 或永久停在 rendering。
- 后台保留策略不再清理仍被活动 Interaction 消费的 Query Run 与缓存，避免长时间模型/运筹计算被误取消。
- Source/Dataset 缓存键补入 Dashboard 与节点身份，并继续由 tab session namespace 隔离；Server Interactive 只读取所属 Query Run 的不可变 Artifact，不会因 Selection/Compute 变化重新查询 Source。

### Documentation

- 仓库首页改为面向首次访问者的简明 README；稳定产品设计收敛到 `DESIGN.md`，未完成工作收敛到 `plan.md`，三者都会进入后续源码 ZIP 与 sdist。
- 删除设计文档中的安装手册、旧版本测试快照和已完成里程碑；明确当前未完成边界、放弃的旧方向与按真实需求触发的候选能力。
- 明确 Runtime 默认选择 `browser-js → browser-python → server-python` 的适用条件、server-python 无法在独立 HTML 重算，以及 Pyodide CDN/bundle 的内网与离线边界。

## 0.1.4 — 2026-08-23

### Fixed

- 默认 View Shell 现在实际渲染 `description`，并统一覆盖 Table、Perspective、Plotly、ECharts、Custom Renderer 与 Repeat View；动态 Selection 文案原地更新，Server 与导出 HTML 保持一致。

## 0.1.3 — 2026-08-23

### Added

- Dashboard、Section 和 View 内容支持作用域完整的 Selection 绑定；例如 `{{ selections.section.night_analysis.dow }}` 会显示 choice label，并在浏览器内即时更新 Section 标题而不重新查询。
- `dataviz validate` 会提前报告未知 Selection、跨 Section/View 的不可见依赖和任意表达式；完整 Canvas 可通过 `content("sections.<id>.title")` 输出可绑定内容节点。

### Runtime

- Selection 内容引用本身就是依赖声明；Section 标题变化只更新对应 DOM，View `title/text` 变化才将目标 View 加入局部重绘集合。Server 与导出 HTML 共享同一绑定清单。

## 0.1.2 — 2026-08-23

### Fixed

- `select`、Cascader 与 Tree Select 统一使用共享 `.dv-selector-panel` 浮层契约；Server 与导出 HTML 的下拉面板默认使用不透明表面，不再透出底层 Table。

### Contract

- Selector 浮层新增可选主题变量 `--dv-overlay-surface`，未设置时回退到 `--dv-panel`；Dashboard 仍可显式定制，但不需要为组件缺失的默认背景打补丁。

## 0.1.1 — 2026-08-23

### Added

- Server 的 Sources 现在是可点击 Run Evidence：所有节点展示状态、执行/缓存来源、耗时与结构化错误；SQL 节点额外展示并可复制 Resolved SQL、参数化 Driver statement、bound parameters、Adapter、SQL 文件、timeout/retry 和 query hash。
- `dataviz validate` 升级为无查询静态 preflight，支持 `--dashboard`、稳定 `dataviz/validation/v1` JSON、七个检查域、修复 hint、next actions 和 `--strict` CI 门禁。
- SQL validate 双向检查命名占位符与 Source `params`，在用户执行查询前报告 `sql_parameter_undeclared` 与 `sql_parameter_unused`。
- Dashboard、Section、View 与 Markdown 内容支持受限 `{{ parameters.<id> }}` 插值，并使用最近一次已提交 Run 的 Query Parameter。

### Fixed

- Canvas 上报完整 Selection 状态时替换历史状态；导出前再次按当前 Contract 过滤，已删除或重命名的 sessionStorage key 不再导致 `Invalid selections`。
- Perspective 自适应可用 View 高度、修复下拉层透明背景，并在短表与滚动边界释放页面滚轮。
- Sources SQL 证据在成功、缓存、超时和其他失败结果中保持一致，同时不序列化 Adapter URL、密码或环境变量 secret。

### Contract

- Resolved SQL 是只读调试预览；SQL Runner 仍只执行参数化 statement 与 bound values。
- `dataviz validate` 固定 `queries_executed=0`；静态通过后再使用 `query`、`output`、`report` 或 `serve` 做动态验证。

## 0.1.0 — 2026-08-23

### Added

- Workspace-first File、DuckDB、MySQL、StarRocks、Python Source 与 Server/Browser Transform DAG。
- Named Output、渐进式分支执行、tab/Dashboard 隔离、Arrow Table 传输和可交互 HTML。
- 声明式 View/Section/Selector、Component Package Registry、Gallery 与 Custom Renderer lifecycle。
- `docs`、`schemas`、`components`、`context`、`scaffold`、`benchmark` 与 `authoring` AI 开发接口。
- append-only `dataviz-authoring.jsonl`，记录真实首次成功、修正轮次、耗时、Token 和 friction。
- 严格 `dataviz/*/v1` Literal 以及 Web Component Runtime v1 参考 Adapter。
- Python 3.11–3.14、Chromium/Firefox/WebKit 和 wheel/sdist/ZIP 发布验证定义。
- Component Registry v3 Selection：统一 `select`，增加 `segmented`、`checkbox-group`，强化 Cascader/Tree Select 父子选择与 Date Range presets。

### Changed

- 平面 Selection 使用 `select`，搜索和虚拟滚动是它的 `auto/always/never` 能力；短列表使用 `segmented` 或 `checkbox-group`。
- `checkbox-group` 与多选 `select` 不再把显式全集归一化为空；全选保留全部值并切换为可配置的反选操作。
- Registry v3 只分发当前 13 个 Component Package，不包含旧 Registry 别名或迁移实现。Registry 对任何有 Manifest 的 Package 执行完整六文件校验。

### Contract

- Runtime 只接受当前 `dataviz/*/v1`；不存在旧字段兼容模式。
- Query Parameter 重新执行服务端 DAG，Selection 只处理浏览器现有数据。
- Dashboard 文件夹末级名称是导航显示名；`dashboard.id` 是稳定机器身份。

当前仍是 `0.x`：Breaking DSL 通过新 Schema URI、Changelog 和人工改写说明发布，不在 Runtime 中维护自动迁移或旧协议分支。

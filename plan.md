# Dataviz 实施计划

更新时间：2026-08-26

稳定设计见 [DESIGN](DESIGN.md)，代码入口见 [当前实现索引](docs/product-architecture.md)，使用者入口见 [README](README.md)。本文件只保留当前结论和仍需完成的工作，不重复记录历史迁移过程。

## 当前结论

| 领域 | 状态 | 结论 |
| --- | --- | --- |
| P0 数据执行架构 | 已完成 | Query DAG、Interactive DAG、Control/View 影响关系、Named Output、三种 Interactive Runtime、状态隔离和导出边界已统一为一份版本化 Dependency Contract。 |
| P0 Selection 状态一致性 | 已完成 | `{intent, values}` 是唯一 canonical state；明确空集、动态全选、optional Single Clear、tab/HTML/三种 Interactive Runtime 使用同一 resolver。 |
| P0 Control Binding / Linked Views | 已完成 | 一个 Selection Control 最多绑定一个可读写 View Adapter；Plotly/ECharts/Table/Custom 与面板共用 canonical state。 |
| P0 Layout Contract | 已完成 | Dashboard v7 拥有结构；Layout Contract v1 统一确定性行列、span、custom mount、Renderer、Server/HTML、AI context 与 validate。 |
| P0 最终配置有效性 | 已完成 | Semantic Validation、inspect-layout、状态摘要、Runtime-aware trigger、紧凑 CLI、Chart Service 与 visual-check 已统一消费最终契约。 |
| P0 Renderer 生命周期 | 已完成 | Plotly、ECharts、Perspective 在 Server/HTML 共用 mount→update→empty→restore→interaction→resize→dispose→export 行为矩阵；首屏 bootstrap 也进入 View ID 状态表。 |
| P1 Component Package | 当前范围已完成 | Registry v4 已覆盖常用 Data Entry、View、Section、Renderer、Repeat 和 Presentation 组件；继续扩张必须由真实场景触发。 |
| P1 AI 开发效率评测 | 工具已完成，真实试验暂缓 | 成对任务、输入完整性、逐项验收和真实 Token 记录均已实现；试验方案尚未决定，不用仓库测试伪造结论。 |
| P2 规模与浏览器矩阵 | 当前范围已完成 | 固定 10K/100K/1M 基准、流式 groupBy 优化，以及 Chromium/Firefox/WebKit 的窄屏与 Perspective 恢复组合矩阵均已有可复现证据。 |
| 开源发布 | 本地发行完成 | `0.8.0` Renderer 生命周期矩阵已通过本地发行门禁；正式对外授权仍等待许可证决定。 |

当前开发基线：Package `0.8.0`、Python 3.11–3.14、Dashboard `dataviz/dashboard/v7`、Presentation `dataviz/presentation/v2`、Source/Dataset/Interactive Transform `v2`、Dependency Contract `v4`、Layout Contract `v1`、State Snapshot `v1`、Browser Runtime `dataviz/runtime/v5`、Component Registry `4.2.0`。这些破坏式契约只接受当前严格字段，不保留旧 alias、自动迁移或第二套 Runtime。

Authoring P0 的 A–G 已进入当前 Schema/Compiler/Runtime，并由 0.7.0 统一发行。复杂实现必须留在 Compiler/Runtime：普通 Dashboard 不手写依赖图、事务、revision 或回调；常见跨图联动最多新增一条声明。

## 已完成的核心能力

### 数据、计算与状态

- [x] Dashboard v7 只有 Query Parameter 与 scoped Controls 两个入口；Control 在 Dashboard/Section/View 统一声明，并以 `kind: selection | compute` 保留不同 delta、提交周期和失效路径。
- [x] Source、Dataset Transform 与 Interactive Transform 统一使用 `query_inputs` 将 canonical Query Parameter 映射到节点本地 alias；删除节点级 `query_params`。SQL placeholder 与三种 Python/Browser Context 只能读取本节点声明的 alias。
- [x] `date_range` 可通过 `{parameter, part: start|end}` 投影为两个标量；Dependency Contract、Planner、Server/Browser Runtime、缓存证据、Resolved SQL、CLI Context 和 HTML Export 使用同一映射。
- [x] Query Parameter 的 `date`/`date_range` 支持基于 Workspace IANA 时区的严格相对默认值；Run 创建前解析为具体 ISO 日期并固化，Compute/Selection 不接受相对默认值。
- [x] Select 候选域用严格的 `options.mode=static|infer` 区分封闭枚举与 Source 推导；`infer` 禁止值列表 `default`，多选初始状态由 `all_available`/`explicit` 意图驱动。
- [x] `selection_inputs` 是 Runtime 数据边界而非普通参数；三种 Interactive Runtime 都先对字段契约匹配的表输入应用 include Selection，再进入 Compute 逻辑。
- [x] Source/Dataset Transform 与 Interactive Transform 使用两个 DAG、显式 Named Output、Schema Contract、provenance 和分支级并发。
- [x] 独立分支完成后立即发布；局部失败、超时或取消不会等待或覆盖无关分支。
- [x] `server-python`、`browser-python`、`browser-js` 共用输入、输出、错误、缓存、generation 和 dispose 契约。
- [x] 同一 tab 可恢复状态；不同 tab、Dashboard、用户、Run 和 Interaction generation 相互隔离。
- [x] Query Run Artifact 统一保存在 Workspace `.dataviz/`；可达 Server Interactive 输入在计划阶段显式分类，按 tab + Dashboard + Run + canonical Output 复用且绝不重查 Source。
- [x] SQL 默认 120 秒超时并立即额外重试一次；Dashboard 可覆盖 timeout/retry。
- [x] `dataviz/dependency-contract/v4` 成为 Query、Interactive、Control、Output 与 View 关系的唯一编译结果；Planner、Loader、Server、Browser、Export、CLI 和 AI context 不再各自推导 DAG。
- [x] 每个不可变 Dashboard load snapshot 以并发安全方式只编译并缓存一个 Dependency Contract；热更新创建新快照，并行首访也只返回同一个对象。
- [x] Query Parameter 契约给出直接消费者及最终受影响 Query 节点、Interactive 分支、option Control、内容字段和 View；Query 节点同时给出下游 View/Control。
- [x] Dependency Contract 以“可执行才存在”为不变量：环、未知 Output、browser → server-python 非法依赖和越界 Control consumer 在编译期拒绝；Loader 仅对无效图做 recovery diagnostics。
- [x] Query/Interactive 节点只读取显式声明的 Query/Selection/Compute 参数；Browser Transform/View 注册会核对 data inputs、Control inputs、Query Parameter inputs 与 Output names，注册 payload 只作 drift assertion，调度与 View 取数仍由契约拥有。
- [x] Control 通过 `depends_on` 只声明直接 Selection 父节点；Dependency Compiler 校验作用域、未知引用、父节点类型和环，生成 canonical 直接边、传递祖先/后代与 `control_order`。Browser 按同一拓扑原子协调候选域，支持 Dashboard→Section→View 和同 View 多级链，不再按 DOM 层级猜测级联。
- [x] `dataviz dependencies WORKSPACE DASHBOARD [--format json]` 为人和 AI 输出同一份可审查依赖图；HTML manifest 同时保存完整契约作为运行证据。

### Runtime 与 HTML Export

- [x] Server 与 HTML 共用 Renderer、Control、Overlay 和内容绑定实现。
- [x] Renderer 作者接口保持 `validate/mount/update/dispose`；平台统一验证 `mount/update/empty/restore/interaction/resize/dispose/export`，并记录 mount/update/empty/restore/interaction/resize/dispose/failure 指标。
- [x] View 具有 ready/loading/stale/empty/error/cancelled/unavailable 终态；取消或失败的 Run 可重新打开检查，不再因缺失 Output 返回 500。
- [x] View 空 descriptor 进入 `empty`，不再永久停在 rendering；Arrow Table 的 Metric 聚合不再显示 `[object Object]`。
- [x] 浏览器聚合改为线性 reducer，150K 行上的 min/max/mean/sum 不再使用会触发 JavaScript 参数上限的 spread。
- [x] HTML Export 明确 `interactive | snapshot | unavailable`；server-python 不伪装成离线交互。
- [x] browser-python 支持 Pyodide CDN 与 `HTML + assets + manifest` bundle；未使用 Pyodide 时不携带相关 Runtime。

### 模板、验证与 AI 入口

- [x] Component Registry v4 提供物理 Package、机器可读 manifest、Story、测试声明、语义 DOM 和 CSS token；`components --check` 检查包结构，行为由 pytest/E2E 实际执行。
- [x] 20 个 Component Package 全部为 package-owned；`data.pipeline`、`view.declarative`、`section.declarative`、`presentation.shell` 已迁出 Runtime bridge，删除 `declarative-runtime.js` 和重复实现。
- [x] 13 个独立 `control.*` Data Entry Package 对齐 Ant Design 的 Input、InputNumber、AutoComplete、Checkbox、Switch、Radio.Group、Select、Checkbox.Group、Cascader、TreeSelect、DatePicker、RangePicker 与 Slider；Query/Selection/Compute 共用 Registry 和 Renderer，单选不生成批量 All/Invert，多选批量操作受 required/clearable/max_selected 约束，RangePicker 使用单触发器范围日历。optional Single Select 的 Clear 仍是下面 Selection P0 的明确缺口。
- [x] Query 与 Dashboard/Section/View Controls 使用 `control-panel.adaptive`：同一面板按 DATA/LOGIC 分组、视口内滚动；Query 默认最多四个可读轨道并响应式降列，`columns` 表达最大列数，控件可显式 `span: 2` 但不会按组件类型自动变宽。Presentation 覆盖排版时不分叉状态逻辑。
- [x] Server Header 将 `Run query` 与 Query Parameters 合并为 split control；参数区默认展开、参与文档流并按 tab/Dashboard 记忆，只有箭头可开合，外部点击与 `Esc` 仅关闭临时 Controls/诊断浮层。
- [x] Gallery 提供 Control、View、Section 的七状态矩阵，以及实际包含 10、100、1,000 个原生选项的 Select Story；1,000 选项搜索覆盖全量且增强 DOM 有界。
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
- [x] `0.3.2` 增加 Workspace 文件监听、debounced revision、SSE 通知和 `canvas / analysis / query` 影响分类；Presentation 自动重载，Interactive 基于现有 Base Output 重算，Query Contract 变化只进入 Outdated 并要求显式查询。
- [x] 热更新保留 tab 的 Run、Control 与 Canvas 滚动位置；无效中间写入不替换当前 iframe，Header 提供诊断和显式 Reload。分类只跟踪实际声明/引用资产；保存 Source 后立即 Query 会先同步 revision。页面重开及查询运行途中发生定义变化时，也会重新核验 Query Contract，旧快照不能被误标为当前结果。
- [x] `0.4.0` 将 Data Entry 升级为 Registry v4：值语义、Control scope 与 UI component 三轴解耦；13 个 `control.*` Package 逐项对齐 Ant Design 组件边界，删除 `selector.*`、`segmented`、`date-range` 及 Presentation `selectors/template` 旧接口，不提供兼容 alias。
- [x] Query Parameter、Selection 与 Compute 复用同一 Control Renderer；Gallery 与浏览器契约覆盖新文本、建议、数值、布尔、日期、范围、平面/层级单多选和 Slider 的真实水合、输入、键盘、浮层、状态与虚拟列表行为。

## 下一步优先级

### P0：Selection、Linked Views 与最终配置有效性

这一阶段解决“配置合法，但最终效果并非作者预期”的核心缺口。它是下一次破坏式发行的前置工作；项目尚未进入生产，不为当前实验性 Presentation 布局字段保留兼容 alias、迁移分支或双协议 Renderer。

P0 不是以“底层支持了更多边”为完成，而以作者复杂度没有增加为门禁：普通看板不写 JS；跨图单选联动只写一条 binding；默认值无需重复声明；当前 `validate/dependencies` 与 Layout Contract 能解释已落地行为，后续 `inspect-layout` 将提供专用 CLI；高级逃生口不能绕过 canonical state。任一实现若要求作者维护第二份筛选值、直接连接两个 View 或理解事务细节，均不验收。

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
- [x] 示例、Gallery、Scaffold、内置文档和测试夹具已迁移；Dashboard v7 / Presentation v2 删除旧 Presentation 结构字段且无兼容 alias。

#### D. Semantic Validation 与静态布局检查

- [x] 在最终 Dashboard + Presentation + Component/Renderer manifest + Layout/Dependency Contract 上运行一次 Semantic Validation，不维护第二套图。
- [x] 增加稳定 `error / warning / advice` 三级诊断；`--strict` 只因 error/warning 失败，主观 advice 不阻塞发布。
- [x] 检查确定性冲突/no-op：模板 cardinality、超出 columns、无效 span、未被使用的 View、没有任何 consumer 的 Control、Renderer 不支持的属性和被覆盖的配置。
- [x] 对 band 中大型明细、可疑 `min_height`、Browser Transform 使用 apply 等启发式问题只给 advice，不假装静态工具了解数据规模或审美。
- [x] 实现 `dataviz inspect-layout WORKSPACE DASHBOARD [--format json]`，输出最终行列、span、来源、冲突和 custom 边界；为 CLI 输出建立稳定 Schema 和 Contract tests。

#### E. 可见的当前分析状态

- [x] 定义 `dataviz/state-snapshot/v1`，统一 committed Query Parameter、applied Selection、committed/draft Compute、stale 和作用域信息。
- [x] Dashboard Header 自动摘要 Query + Dashboard Controls；Section/View 标题附近摘要本作用域 Controls；长多选显示数量并可展开。
- [x] 明确区分“产生当前结果的已提交值”和“待应用草稿”，避免标题、摘要和报告证据提前使用 draft。
- [x] Server 与导出 HTML 共用同一摘要组件、formatter、事件和状态快照；允许作者调整 label/顺序/隐藏项，不要求手写 JS。

#### F. Runtime/CLI 默认体验

- [x] 将默认 trigger 改为 Runtime-aware：browser-js/browser-python 默认 auto，server-python 默认 apply；保留显式 auto/apply/manual、debounce、取消和 stale 语义。
- [x] 为 Runtime-aware trigger 补齐 Schema、Dependency Contract、Server/HTML、CLI docs、Scaffold 和三浏览器回归；静态工具不猜测计算成本。
- [x] 将 `query/output/compute --format json` 默认输出收敛为稳定 summary；增加 `--detail debug|full`（或等价显式选项）按需返回 SQL、bindings、Artifact、Node、provenance 和完整 diagnostics。
- [x] 精简模式保留稳定错误 code、必要失败上下文和下一步建议，并用真实 AI context 快照测试防止输出再次膨胀。

#### G. Chart Service 与真实浏览器视觉检查

- [x] 从内置 View Adapter 抽取 `context.charts.plotly` / `context.charts.echarts`，统一 Theme、responsive、scrollZoom、resize、update、dispose、错误状态与 Export。
- [x] 让 Scaffold、Gallery 和内置 Custom Renderer 默认使用 Chart Service；保留直接底层调用作为显式逃生口，并通过 Renderer manifest 声明可验证能力。
- [x] 实现 `dataviz visual-check`：在固定 viewport 的真实浏览器中检查横向溢出、重叠、零尺寸、弹层裁切、永久 Loading、Perspective 容器高度和 Console error。
- [x] visual-check 输出 Screenshot、机器可读 geometry report、稳定诊断 code 和复现参数，并覆盖 Server 与导出 HTML、Chromium/Firefox/WebKit 以及窄视口。
- [x] 明确 visual-check 不判断配色、业务图表选择或主观美感；这些继续由视觉模型/人工审阅和 Gallery 负责。

完成顺序固定为：Selection State Contract → View Event/Control transaction → Layout Contract → Semantic Validation → inspect-layout → State Snapshot/摘要 → Runtime/CLI 默认体验 → Chart Service → visual-check。Linked Views 必须建立在共享 Selection resolver 上；后续步骤不得先复制一套临时 Selection、事件、布局或状态推导。

排序原因是：Selection resolver 决定“当前到底选了什么”；Linked Views 只是增加同一状态的 writer；Layout/Semantic Validation 决定作者写的结构是否真的生效；State Snapshot 让用户看见当前上下文；CLI、Chart Service 与浏览器视觉检查最后再压缩试错成本。这样每一步都建立在前一份唯一契约上，而不是用 UI 补丁掩盖状态问题。

### P1：验证 AI 开发效率

评测工具已经完成，但真实成对试验按产品决定暂缓；这不阻塞 Runtime 工程工作，也不允许预设 Token 节省结论。

- [ ] 使用相同模型、客户端、权限和时间预算，对五类固定任务执行多次 Dataviz / standalone HTML 随机顺序成对试验。
- [ ] 发布原始 JSONL、环境说明、逐项验收证据、真实 input/output Token、首次成功率、修正轮次和耗时。
- [ ] 根据真实 friction 压缩 focused context、CLI docs 和 Scaffold；不预设固定 Token 上限或节省比例。

评测协议见 [AI Authoring 成对评测](docs/authoring-evaluation.md)。

### P2：规模与性能证据

- [x] Arrow 传输记录行数、字节和耗时；Renderer 记录 mount/update/empty/failure/耗时。
- [x] `benchmark --browser-runtime` 等待传输、Interactive Transform、Repeat reconciliation 和已挂载 View 进入稳定状态，并分别记录 Query、报告生成和页面就绪时间。
- [x] 150K 行真实浏览器回归覆盖声明式 Metric、browser-js Worker 与 Custom Canvas 聚合。
- [x] 固定并运行 10K、100K、1M 行 Query → Arrow → Interactive → Renderer 基准，记录 CLI 峰值 RSS、浏览器进程树 RSS、页面耗时和三轮 dispose 回落；原始结果见 `benchmarks/results/`。
- [x] 依据 1M 证据把 Worker/Data API 的 groupBy 改为单遍流式聚合：页面就绪中位数约降低 23%，浏览器峰值增量约降低 20%。当前不实现通用服务端分页或 Record Batch DSL；原始明细 View 另行基准触发。

### P2：浏览器可靠性

- [x] Chromium 覆盖独立分支渐进发布、失败隔离、取消后终态、空 View、大数据 Arrow 和局部重绘。
- [x] 当前完整 E2E 契约套件在 Chromium、Firefox、WebKit 通过，覆盖渐进 Query/Interactive 分支、Selection 级联、局部更新、Perspective 与 HTML Export。
- [x] Chromium、Firefox、WebKit 均通过 390×520 Query Header 内联面板、显式开合、单列响应式、内部滚动、Select 键盘/ARIA，以及 Perspective 三轮 dispose/reload/wheel 恢复矩阵。
- [x] Control、View、Section 七状态矩阵和 Select 10/100/1,000 真实选项 Story 已进入 Gallery 与 Chromium 契约测试。

### P2：内部归属与可维护性

这些工作不改变当前 DSL，但会降低下一次替换前端框架或拆分 Runtime 的迁移成本。

- [x] `view.declarative`、`section.declarative`、`data.pipeline` 和 `presentation.shell` 已迁入 owner Package；20 个 Package 均为 package-owned，Runtime 内没有同功能副本。
- [ ] 按 Runtime Manifest、Output Store、Interactive Scheduler、Selection Binding、Renderer Lifecycle 拆分大型 `canvas-runtime.js`，并通过构建步骤输出单一浏览器资产。
- [ ] 按 parse/load、cross-file contract、asset validation、catalog/navigation 拆分大型 `workspace/loader.py`；稳定错误 code 和 CLI 输出不得随物理拆分漂移。

### 开源发布

- [x] 完成 `0.3.0` 本地发行门禁：wheel、sdist、pip ZIP 构建，并分别在干净 Python 3.12 环境完成 `version → schemas → components → init → validate → report` 冒烟。
- [x] 完成 `0.3.1` 本地发行门禁：三种归档构建、内容审计，并分别在干净 Python 3.12 环境完成安装与 CLI/报告冒烟。
- [x] 完成 `0.3.2` 本地发行门禁：全量 Python 与 Chromium Runtime 回归、三种归档内容审计，并分别在干净 Python 3.12 环境完成安装与 `version → schemas → components → init → validate → report` 冒烟。
- [x] 完成 `0.4.0` 发行门禁：全量 Python/浏览器回归、wheel/sdist/pip ZIP 构建、内容审计与干净环境安装冒烟。
- [x] 完成 `0.5.1` 依赖架构发行门禁：单一 Dependency Contract 残余审计、完整 Python 与 Chromium/Firefox/WebKit Runtime 回归、全部示例 Workspace strict validate，并分别从 wheel、sdist、pip ZIP 在干净 Python 3.12 环境完成 `install → version → components → validate → dependencies → report`。
- [x] 完成 `0.5.2` Overlay 修复发行门禁：完整 Python 契约套件、Chromium/Firefox/WebKit 桌面与窄屏浮层回归、三种归档内容审计，并分别在干净 Python 3.12 环境完成 `install → version → components → validate → dependencies → report`；最终 wheel 另行通过真实 Server/Chromium 几何冒烟。
- [x] 完成 `0.5.3` Plotly 页面滚动修复发行门禁：默认 `scrollZoom=false` 与显式 opt-in 均通过 Chromium/Firefox/WebKit 真实滚轮回归；306 项 Python 契约测试、Component Package 检查、Feature Showcase strict validate，以及 wheel/sdist/pip ZIP 的干净安装与报告导出全部通过。
- [x] 完成 `0.5.4` Custom Renderer Plotly 滚轮契约发行门禁：AI 文档、组件契约与 Scaffold 明确自定义 `newPlot`/`react` 默认使用 `scrollZoom=false`；336 项完整测试、四个代表性 Workspace strict validate，以及 wheel/sdist/pip ZIP 的干净安装与离线报告导出全部通过。
- [x] 完成 `0.6.0` 断代发行门禁：312 项 Python 契约测试、Chromium/Firefox/WebKit 各 25 项回归、8 个 Workspace/11 个 Dashboard 严格 validate、wheel/sdist/pip ZIP 内容审计，以及三套独立 Python 3.12 干净安装的完整 CLI/报告冒烟全部通过。
- [x] 完成 `0.6.1` 布局修复发行门禁：Query Parameter 最多四轨的响应式布局与显式 `span` 通过 312 项 Python 契约测试、Chromium/Firefox/WebKit 各 26 项回归、全部示例 Workspace 严格校验，以及 wheel/sdist/pip ZIP 的内容审计和独立 Python 3.12 安装冒烟。
- [x] 完成 `0.7.0` P0 A–G 发行门禁：335 项 Python 契约测试、Chromium 32 项及 Firefox/WebKit 各 31 项真实浏览器回归、5 个代表性 Workspace 严格校验、20 个 Component Package 检查，以及 wheel/sdist/pip ZIP 独立安装与 Python 3.11–3.14 兼容冒烟。
- [x] 完成 `0.8.0` Renderer 生命周期发行门禁：统一 Plotly/ECharts/Perspective 的八阶段 Server/HTML 矩阵；373 项当前测试契约、完整 Chromium 与 Firefox/WebKit 核心 Perspective 生命周期、全部示例 Workspace strict validate、三种归档审计及独立 Python 3.12 安装冒烟通过。Perspective Worker/Table/Viewer 归属单个 Renderer 实例，异步阶段超时会进入 Table Fallback，不会永久 Loading。
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

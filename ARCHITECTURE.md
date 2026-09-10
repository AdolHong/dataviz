# Dataviz 当前架构与设计理由

本文解释当前职责、数据流与取舍，不保存历史迁移步骤。使用入口见 [README](README.md)，视觉规范见 [DESIGN](DESIGN.md)，代码定位见 [实现索引](docs/product-architecture.md)，未完成工作见 [plan](plan.md)，发行历史见 [CHANGELOG](CHANGELOG.md)。

字段与协议版本以 [protocols.py](src/dataviz/protocols.py)、严格模型及 `dataviz schemas/version/components` 为准。这里不维护第二张版本清单：包版本、组件版本、持久化协议与内部通信有不同的变化原因。

## 文件组织与运行事实

Server Action 是独立的显式执行边界，完整契约与验收见
[Server Action 设计](docs/server-actions.md)。其职责是显式执行受信任 Python
副作用，而不是扩充 Source/Transform 的自动执行语义。资源使用外部 Adapter
绑定；业务 CRUD 留在 Python；Source 失效与 View 重绘明确区分。Server API、
Renderer 与 CLI 共用一套回执和刷新调度；超时不自动重放写入。刷新只替换受影响
的分支，以已应用参数创建新 Query Run，不改写旧 Run 或已封存 Result。
当前工作树已实现并验证，发行状态以 plan/CHANGELOG 为准。

Dataviz 是 workspace-first 的分析看板工具。Dashboard 是可复制、审查和 Git 管理的普通文件；CLI 面向作者与自动化，Server 提供交互工作台，HTML 提供可搬运报告。

Workspace 是内部执行边界，不必成为简单看板的作者负担。独立 YAML 入口将内嵌代码和声明文件降为普通 Workspace 快照，继续使用同一套校验、DAG、Result 与 Renderer，不另建轻量执行器。`--auth` 显式引用外部 Adapter 文件/目录/Workspace，仅加载认证环境，不共享取数逻辑；凭据不复制，私有元数据仅记录路径。源内容变化产生新快照，旧 Result 保留在原路径。首版单看板 serve 修改后重启，不提供生成文件的页面编辑写回。语法和限制见 `docs standalone`。

```text
Catalog → canonical Target → Execution Run → immutable Result → Evidence
Dashboard files → validate/compile → Server 或 portable HTML
```

Catalog 只发现、不执行查询；Target 使用 Dashboard、Source、Dataset、Interactive Output 或 View 的稳定物理引用。`result show/inspect/export` 消费已有事实，不重新查数。

Execution Run 与 Result 不合并：前者可以渐进更新、失败或取消，后者是封存后的事实。显式 CLI Run 通过 preflight 并启动后，终态可以封存 ready/partial/failed/cancelled Result；启动前错误不创建 Result。普通 Server 交互不自动创建公开 Result，显式分享、导出等发布动作才封存相应事实。

## 查询、交互与显示的边界

### 多 Page 的目标边界（实施中）

Dashboard 是代码、资源逻辑引用与统一发布的边界；Page 是分析入口、查询参数、
执行依赖闭包和交互状态的边界。同一 Dashboard 的 Page 可调用相同本地 Python/JS，
不引入跨 Dashboard 软链接或隐式执行依赖。公共代码修改影响本 Dashboard 的所有
消费者，这属于明确的共同维护范围，应一起校验与发布。

Page 独立持有 Query draft、applied 参数证据、Run、Control checkpoint 和滚动位置。
同名参数不共享值，也不自动跨页继承；第一版不提供共享参数、跨页 Control 或嵌套 Page。
Page 的查询范围从其 View、候选域与交互入口推导，不能要求作者重复维护 Source 白名单，
也不能通过隐藏 Section 模拟按页执行。没有消费者的其他 Page 数据不查询、不下发浏览器。

执行仍使用现有 Compiler/Executor/Result；Page 身份必须贯穿 Run、缓存、候选域、
Action 与交互请求、诊断和导出。切页不发起 Query；返回恢复仍有效的状态。后台页完成
只更新自身状态，不能覆盖活动页。Action 写入仍独立于页面同步；未提交的动作不能因
切页而被改投另一页。受共享标注失效影响的其他页标为过期，不自动执行昂贵查询。

共享数据的新旧判断复用 Action Journal 的 Source mutation epoch：Source 在执行或
缓存命中前捕获版本，同一版本写入缓存键和节点诊断；Run 本身不因后续写入而改变。
Server 在现有事件连接中发送已声明 Source 的当前版本，Shell 与实际显示的 Run 比较，
所以保存成功但页面同步失败时，仍能识别旧画面。只沿 Dashboard 内的同一 Source ID
传播，不从数据库文件路径推断依赖，也不把数据过期误报为 SQL/Python 定义变化。
该通知不触发查询；断线重连与会话恢复重新取得版本证据，不依赖某条瞬时通知必达。

Sidebar 继续组织 Dashboard。多页导航位于 Dashboard 标题与当前页参数之间；Run、
参数状态与 Controls 明确属于当前页。URL 带 Page，支持刷新、深链与前进后退。
首次进入本页展开参数，成功后折叠；草稿不能冒充本页已有结果的已应用参数。
参数编辑器也按所选 Page 读写，保存时校验整个 Dashboard 文件 revision；
同名字段不会写入其他页，页面导航不能改变已经打开的编辑请求的目标。
只有一个入口时不显示多余导航，现有单页 Dashboard 保持行为。

Bundle 封存整个 Dashboard 的定义和代码；运行结果与报告明确记录所选 Page。
查看/导出 Page 结果不隐式运行其他页。多页静态报告只能消费已经封存的各页事实，
不能承诺离线查询；未实现的组合导出必须明确拒绝，不能静默导出错误页面。
本节是本次实施的约束，不表示所有入口已经完成；验收状态见 plan。

#### 渐进式作者入口

Page 是可选的高级组织能力，不是每个看板必填的包装层。Quickstart 继续以一个 YAML、
一个 Source 和一个 View 为最短路径，可内嵌少量 SQL/Python/JS；外部连接仍显式通过
Auth/Adapter 绑定。没有 pages 时，顶层 query_parameters/controls/views/sections 就是
唯一分析入口；作者不需要编写默认 Page，也不需要先理解 Workspace 目录或多页执行身份。
内部可统一投影，但不能把运行实现的层次变成用户入门负担。

文档按任务逐级展开：单文件最小看板 → 参数与交互 → 多 View/Section → 独立分析 Page。
Quickstart 不预先堆入 pages、空 sections、空 controls 或高级部署配置。需要第二条分析
路径时，再介绍把现有参数与展示移入一个 Page、增加另一个独立 Page；不改变原有取数
和业务代码的职责。CLI 搜索应能按“第二个分析页面/不同参数”找到多页说明，而最短创建
入口继续返回可直接运行的简单示例。静态校验仍使用同一套契约，不另建宽松的 quick DSL。

CLI 同样按需展开：已知看板直接 run，不强制先检索 Catalog；只在未知目标时使用发现入口。
`--page` 可省略：无 pages 运行顶层，单 Page 自动选择，多 Page 默认第一条声明的 Page，
不会隐式运行全部页。结果记录实际 page_id；需要稳定固定某个入口的自动化显式指定它。
查看或导出已有 Result 沿用封存的 Page，不再次传参选择。这个默认减少入门负担，
同时保留可追溯的执行身份；不引入 default_page 等额外 DSL。

```text
Query Parameter → Adapter → Source → Dataset Transform（可选）
                                         ↓
                                  Base Named Output
                                         ↓
Control → consumer binding → View 或 Interactive Transform
                                         ↓
                                  Derived Named Output → View
```

- Adapter 是 Workspace 的连接与凭证边界；Source 是只读分析 DAG 的外部数据入口。
- Dataset Transform 在查询阶段处理数据；Base Output 在一次 Query Run 中保持不变。
- Control 持有查询后的状态，consumer 决定它是过滤条件还是计算参数。
- Interactive Transform 在既有输入上计算，不隐式访问 Adapter 或重查 Source。
- View 负责表达，Presentation 负责视觉；业务计算继续使用 SQL/Python/JavaScript。

最简单的看板只有 `Source/main → View`。这些层可以省略，但不能把查询事务、局部交互与渲染生命周期合并成一个万能状态对象。

### 参数状态为什么不同

Query Parameter 使用 `default`；候选多选保存紧凑的 `all/include/exclude/none` 和有限 operands。RUN 消费 committed state；草稿、搜索词和分页游标不代表 Result 使用的参数。`query_filters` 对 all/include/exclude 生成参数化 TRUE/IN/NOT IN；none 与空 multiple_input 由 consumer 的 `empty: passthrough|match_none` 决定 TRUE/FALSE，不产生 `IN ()`。

Control Select 使用 `initial`，候选多选状态为 `{value, revision, intent}`，intent 是 `all_available/explicit`。全选按已解析候选值过滤，不是无条件放行整个 Output；compact 空 operands 的静态候选仍受 choices 白名单约束，非静态 compact 全选保持通过。显式空选按 consumer empty policy 解释。

两者共享 typed value 校验，不共享提交生命周期或集合状态协议。`0`、`false`、空字符串与空列表不能用一个 truthiness 判断替代各自契约。

## 一份事实，一套推导

每次加载或热更新产生新的 `LoadedDashboard` 快照，分别惰性编译并缓存三份 Contract：

- Dependency：数据图、参数与 Control binding、writer、影响关系。
- Layout：Section/View 结构与布局。
- Parameter Domain：候选定义与 Lookup 消费关系。

三者有不同 consumer 和成本，不强迫进入总编译，也不新增包裹 owner。Contract 间依赖必须显式、单向；请求级 ExecutionPlan 由 Contract 与 RunRequest 派生，Target 和当前 state 不缓存进加载快照。

Compiler 校验引用、作用域、拓扑和输入输出。Planner、Canvas、CLI、Server 与诊断只消费或投影同一事实，不从 DOM 或字段名猜另一张图。失败编译不缓存 partial Contract；validate 的恢复性扫描只能补诊断，不能生成可执行的部分事实。

`run_analysis()` 是显式 Target 执行的应用边界，复用 resolver、Executor 和 ResultStore。CLI 负责参数与输出；普通 Server RunManager 仍拥有 session、渐进事件、取消及临时 Artifact 生命周期，不合并成万能 Runner。

## Control 的唯一状态权威

候选级联的父字段优先采用该消费 View 已声明的 filter 映射，否则采用父 Control 的显式字段。
无需为选项推导给所有 View 补一份父过滤；但平台也不猜测业务字段对应关系。
关系字段缺失、上游失败、尚未加载和合法空域必须区分，前者保留原选择并提供诊断。

Dashboard、Section、View 决定逻辑作用域；Canvas 托管的 ControlRuntime 是 canonical state 的唯一修改者。组件和 View gesture 都只是 typed action producer。

一个 Control 可以有多个合法 View writer；一个手势可以原子写入多个目标。Compiler 校验 scope、字段与类型，Runtime 校验 action identity、source View 和 generation；compound action 失败不部分提交。程序化重绘只更新选中投影，不回发用户 action。

`depends_on` 只声明直接父节点；Runtime 按拓扑协调候选。all_available 跟随新候选，explicit 保留有效交集，原非空选择完全失效才恢复 initial，主动空选不被自动恢复。

Server Shell 拥有 Query draft/committed、导航及已确认 checkpoint，Header Control 只是 Canvas 状态投影；Shell 不增加 Control revision，不合并第二份权威状态。Server/portable 使用同一 reducer。Host channel 是同包 lockstep 通信，校验 frame identity；初始化没有 checkpoint 或超时也必须继续。

current state 与 applied evidence 不同：consumer 在 generation 开始时捕获输入，只有该 generation 成功后才推进 applied revision/state 与 writer provenance。过期结果、失败与取消不能覆盖新状态或冒充已应用结果。

## 候选物化与共享文件

SQL Parameter Domain 由所属 Dashboard 持有，先形成 immutable materialization，再由 Server-local Lookup 做搜索、父级过滤和 cursor 分页。交互不重跑远端 SQL，不把完整候选池交给浏览器。

物化身份包含 Dashboard 定义/代码、实际 Adapter identity 与 visibility scope。同 Dashboard 的用户/tab 只有在相同可见范围下才能复用 generation，不同 Dashboard 隔离。刷新期与硬过期由 `refresh_after_seconds`、`expire_after_seconds` 区分；lease、原子发布、reader pin 与 prune 协调构建和读取。cursor 绑定 generation，迟到成功或失败都不能覆盖新搜索。

Parameter Domain 是候选发现，不是业务 Output 或 Query Parameter 合法值白名单。CLI 已知值可直接提交，不因参数校验隐式物化。HTML/Result 保存参数状态，不嵌入候选 SQL、Parquet、搜索词或候选页。

Workspace 只共享稳定静态 Asset，不共享 Source、Transform、View、Parameter Domain 或业务 SQL。少量 Dashboard-local 复制换取独立演进：优化一个看板，不应意外改变另一个看板。Catalog 发现既有 Output，不构成隐式跨 Dashboard 执行依赖。

Asset 注册与 Browser allowlist 分开，File Source 的 `asset:<id>` 不自动授权 Browser。Server 与 portable 通过同一 `context.assets` API 提供内容，AI context 只投影元数据。

Bundle 是独立快照，不是 import/merge/sync：只接受新目录或空目录，在 staging 复制完整 Dashboard 和实际引用 Asset，校验 hash 与来源稳定性后一次发布。不覆盖已有 Workspace，不带凭据、无关文件或物化缓存，因此旧副本不会反向覆盖新 SQL 或共享文件。

## 增量运行与 Renderer 输入

输出发布是一个原子状态动作：值、kind、schema 与 signature 一起更新，输出消失时一起清理。
错误恢复和元信息变化也需要通知消费者，不能仅比较数据值后跳过；否则有值的表仍可能被判断为不可过滤。
Canvas 重载从服务端已接受的 generation 水位接续，而不是关闭旧请求检查；水位按 session/Dashboard/Run/Transform 隔离。

Interactive Transform 的执行单位是整个函数，下游更新单位是实际变化的 Named Output。Runtime 比较 signature，未变化的 Output 不传播重绘。browser-js 在 Worker 中执行，独立分支可并发，过期 generation 不提交。完整输出使用有界会话缓存，key 包含代码、输入、Runtime 与有语义的参数状态，审计 revision 不单独造成 cache miss。

已有画面在重算时保留并显示 updating；这只是视觉连续性，不代表新 generation 已应用。首次无内容才显示完整 loading。

Custom View 使用主 `input` 与额外 `inputs`，不用把 Geography 和 Store 拼成 row_kind 混合表。表格主输入的 `descriptor.inputs.main` 与 `descriptor.rows` 使用同一份处理后数据；额外 alias 只应用明确绑定给自己的筛选，未绑定输入保持原值，原始 Output 不修改。

Renderer 通过 mount/update/resize/dispose 管理资源。契约测试可以检查空 mount、hook failure、dispose 后遗留 DOM，不能证明任意第三方监听器或内存绝无泄漏。

Plotly 是统一图表接口，普通 Table 使用 TanStack，Perspective 用于现场多维探索。原生 Map 的 region/point layers 共用 viewport、Control writer 与生命周期；地理裁剪由 Transform 完成。Metric 的主值、unit 和 secondary 表达已计算数据，不承担业务公式。Plotly layout 只支持完整 `{{ parameters.<id> }}` token 读取 committed typed Query Parameter，不是通用模板执行器。

## Result、Evidence 与可复现性

Result 在 staging 校验 manifest/Artifact hash 后原子发布，已发布事实不回写；索引和访问统计可重建，不是业务事实来源。Report 依赖封存的 Presentation 与数据，后续查看不重跑 DAG。

File Source 直接复用原文件时，Result 保存读取收据、路径与 content hash；再次读取时源文件变化或缺失必须明确失败，不能读取新内容冒充旧结果。这种引用不保证文件变化后仍可永久复现。新计算产物由 Result 托管，沿用原生 Artifact 格式，避免不必要的复制与转码。

Dataset Transform 可通过 `run ... --from-result` 复用一个 Result 中兼容的直接输入，仍生成新 Result；不匹配时失败，不悄悄查询数据库。Interactive 输入复用不能绕过 Control/applied-state 重建。

Analysis producer 严格拒绝未知核心字段；reader 的 tolerant 行为是另一边界。保留字段参与相应 hash，不得覆盖已知字段含义。Evidence 引用 Result、lineage 与 applied evidence；Promote 产生可审阅的普通 Workspace 变更，不自动 apply 或 certified。

## 诊断、文档与作者体验

诊断区分执行前 explanation、执行中 telemetry 与执行后 immutable evidence。`inspect query` 返回 `executed: false`，不能把计划当成数据库执行事实。Result 提供真实 SQL、bindings、行数、错误与 provenance；作者面板提供会话内刷新原因、Lookup 阶段、输入规模和 Renderer 耗时。

No data 只解释可证明的阶段，例如上游零行或 Control 过滤后零行，不凭空断言业务事实不存在。Copy diagnosis 聚合已有证据，不创建另一份状态或审计存储。

文档按任务渐进展开：普通作者从 Source → View 开始，需要时再进入 Control、Transform 或 Renderer。`docs --search` 检索专题与任务正文，返回有界片段和可执行的 follow-up command；完整关键词匹配优先，部分匹配作为回退。它不是语义问答，不使用外部索引，也不取代 Schema 校验。

Server 人工编辑只调整受限默认配置、静态候选与同级顺序，不成为第二套数据逻辑或布局开发器。保存经过 revision 检查、Schema 校验与原子写入，不能覆盖并发编辑或静默改写当前提交状态；可编辑范围以接口校验为准。

Server 与 HTML 可以有不同外层操作，但 Dashboard 字体、控件、View 与状态语义共享实现。视觉细节由 DESIGN 维护，不在架构文档重复尺寸与颜色。

## 可靠性与演进准则

- 同一语义跨 Python、Canvas、Web Component 时共用 conformance expected；测试调用生产实现，不复制另一套解释器。
- Runtime source 与生成 bundle 必须一致。协议变化按 authoring、wire、持久化和组件边界判断，不因发包机械全部升版。
- 当前 Runtime 是 exact-current、同包 lockstep；没有 capability negotiation，不能用假设中的协商机制论证兼容性。
- 新抽象必须消除实际重复解释、确立所有权或支持已验证需求。函数和普通数据够用时，不新增 service、phase、DSL 或持久化对象。
- 单进程拥有 Workspace 运行协调，不承诺多个 Server 同写同一路径。可信本地代码执行不是多租户沙箱，session ID 不是身份认证。
- Arrow、聚合基准或 Lookup 的可扩展性不代表任意原始大表都可安全进入 Browser；分页与并行优化由测量触发。
- 浏览器测试验证行为与几何，不替代业务口径或审美判断；安装冒烟验证发行物，不等价于源码测试。验证范围与缺口按本次变更报告。

没有真实需求时，不增加输出级执行 DSL、GIS/指标表达式、共享业务代码层或另一套知识存储。待办只放在 plan，历史迁移只用于版本记录。

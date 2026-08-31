# Dataviz 设计

> 快速安装和当前可用命令见 [README](README.md)；后续工作见 [plan.md](plan.md)。安装版本真正接受的字段始终以 `dataviz schemas`、`dataviz docs` 和 `dataviz components` 为准。

本文记录已经落地并可由当前 Schema、CLI、Runtime 和测试证明的契约，以及明确标注的后续目标。当前严格契约是 `dataviz/dashboard/v11`、`dataviz/presentation/v2`、Source/Transform v3、`dataviz/dependency-contract/v7`、`dataviz/layout-contract/v1`、`dataviz/state-snapshot/v2`、`dataviz/runtime/v6` 与 Component Registry `5.6.0`。Input State、Control writer/consumer binding、current/applied revision、Layout/Semantic Contract、Chart/Table Service、Renderer 行为矩阵、`inspect layout` 与 visual-check 均已进入实现；当前代码只接受现行严格契约，不保留旧字段 alias、自动迁移或双协议 Runtime。

Dataviz 是一个 workspace-first、AI-friendly 的数据看板工具。看板是普通文件，能够被 Git 管理、复制和审查；Server 面向人提供交互页面，CLI 面向 AI 与自动化提供构建校验、Catalog 发现、Target 执行、不可变 Result 检查和 HTML 报告。

## CLI 与运行事实模型

当前 CLI 使用语义 Catalog、局部 DAG 执行和不可变 Result 这组稳定领域对象，不增加第二套执行引擎，也不暴露生成式短 alias 或并列执行入口：

```text
Catalog ──发现──> Target ──run──> Execution Run ──终态封存──> Result
                                                               │
                                                               └─> Evidence ──> Promote
```

公开用户只需理解 `catalog → run → result → evidence`。`Execution Run` 仍是 Runtime 内部对象，可以处于 running、partial、failed、cancelled 等状态并支持 Server 渐进更新；`Result` 是公开、不可变、可寻址的运行事实。二者不会为了表面上的 CLI 简洁而合并成同一个可变对象。

### Target Reference v1

Catalog 不再生成或接受 `src_...`、`base_...`、`drv_...`、`view_...` alias。所有发现、描述、执行、Result 和 Evidence 使用可读、稳定的物理引用：

```text
<dashboard-id>
<dashboard-id>::source:<source-id>
<dashboard-id>::source:<source-id>/<output-name>
<dashboard-id>::dataset:<transform-id>/<output-name>
<dashboard-id>::interactive:<transform-id>/<output-name>
<dashboard-id>::view:<view-id>
```

第一种是 Dashboard 的 CLI 简写；其余形式构成 `dataviz/target-reference/v1`。解析器只按 grammar 和 Workspace 当前定义解析，不猜测 hash alias、对象名或 Result ID。Catalog Entry、Result Manifest 与 Evidence 必须保存 canonical Target Reference；命令行输出提供可复制的物理引用。

### 公开命令边界

公开命令按稳定领域对象组织，不使用按角色或模糊行为划分的垃圾桶分组：

```text
Workspace       init, tree, docs, schemas, scaffold, version
Build/verify    validate, visual-check, inspect context|dependencies|layout
Execute/deliver run, report, serve, prune
Discover        catalog list|search|describe
Results         result list|show|inspect|export
Knowledge       evidence create|promote
Extensions      components list|show|check|gallery, renderer test,
                frontend-adapters, benchmark runtime
```

`tree` 只回答 Workspace 的物理工程结构，默认文本必须是真正的树；`catalog` 只读，只回答可分析的数据能力，不能执行。`run WORKSPACE TARGET` 是唯一公开数据执行入口，Target 可以是 Dashboard、Source Output、Dataset Output、Interactive Output 或 View。

`validate` 保持无浏览器、快速、静态的 core 契约；`visual-check` 继续作为需要 Playwright/浏览器的独立重型检查。编译结构统一由只读的 `inspect context/dependencies/layout` 提供；组件陈列室属于 `components gallery`，自定义 Renderer 验证属于 `renderer test`，生命周期清理统一由默认只预览的 `prune` 承担。

### Result 终态与下游消费

显式 CLI `run` 一旦通过 preflight 并真正启动，进入终态后必须封存 Result。Result 状态允许 `ready | partial | failed | cancelled`；失败 Result 可以没有 Output，但仍保存 Target、参数、DAG、错误、日志、时序、定义 hash 与 provenance。未知 Target、参数解析失败、Schema 无效等启动前错误不创建 Result。

Server 的每次点击、Control 更新和后台重算仍只属于 Execution Run，不自动制造公开 Result；用户显式 Share、Export 或 Save 时才封存。`result show/inspect/export` 永远读取既有 Result，不重新执行；`result list` 提供运行历史。全局 `prune` 负责 Result、Execution Artifact 和缓存的生命周期，Result 域不再增加第二个清理入口。

Report、Share、Evidence 等下游能力优先消费不可变 Result，避免重复昂贵查询。Result 记录 `renderability`（dashboard、view 或 data-only）和定义证据；只有一并封存完整 Presentation 快照的 Dashboard/View Result 才能生成完整报告。直接从 Dashboard 生成报告保留为 convenience flow：它只执行一次，在同一发布事务中封存数据 Artifact、Presentation 快照和 Result；此后的 Report 消费 Result 快照，不重新运行 DAG。

### 渐进式文档与内部评测隔离

正式文档只暴露两个分支：

```text
构建与验证：init → scaffold → validate → run → serve
探索与执行：catalog search → catalog describe → run → result show
```

`report/visual-check/inspect`、`result inspect/export`、`evidence` 和扩展开发能力按任务继续披露。AI Authoring 成对评测、Token/会话采集和 context benchmark 属于仓库维护工具，不属于 Dataviz 产品：它们迁移到独立 `tools/authoring-evaluation/` 项目，使用 `dataviz-authoring-eval`，不得进入正式 `dataviz --help`、README 用户路径、wheel、sdist 或 pip ZIP。正式包只保留 Dashboard authoring 所需的 context/scaffold/docs 能力和 runtime benchmark。

内置 `dataviz docs` 将这两个主分支实现为机器可读路径，并另设“运行维护与扩展”参考区。探索路径按需披露 Catalog、Target Reference、Result、Overlay 和 Evidence/Promote；默认入口不要求简单看板作者读取 Analysis Plane，也不要求只想取数的 AI 阅读完整 Runtime。

项目长期只用两个维度衡量价值：

1. 模板和组件是否可靠、易懂、可扩展，能减少用户困惑与 AI 试错。
2. AI 开发新看板所需的输入上下文、输出代码和修正轮次是否更少。

第二项必须通过真实任务测量，不预设没有证据的 Token 目标。第一优先级始终是先把工具做得好用。

## 设计原则：复杂度必须下沉

Dataviz 可以支持复杂数据流，但不能要求普通作者理解 Runtime 内部实现。作者面对的稳定模型只有五件事：取数参数、数据节点、Controls、Views/Sections、布局；`presentation.yaml`、Transform 代码和 Custom Renderer 都是按需逃生口。Dependency Contract、拓扑排序、状态事务、revision、缓存和 Renderer 生命周期由 Compiler/Runtime 自动生成，不能变成 Dashboard 的手写负担。

| 作者想做的事 | 唯一默认路径 |
| --- | --- |
| 改变取数范围 | Query Parameter |
| 在已有数据中筛选样本 | scoped Control + consumer filter binding |
| 改变查询后的计算逻辑 | scoped Control + Interactive Transform value binding |
| 点击图/表联动其他 View | View event 写入一个既有 Control，consumer 决定如何使用 |
| 编排 Section/View | `dashboard.yaml` 的语义模板与 span |
| 调整颜色、容器和局部样式 | 可选 `presentation.yaml` |

普通路径必须满足“一个需求、一种写法、一个状态 owner”。平台不会为 View 联动再创建隐藏 filter，不允许 View 直接调用另一个 View，也不会要求作者手写事件总线。只有字段映射、触发策略或视觉行为确实偏离默认值时才展开高级配置。若一个常见看板必须写回调、复制状态、理解 canonical key 或阅读 Runtime 源码才能完成，应把它视为框架缺口，而不是作者责任。

### 作者文档也必须渐进披露

完整 Runtime 架构是平台实现契约，不是每个作者任务的必读前置。CLI 以 `dataviz/authoring-route/v1` 返回任务最小闭包，默认 `minimal` 只披露：

```text
Adapter → Source → View → Layout
```

只有需求包含 Query 后状态或计算时才加入 `Control → Interactive Transform → Named Output`；只有内置 View 无法表达视觉时才加入 Renderer Contract 与生命周期。`interactive` 和 `custom-renderer` 都继承 minimal，但互不强制继承，避免一个高级能力把另一套无关契约带入上下文。

`dataviz scaffold minimal|interactive|custom-renderer` 分别生成完整可运行 Workspace。Scaffold Catalog v2 为每项声明 route 与 `workspace|fragment` scope；任务文档显式声明 `requires`，回归检查这些引用必须属于当前路由闭包。每个 profile 独立通过 `validate → report → visual-check`，但这类确定性工程回归不等于 AI 效率证据；Token、首次成功率、轮次和耗时仍只接受真实成对试验。

### AI 开发与人工调参的边界

AI/代码仍然拥有 Dashboard 的结构和逻辑：ID、类型、作用域、依赖、Adapter、Source/Transform、View、Section、布局、Presentation 与自定义资产只能通过文件开发并接受 `validate`。Server 只提供一个受限的人工调参面，不发展成第二套可视化开发器：

- 可编辑 Query Parameter、Dashboard Control、Section Control 和 View Control 的 `default`；
- 可编辑 `options.mode: static` 的候选项及候选项顺序；
- 可调整同一作用域内参数/Control 的陈列顺序；
- `options.mode: infer` 的候选项和默认值只读，因为它们由数据契约决定；
- 不允许新增/删除参数，不允许修改 ID、type、kind、required、作用域、`depends_on`、输入绑定、布局或样式。

编辑器直接对当前 Dashboard 的 `dashboard.yaml` 做保留注释与格式的 round-trip 更新，不创建数据库或第二份配置。保存使用 revision 乐观锁、进程内写锁、完整 Dashboard Schema 校验和原子替换；若 AI 或其他编辑器在弹窗打开后修改了文件，本次保存必须冲突失败，不能覆盖新内容。编辑器改变的是下一次初始化使用的默认配置，不得悄悄改写当前 tab 已经提交的 Query Parameter 或 Control 状态。它只存在于 Server authoring surface，导出 HTML 永远是只读分析报告。

编辑入口复用现有操作对象，不向任何 Control Panel 添加常驻工具条：右键“查询”主按钮打开 Query Parameter 编辑，右键 Dashboard/Section/View Controls 触发器打开对应作用域编辑；左键仍只执行 Query 或开合 Controls。没有可编辑项时保留浏览器原生右键菜单。此入口属于熟练用户的低频 authoring 动作，不与高频分析操作争夺视觉注意力。

能力按下面顺序渐进开放，前一层始终可以独立工作：

```text
声明式默认模板
  → 模板参数与 Dashboard 布局
  → Presentation token / 局部样式
  → 单个 Custom Renderer
  → 完整自定义 Canvas
```

## 1. 核心执行模型

执行模型由两个阶段组成：查询阶段先确定基础数据，交互阶段只在基础数据之上计算。

```text
查询阶段

Query Parameter → Workspace Adapter → Source → Dataset Transform（可选，Server）
                                                   ↓
                                           Base Named Output

交互阶段

Control Component ──────────────→ scoped Control Input State（Dashboard / Section / View）
View user event ─────────────────┘               │
                                                 ├─ filter binding → 选择数据
                                                 └─ value binding  → 改变计算逻辑

Base Named Output + resolved Controls
             ├─→ View Renderer → Presentation
             └─→ Interactive Transform（可选）
                   ├─ server-python
                   └─ browser-js
                            ↓
                    Derived Named Output → View Renderer → Presentation
```

查询与计算部分是一张 DAG，不要求每层都出现；Control Component/View user event 是状态写入边，不是会自动继续触发自身的执行边。最简单的看板仍然只有：

```text
Source/main → View → 默认 Presentation
```

### 稳定职责

- **Adapter**：Workspace 本地的数据连接和凭证边界。
- **Source**：从 File、SQL 或可信 Python 入口读取外部数据。
- **Dataset Transform**：查询阶段在 Server 对 Source Output 做清洗、合并、特征加工和基础模型计算。
- **Base Named Output**：一次 Query Run 确定后保持不变的基础结果。
- **Control**：Query 后唯一的交互状态入口；Control Component 和目标 View 的用户选择只是同一 Input State 的不同 writer。作用域只定义可见范围，数据筛选或计算参数语义由 consumer binding 定义。
- **Interactive Transform**：不重新取数，只根据 Base Output 与显式 Control 输入产生交互结果。
- **Derived Named Output**：Interactive Transform 的标准命名结果。
- **View Renderer**：把 Base/Derived Output 渲染为图、表、指标、文本或自定义组件。
- **Dashboard Composition**：拥有 Section/View 顺序、结构模板、列数和 span；删除 Presentation 后仍能确定完整阅读结构。
- **Presentation**：按稳定 ID 调整主题、容器外观、组件外观、Renderer 视觉参数和局部样式，不拥有结构布局或分析语义。

“Dataset”不是额外的隐式对象。表格 Dataset 是一种 Named Output；所有节点必须通过显式 Output 引用连接，Runtime 不暗中猜测数据来源或执行隐藏聚合。

### 单一 Dependency Contract

每次 Workspace 载入或热更新都会创建新的不可变 Dashboard 快照；每个快照只编译一次版本化的 `dataviz/dependency-contract/v7`。同一快照内的执行、交互和渲染层共享同一个契约对象，不能重复编译或各自解释 DSL。它包含：

- Query 节点的输入 alias、上游节点、Named Output、拓扑顺序、下游 View/option Control，以及每个节点允许读取的 Query Parameter；
- 每个 Query Parameter 的直接消费者和最终受影响 Query 节点、Interactive 分支、option Control、内容字段与 View；
- Interactive Transform 的 Base/Derived 输入、Query/Control 输入 alias、Runtime、Named Output、直接/完整下游 View 和拓扑顺序；
- View 的有效输入、继承后的 Control、View writer binding，以及按拓扑排序的 Query/Interactive `pipeline_nodes`；
- Control 的作用域、显式直接父节点、传递祖先/后代、拓扑顺序、候选域 Base Output、直接数据 View、Interactive consumer、派生 View、内容绑定和最终影响上界；
- Named Output 到直接 View consumer 的反向索引，以及首次水合的固定顺序。

Dependency Contract 编译 `state owner → writer / consumer binding`。每条 consumer edge 携带 mode、projection、field/inputs、empty policy、trigger 和直接/传递影响；每条 View writer edge 携带 action/value mapping 与唯一 writer 约束。Planner、Server、Browser、HTML 与 CLI 只消费这份 binding graph，不能再根据 DOM 或字段名重新猜测效果。

下面这些层只能消费或投影该契约，不能各自再推导一张“差不多”的图：

```text
Workspace validation
Query Planner / Interactive Planner
Server Pipeline / AI context / dependencies CLI
Canvas Runtime / HTML Export / Web Component Adapter
```

诊断 UI 也是该契约的只读投影，不维护第二份依赖图：Header 只显示 Source 与 Dataset Transform 的 Query 层状态；每个 View 的标题栏按拓扑序持有自身可达的 Query/Interactive 节点和最终 Renderer 状态。View 信号灯只在 `queued/loading/stale/error/cancelled/unavailable` 时出现，`not_run/ready/empty` 自动隐藏。这样正常阅读没有常驻技术噪音，分支卡住时又能直接定位到具体 Source、Interactive Transform 或 Renderer；导出 HTML 的 Query 节点已经固化为 Ready，因此只会短暂显示端侧计算和渲染状态。

Browser Runtime 注册 Transform 和 View 时会核对 data inputs、Control inputs、Query Parameter inputs 与 Output names；任何注册结果和编译契约不一致都会直接失败，不能静默运行另一张图。注册 payload 只承担 drift assertion，调度器、View 等待态和声明式 Renderer 实际读取的输入都来自 Dependency Contract，不会“校验契约后又执行原始配置”。浏览器不根据 DOM 或作用域层级猜测 Control 依赖，统一使用契约中的 `control_order`、`depends_on` 与 `dependency_ancestors`。

候选型 Control 使用 `depends_on` 声明直接父节点。引用采用相对 owner 的稳定前缀：`dashboard.<id>`、`section.<id>`、`view.<id>`。Dashboard 只能引用当前 Dashboard；Section 只能引用当前 Dashboard 或本 Section；View 只能引用当前 Dashboard、所在 Section 或自身 View，不能跨兄弟容器。Compiler 解析 canonical key、计算传递闭包和拓扑顺序，并拒绝未知引用、越界和完整环路径。Runtime 按拓扑顺序协调候选域并一次提交 canonical Control 快照；链 `A depends_on B`、`B depends_on C` 只写两条直接边，A 自动拥有 B/C 两个有效祖先。是否被某个 consumer 当作 filter 与候选依赖无关。

契约缓存使用并发安全的首次初始化。同一 load snapshot 即使同时收到多个 Planner、Server 或 Canvas 请求，也只编译一次并返回同一个对象；热更新才创建新的快照和契约。

契约必须“可执行才存在”。编译器会直接拒绝环、未知 Output、`server-python` 依赖浏览器 Runtime，以及 Interactive Transform 消费其下游 View 作用域之外的 Control。`validate` 在契约无法形成时可用容错扫描补充定位信息，但该扫描不是第二张运行时 DAG。

Query/Interactive Python 上下文只暴露节点显式声明的参数。仅仅因为某个值存在于 Dashboard 全局状态，不代表节点可以读取它；否则缓存指纹和依赖图都会失真。

Selection 的 `scope_views` 表示结构作用域，不等于每个 View 都一定含有可筛字段。契约进一步记录每个 View 的字段、operator 和输入 Output：Output Schema 已保证字段时标为 `declared`；表格 Schema 未保证时标为 `runtime`，在真实数据水合后检查；无表格输入时标为 `not_applicable`。因此 `affected_views` 是保守影响上界，实际重绘仍按当前 Output 的字段契约收窄，不伪造静态精度。

人和 AI 可以在运行前检查同一份图：

```bash
dataviz inspect dependencies WORKSPACE DASHBOARD
dataviz inspect dependencies WORKSPACE DASHBOARD --format json
```

## 2. 两个执行入口与统一 Input State

用户和 AI 只面对两个一级入口：

| 入口 | 声明位置 | 语义 | 修改后发生什么 | HTML 导出 |
| --- | --- | --- | --- | --- |
| Query Parameter | `dashboard.query_parameters` | 决定取什么数据 | 新建 Query Run，重新执行 Source/Dataset Transform | 固定为导出时已提交值 |
| Control | Dashboard/Section/View 的 `controls` | Query 后提供交互输入 | 由 consumer binding 局部筛选、重绘或重算 Interactive Transform | 保持交互；能力取决于 Runtime/export mode |

> **设计状态：已实现。** Dashboard v11、Transform v3、Dependency Contract v7、State Snapshot v2 和 Runtime v6 已在 Schema、Compiler、Server、Browser、HTML、CLI、示例与测试中同步切换；旧 `kind` 和双输入协议不提供兼容分支。

### Input State 只保存事实

Query Parameter 与 Control 不合并为一个作者可见的通用 `states:` 列表。两者仍然保留清晰的执行边界，但共用同一份值状态契约：

| 维度 | Input State 负责 | Input State 不负责 |
| --- | --- | --- |
| 值 | scalar、set/list、range 等 canonical value 与 `value_type` | 值在某个下游代表筛选、算法还是展示 |
| 候选 | 静态/动态 option domain、初始化和有效值协调 | 把候选表当作业务合法性白名单 |
| 意图 | 仅候选型集合保存 `all_available | explicit` | 给自由文本集合臆造 All/Exclude 语义 |
| 生命周期 | initial、current/draft、revision 与恢复证据 | 决定所有消费者必须同时提交 |
| 所有权 | Query Parameter 或 scoped Control 是唯一 owner | 让组件、View 或 Transform 保存第二份影子状态 |

因此 `multiple_select` 的可选 `intent` 不是某种 Control kind 的专属状态，而是**候选型集合状态**；canonical entry 为 `{value, revision, intent?}`。Query Parameter 与 Control 都可以使用。`multiple_input` 是自由集合，只保存 `list[T]` value：空列表只是“没有提供值”这一事实，不自动等于不过滤、空结果或恢复默认。是否有值通过 `projection: present` 投影，业务含义由每个 consumer 决定。

Selection 这个词只保留给用户手势：点击点、选择行、矩形或套索框选。它是一个 writer action，不再是 Control 的固有种类。Compute 同样不再是 Control 的固有种类；它只是某个 Interactive Transform 把 Control 值作为计算参数消费。一个 Control 可以同时驱动即时 View 投影和需要 Apply 的重型 Transform，不能因为声明时被贴上一个 `kind` 就强迫所有 consumer 共用一种提交方式。

### Producer、State 与 Consumer Binding

统一模型是：

```text
Control Component ─┐
                   ├─→ typed Control state ─→ filter binding ─→ View / Transform input
View user event ───┘                      └─→ value binding  ─→ View / Transform argument

Query Parameter component → typed Query state → explicit RUN → Query input bindings
```

- **Producer** 只产生类型化 action，例如 `set`、`select_one`、`select_many`、`clear`、`reset`；它不知道下游用途。
- **Input State** 校验 action、更新 canonical value/intent/revision，并按 option-domain 拓扑协调候选型后代。
- **Consumer Binding** 声明目标节点如何使用该状态。作用域只决定哪些 consumer 可以引用 Control，不再暗示筛选效果。
- **Scheduler** 根据 binding、consumer trigger 和 state revision 计算局部失效；不再维护 selection delta 与 compute delta 两套平行状态机。

View 点击、框选或表格行选择不是第三个一级入口，也不拥有独立状态；它只通过 `control_binding` 写入一个类型兼容的既有 Control。程序化 View 更新只读取同一 Control 并更新选中投影，不得重新发出用户 action。

### Binding 的最小语义

Binding 把“读取什么”和“怎样消费”分开，但不允许无意义的任意组合：

1. **Projection**：`mode: value` 从状态读取什么。第一版只需要 `value | present | intent`；字符串简写等于 `mode: value + projection: value`。`present` 对 `null`、空字符串和空集合返回 false，但 `0`、`false` 和非空集合仍为 true；`intent` 只允许候选型集合。
2. **Mode**：consumer 怎样使用状态。第一版只需要 `value | filter`。`value` 把投影后的值交给节点本地 alias；`filter` 固定消费 canonical value 与可选 candidate intent，在进入 View/Interactive Transform 前对显式表输入应用 include 筛选。`filter + projection: present/intent` 在 Schema 阶段拒绝，不能把 boolean 或意图字符串当成待匹配字段值。

`filter` 必须明确目标 `field`，并明确空集合策略：

| `empty` | 语义 | 典型用途 |
| --- | --- | --- |
| `passthrough` | 空值不添加筛选条件 | 可选 `multiple_input` Item 列表 |
| `match_none` | 空值产生空结果 | 用户明确清空一个样本选择 |

`empty` 只解释自由空集合或 `explicit + []`；候选型集合的 `all_available` 由 resolver 根据当前候选域解析，它不是第三种 `empty`。第一版 filter 仍只有 include，不加入 exclude、任意谓词或 Filter Group。SQL Source 不使用通用 `mode: filter`：SQL/文件/Python Source 自己拥有业务查询，Query Parameter 通过 `value/present/intent` 投影给本地 alias，由 Source 明确解释。

目标 Query binding 例如：

```yaml
query_inputs:
  item_nbrs: item_nbrs
  item_nbrs_present:
    parameter: item_nbrs
    projection: present
```

目标 Interactive binding 例如：

```yaml
interactive_transforms:
  - id: simulation
    inputs:
      base: dataset:features/main
    control_inputs:
      regions:
        control: dashboard.region
        mode: filter
        field: region
        inputs: [base]
        empty: match_none
      simulations: dashboard.simulations
    trigger: apply
```

字符串 `dashboard.simulations` 是 `mode: value + projection: value` 的简写。直接 View consumer 使用同一 binding 结构；Bound View 的 `control_binding` 仍负责真实用户 writer 与 selected projection，不等同于对该 View 本身应用 filter。

### 生命周期与运行证据

Query Parameter 仍拥有整张 Query Card 的 draft/committed 事务：只有明确查询才把快照交给 Query DAG。Control 则保存一份最新 canonical revision；每个 consumer 根据自身 `auto | apply | manual` trigger 保存 applied revision。于是同一个 Control 改变后，轻量 View 可以立即更新，而重型 `server-python` 分支继续展示上一 applied revision 并标记 stale，直到用户 Apply。不能再用“Selection 一定即时、Compute 一定提交”代替真实 consumer 成本。

State Snapshot v2 统一保存每个 Query Parameter/Control 的 canonical value、可选 intent 和 revision，并按 Dependency Contract 把 Runtime 原始 `applied_revisions` 规范化为 `consumer_revisions`。每个 View/Interactive Transform consumer 都记录 trigger、整体 stale 状态，以及各 Control 的 `effective_revision / applied_revision / stale`；未知 consumer/control 会被丢弃，非法或领先于 effective state 的 revision 会被拒绝。Result 只封存这份紧凑审计证据，Evidence 原样继承，不复制整份 State Snapshot。这样 Apply/Manual 分支仍可展示旧结果，但不会把尚未应用的最新 Control 冒充成结果上下文。

### 已完成的 v10 → v11 破坏式迁移

v11 已采用一次性破坏迁移，Runtime 不兼容旧字段：

| v10 旧字段 | v11 编译语义 |
| --- | --- |
| `kind: selection` | 删除 `kind`；原作用域筛选边变为显式 `mode: filter, empty: match_none` binding |
| `kind: compute` | 删除 `kind`；原参数边变为 `mode: value` binding |
| `selection_inputs` | 合并到 `control_inputs` 的 filter binding |
| `compute_inputs` | 合并到 `control_inputs` 的 value binding |
| `context.selections / context.compute_params` | 合并为局部、只含显式声明项的 `context.control_inputs` |
| selection/compute delta | 单一 Control revision delta，由 consumer binding 和 trigger 解释 |

该切换已同步升级 Dashboard v11、Source/Dataset/Interactive Transform v3、Dependency Contract v7、State Snapshot v2 与 Browser Runtime v6；Parameter Domain v1、Presentation v2 和 Named Output 语义不变。版本号是协议边界，不允许只升级 YAML 而继续运行旧 Browser/Server 状态机。

迁移不得改变 Query/Interactive 两阶段边界、Control 的 Dashboard/Section/View 作用域、单 writer 限制、候选域拓扑、Named Output、局部失效或 HTML Runtime 能力。`inspect dependencies` 必须展示每条 binding 的 mode、projection、field、empty、trigger 和受影响 consumer，让“同一个值为什么在这里不过滤、在那里产生空结果”可以在执行前回答。

### Query Parameter（当前 v11 契约）

- 只在用户点击 **查询** 后提交。
- Dashboard 保存 canonical 值；`multiple_select` 还保存 `all_available | explicit` 意图。Source/Dataset/Interactive Transform 必须用 `query_inputs` 映射到节点本地 alias。
- 进入节点执行上下文和缓存键的是投影后的本地 `context.query_inputs`，未声明的全局参数不可读取。
- 修改草稿但没有重新查询时，页面仍展示上一次 Run 的已提交值和结果。

`query_inputs` 的 key 是节点本地名称，也是 SQL named placeholder 或 Python/Browser Context 的 key；value 是 canonical Query Parameter id。字符串是值投影的简写。结构化绑定既可把 `range_input/date` 投影为端点，也可把 `multiple_select` 投影为选择意图：

```yaml
query_parameters:
  - id: job_date_range
    type: range_input
    value_type: date
    required: true
    default:
      - {mode: relative, anchor: today, offset: -3d}
      - {mode: relative, anchor: today, offset: -1d}

sources:
  - id: sales
    type: sql
    adapter: warehouse
    code: sources/sales.sql
    query_inputs:
      warehouse_id: warehouse_id
      start_date: {parameter: job_date_range, part: start}
      end_date: {parameter: job_date_range, part: end}
      city_values: cities
      city_intent: {parameter: cities, projection: intent}
```

Query Parameter 的公开选择意图只有两种：`all_available` 表示当前父级范围内全部可用成员，`explicit` 表示调用方明确给出的有限列表；`explicit + []` 是明确空集。Clear 产生明确空集，Reset 只是恢复声明的 `initial`，loading/error 只是请求状态，三者都不是新的业务意图。当前不提供 `exclude`，避免把补集、候选版本和 SQL 负担扩散到所有作者与 Runtime。

值与意图必须分开投影。以 `province → city` 的有界候选域为例，`city_intent=all_available` 允许 Source 跳过 City 级过滤并使用上层范围；`city_intent=explicit` 且值非空时按 City 过滤；`explicit + []` 表示明确空结果。未声明 `projection: intent` 的节点继续只看到值，不得从空列表猜测 All 或 None。`projection: intent` 只允许引用 `multiple_select`，不能与日期 `part` 同时使用。

```sql
where warehouse_id = :warehouse_id
  and job_date between :start_date and :end_date
```

#### Parameter Domain DAG

Query Parameter 的值契约、候选数据域、页面组件和提交状态是四个不同概念。`type/value_type/required` 定义 canonical value；Parameter Domain 只提供面向人的当前候选空间，不是 Source 执行的权威白名单；Select、Date Picker、Slider 等组件只是编辑投影；父页面维护 draft，只有用户明确点击查询后才提交为 Query Run 的 immutable parameter snapshot。不能为了加载候选而提前执行普通 Source，也不能让未提交 draft 冒充当前 Result 的参数。

Dashboard v10 新增命名 `parameter_domains`。第一版 Domain 是在正式 Query DAG 之前执行的轻量 SQL table：它复用 Workspace Adapter、参数化 SQL、超时、缓存和密钥脱敏边界，但不进入普通 Source/Dataset DAG，不产生 Base Named Output，不进入 Catalog，也不单独创建 Result。一个 Domain SQL 返回一张关系表，多个 Query Parameter 可以从不同字段投影候选；这避免为省份、城市、区县分别执行重复 SQL：

```yaml
parameter_domains:
  - id: locations
    type: sql
    adapter: warehouse
    code: parameter_domains/locations.sql
    cache: {mode: session}

query_parameters:
  - id: province
    type: multiple_select
    value_type: text
    initial: {mode: all}
    options:
      mode: domain
      source: locations
      value_field: province_code
      label_field: province_name

  - id: city
    type: multiple_select
    value_type: text
    initial: {mode: all}
    options:
      mode: domain
      source: locations
      value_field: city_code
      label_field: city_name
      depends_on:
        province: {field: province_code}
```

```sql
select distinct
    province_code,
    province_name,
    city_code,
    city_name
from dim_location
order by province_name, city_name
```

`value_field` 必需；`label_field` 缺省时使用 value。可选 `description_field/group_field/keywords_field/sort_field/disabled_field` 只提供候选元数据，不改变 canonical value。投影按 canonical value 自动去重，因此一张包含省市明细的关系表可以同时产生独立 Province/City 候选；不需要级联时不声明 `depends_on`。同一 value 若对应冲突 label/metadata，Domain 解析必须失败，不能随机选一行。null value 不进入候选；字段缺失、类型不符、重复 Parameter/Domain id、未知 source/parent、自依赖、间接环和不稳定元数据都有稳定 validation/runtime code。

`options.depends_on` 的 key 是直接父 Query Parameter id，`field` 是 Domain Table 中与父值匹配的列。Compiler 从这些边生成 Parameter order、祖先闭包和受影响后代；作者不重复声明传递依赖。父参数改变时，Runtime 从同一 immutable Domain snapshot 过滤行并重新投影子候选，不重新执行 SQL。若 Domain 本身声明 `query_inputs`，它只能读取拓扑上更早的 Query Parameter；对应上游 draft 改变时只使该 Domain cache key 失效并重新查询，仍不得依赖普通 Source、Dataset/Interactive Transform、Control、View 或自身后代。

Parameter Domain resolution 是独立、可选的候选发现能力。Server Parameter Resolver 在 Dashboard 打开或 draft 上游值变化时，按 Domain/Parameter 拓扑解析候选；外层 Query Panel Shell 只渲染返回的类型化 Choice，不自行解释 SQL 或业务字段。这不是 Canvas 内的 `browser-js` Interactive Runtime。AI 也可以显式执行 `dataviz parameters options` 探索当前候选，但这一步不是 `dataviz run` 的前置条件。

CLI 候选探索不能把几万行 Choice 或未经压缩的 JSON 直接写入终端。每次 `parameters options` 执行 Domain SQL 后，把每个 Domain 的原始多列表以 immutable `options_id` 封存在 Workspace `.dataviz/parameter-options/`，默认只展示 10 行高密度表格和总行数，显式预览/分页也硬限制为 100 行。`parameters filter <workspace> <options_id> --where field=JSON --column field` 只读取同一快照，支持按原始查询 key 筛选、选择列和分页，不重新执行 SQL。候选快照是短期 AI 探索缓存，不是 Query Result、Named Output、Catalog Entry 或 Source Artifact；其 ID、目录和生命周期也不与 `result_id` 混用。`dataviz prune` 把它纳入普通 cache 数量/时效策略并保持 preview-first，避免长期堆积。

`dataviz run` 永不隐式执行 Parameter Domain，也不以当前候选表做成员校验。AI 已知 `item_nbr` 等值时可直接通过 `--query-param` 运行；CLI 只校验 Query Parameter 的类型、`value_type`、required 和范围契约。未传参数时仍只使用无需 Domain 即可物化的声明初始值；`initial: all/first` 若必须依赖实时候选才能求值，则作者应让参数可空、提供可直接物化的初始值，或要求调用方显式传值。若 AI 想绕过 Source SQL 本身声明的 `where item_nbr = :item_nbr`，应使用另一口径或 Analysis Overlay 修改 SQL；跳过候选查询不会改写 Source 逻辑。

父页面为每个 tab/Dashboard 保存 Domain snapshot generation、draft Query Parameter，以及每次成功 Query 封存的 committed `{values, intents}` snapshot。首次水合按 `initial` 解析；普通候选刷新与上游编辑遵守共享 reducer：`all_available` 跟随全部新候选，`explicit` 保留有效交集，原非空值完全失效才恢复 `initial`，用户主动空集保持为空。上游变化后受影响字段进入 loading/stale；所有 required Domain 稳定前禁用查询。迟到响应按 dashboard/revision/request generation 丢弃，切换 Dashboard 或发起新请求会取消旧请求；失败时保留最后一份成功候选用于阅读，但标记 stale 并禁止用未验证 draft 创建 Run。坏掉的旧 Dashboard 草稿只能阻止该 Dashboard 查询，不能阻止 Shell 切换到其他 Dashboard；离开时立即取消旧 Domain 请求，刷新只重试当前路由对应的 Dashboard。

Domain cache 至少包含 Dashboard definition hash、Domain code hash、Adapter/auth identity、canonical `query_inputs` 和 Workspace revision；不同 tab/session 不共享含权限差异的 session cache。返回行数受 Domain `max_rows` 限制，超过上限明确失败，不能悄悄截断网页候选空间。Parameter Domain 的候选池必须有界并适合一次完整加载；数十万 `item_nbr` 等实体不应成为 Select 候选。作者应缩小业务参数层级，或在用户已知 ID 时使用 `multiple_input` 直接输入，不能通过扩张候选组件掩盖错误的参数边界。数据驱动 Date/Slider bounds、Domain-driven initial 和 Parameter Preset 也不进入 v1，不得由作者自行发明非标准 YAML 字段。

浏览器刷新不等于恢复初始值。Query Parameter draft 的恢复优先级固定为：当前 URL 显式值 → 该 tab/Dashboard 保存的 draft → 当前 Result 的 committed snapshot → 声明的 `initial`。普通页面恢复后再按当前 Domain 协调 draft：仍在候选中的广东/深圳原样保留；部分失效时保留有效交集；原非空值完全失效才按 `initial` 恢复；用户主动空集仍为空。普通页面刷新命中 session/TTL cache 时不重新执行 SQL；Server 重启、Domain/Adapter/input hash 改变或 TTL 到期才查询新 snapshot。即便新 Domain 使 draft 改变，旧 Result 和它的 committed 广东/深圳仍保持不变，页面只标记参数待重新查询，绝不能用新候选静默改写旧分析结果。

Revert 是另一条严格路径：它以最后一次成功 Query 的完整 committed `{values, intents}` 为目标，一次性交给 Parameter Resolver，并按依赖拓扑重新水合全部候选与字段；Shell 在同一个事务中替换候选、值和 intent，不逐个触发控件 change，也不执行正式 Query。恢复完成后 Query Card 回到 Applied。当前 Domain 缺少 committed value 时，Resolver 仍原样保留该值并附加只读 unavailable choice；候选是给人的建议，不是 Source 参数合法性的白名单。Revert 不保存旧候选表，也不退回声明 `initial`。

只要当前 Dashboard 存在动态 Parameter Domain，Query Card 标题“查询参数”的右侧显示一个克制的 reload 图标，Tooltip/ARIA 明确写“刷新参数选项”；纯静态参数看板不显示。该动作强制绕过 Domain cache 并重新解析全部候选，不刷新网页、不执行正式 Query、不恢复默认值、不清空有效选择。存在 committed snapshot 且 draft 的 values 或 intents 已改变时，同一区域才显示“恢复已应用参数”的 Revert 图标；Applied 状态不常驻展示无意义动作。两个动作在加载期间都禁止重复点击。刷新成功只短暂提示候选已更新；Revert 成功提示已恢复已应用参数。失败时保留最后一份成功 Domain 与当前 draft，不能用空响应替换候选。刷新导致 draft 协调变化时只标记“参数待查询”，用户仍需点击 Header 的查询按钮才创建新 Result。

```text
Parameter Domain SQL → immutable Domain Table
                         ├─→ province candidates/draft
                         └─→ province-filtered city candidates/draft
                                      ↓ explicit RUN
                         committed Query Parameter values + intents
                                      ↓
                                 Query DAG → Result
```

Parameter Domain 与普通 Source 都可以查询 SQL，但产品语义不能合并：前者只回答“网页当前建议用户选择哪些值”，后者才产生“本次分析的数据与口径”。候选缺少某个值不代表 Source 禁止 AI 使用该值。

Parameter Domain 也不进入任何 Result consumer。portable HTML 和分享链接都从一个已经封存的 Result 开始，只携带该 Result 的 committed Query Parameter values/intents；Query Card 只展示固定值，不能编辑、级联或再次 RUN。导出/分享不得嵌入 Domain Table、SQL、候选列表、Adapter、Server session cache 或 CLI `options_id` 快照，也不得在打开页面时访问 Parameter Domain endpoint。分享链接虽然仍由 Dataviz Server 渲染并可执行声明允许的 `server-python` Interactive Transform，但这不会恢复 Query Parameter authoring 能力；若要改变取数参数，必须回到正式 Dashboard 创建新的 Query Run 和 Result。

Parameter Domain DAG 与 Interactive DAG 没有执行边：前者只在 Query 前为 Query Parameter draft 提供建议候选并协调网页选择状态，后者只在 Query 后消费 Base Named Output 和已提交 Controls 做计算或渲染。Domain 不定义 Query Parameter 的合法成员集合，不进入 Canvas Runtime Manifest，不触发 Interactive Scheduler，也不能被 `browser-js` 或 View Renderer 读取。

相对日期不是自由格式字符串。当前严格语法只接受 `anchor: today` 与整数日偏移 `offset: ±Nd/0d`。日期范围是两个独立 Date Atom 的有序对，每个端点可以是固定 ISO 日期，也可以是相对表达式，因此可以表达“固定开始日 + 相对结束日”。默认值编辑器也直接编辑这两个 Atom：每个端点只有“固定日期/相对今天”模式和一个随模式切换的值控件，不同时维护隐藏的 fixed/offset 副本，不使用 `start_offset/end_offset` 范围对象；固定模式复用运行界面的 ISO DatePicker 输入、日历与校验，相对模式使用整数 offset。`today` 按 `workspace.context.timezone` 求值，并在 tab 首次构建参数表单或 CLI Run 开始时解析为具体 ISO 日期。Query Run、缓存指纹、SQL 绑定和 HTML Export 保存的都是这个具体值；导出页不会在第二天重新解释“today”。Server 启动时不预计算，避免跨午夜后继续使用旧日期。

### Control、候选意图与 consumer binding

Dashboard、Section 与 View 是 Control 的三个稳定 owner。作用域只决定 Control 在哪里可见、哪些下游可以引用它；Control 本身不携带 selection/compute kind。所有 Control 都保存同一种 canonical Input State：

```text
{value, revision, intent?}
```

`intent` 只属于候选型多选集合：`all_available` 表示持续跟随完整候选域，`explicit` 表示用户明确选择的集合，`explicit + []` 表示明确空集。自由输入的 `multiple_input` 只保存值列表，不伪造候选意图。候选域变化时，`all_available` 扩展到全部新候选；`explicit` 保留有效交集；原非空集合完全失效时才回到 `initial`；用户主动空集保持为空。

`depends_on` 只表达候选域的直接父 Control，不表达数据筛选。Compiler 解析 `dashboard.<id>`、`section.<id>`、`view.<id>`，计算祖先/后代和拓扑顺序，并拒绝未知引用、越界和环。Cascader/Tree Select 的 `path_fields` 是单个 Control 内的层级路径，也不等同于多个 Control 的依赖边。

Control 对数据的效果由每个 consumer 显式声明：

```yaml
control_inputs:
  region:
    mode: filter
    control: dashboard.region
    field: region
    inputs: [rows]
    empty: passthrough
  simulations:
    mode: value
    control: dashboard.simulations
    projection: value
```

- `mode: filter` 只裁剪 `inputs` 明确列出的 table alias；必须声明字段、operator 与空值策略。
- `mode: value` 把 `value | present | intent` 投影到 consumer-local alias，不隐式改写表。
- 同一 Control 可以被不同 View/Transform 以不同 mode 消费，也可以同时驱动 `auto` 与 `apply/manual` 分支。
- View 的 `control_binding` 是 writer edge。一个 Control 最多有一个 writer View；Plotly、Table 与 Custom Renderer 通过 `select / select_many / clear / reset` Action 写 canonical state。

Runtime 分开维护 current state 与 applied state，并为每个 View/Interactive Transform 记录 applied revision。即时 consumer 可以使用新 revision 更新，显式 Apply consumer 继续指向旧 revision，直到用户提交；标题、内容插值、状态摘要和 provenance 必须引用真正产生当前结果的 applied state，不能把未应用草稿伪装成结果上下文。

Plotly 默认工具栏反映真实能力：未绑定 writer 的图不显示选择工具；绑定后的图才显示矩形选择、套索选择与恢复默认选择。程序化 projection、状态恢复或 Renderer 重绘不得重新发出用户事件，从根源上阻断 `View → Control → View` 反馈循环。
### Consumer trigger 与 applied revision

Interactive Transform 支持：

- `trigger: auto`：Control 变化后 debounce 并自动执行；新 revision supersede 旧计算。
- `trigger: apply`：Control 变化先更新 current state，分支保持旧 applied revision 并标记 stale，用户 Apply 后再执行。
- `trigger: manual`：只由明确按钮或 CLI/API 调用。

`browser-js` 默认 `auto`，`server-python` 默认 `apply`；作者可显式覆盖。同一 Control 可以同时被不同 trigger 的消费者读取，因为触发策略属于 consumer，不属于 Control。
## 3. 两种 Transform

阶段和执行位置是两个不同维度：Dataset/Interactive 描述业务生命周期，Server/Browser 描述 Runtime 位置。

### Dataset Transform

- 字段：`dataset_transforms`。
- standalone schema：`dataviz/dataset-transform/v3`。
- 执行位置固定为 Server Python。
- 由 Query Parameter 和上游 Named Output 决定。
- 适合多 Source 合并、数据清洗、特征构造、基础指标和一次 Run 内固定的复杂计算。
- 执行完成后产生 Base Named Output；任何 scoped Control 都不得触发它。

### Interactive Transform

- 字段：`interactive_transforms`。
- standalone schema：`dataviz/interactive-transform/v3`。
- 只消费已经确定的 Base/Derived Named Output。
- 可以显式消费已提交 Query Parameter 快照，以及带 mode/projection 的 Control consumer bindings。
- 不访问 Adapter、不重新查询 Source。
- 适合 Monte Carlo、模型推断、运筹优化、情景分析和交互聚合。

当前 DSL 形态：

```yaml
dataset_transforms:
  - id: features
    runtime: server-python
    code: transforms/features.py
    inputs:
      orders: source:orders/main
    query_inputs:
      start_date: start_date
      end_date: end_date
    outputs:
      main: {kind: table}

interactive_transforms:
  - id: monte-carlo
    runtime: server-python
    code: transforms/monte_carlo.py
    inputs:
      base: dataset:features/main
    query_inputs:
      start_date: start_date
      end_date: end_date
    control_inputs:
      seed: {mode: value, control: dashboard.seed}
      simulations: {mode: value, control: dashboard.simulations}
      region: {mode: filter, control: dashboard.region, field: region, inputs: [base], empty: passthrough}
    trigger: apply
    export: {mode: snapshot}
    outputs:
      summary: {kind: table}
      distribution: {kind: table}
```

Transform 代码只看到作者显式选择的局部 alias：

```text
context.query_inputs
context.control_inputs
context.inputs
```

`mode: filter` 在 Transform 执行前裁剪明确列出的表输入，`mode: value` 只产生 `context.control_inputs` 中的局部值。浏览器 Runtime 直接从 `context.inputs` 读已解析数据；Server Python 通过 `table()` 或 `input()` 读取，`context.inputs` / `context.artifact(name)` 中的 descriptor 只用于 provenance 与调试。局部失效由 binding graph 计算，不暴露两类全局状态袋。

Interactive Transform 的上下文不提供 Adapter。即使运行在 Server，也不能因为实现位置方便而偷偷重新取数。

## 4. Interactive Runtime

Interactive Transform 有两种 Runtime，但共享同一个输入、Output、状态、错误和生命周期契约。

| Runtime | 主要用途 | Python 包能力 | 独立 HTML 重新计算 |
| --- | --- | --- | --- |
| `server-python` | 原生模型、运筹优化、大规模或专有 Python 计算 | 使用 Workspace Server 环境 | 不支持；只能 snapshot 或 unavailable |
| `browser-js` | 筛选、聚合、轻量模拟和常规交互计算 | JavaScript/Web API | 支持，默认首选 |

选择由执行边界决定：

```text
浏览器内的 snapshot 数据加工、便携交互 → browser-js
完整 Python 生态、复杂模型或重型计算 → server-python
```

浏览器 Runtime 受浏览器的内存、CPU 和资产边界约束；需要原生 Python 依赖、大模型、运筹求解器或明显超出浏览器容量的数据，应直接使用 `server-python`。作者语言偏好不构成新增 Runtime 的理由。

### server-python

- Server 根据 `run_id + Named Output reference` 读取当前 tab 的 Base Artifact，浏览器不重新上传整份 Dataset。
- Query 计划会显式分类所有被可达 `server-python` 分支消费的 Base Output；分类结果进入 Run 诊断，不能靠 Interactive 运行时临时猜测或重新取数。
- Artifact 的物理位置是 Workspace `.dataviz/runs/<run-id>/artifacts/`，不在 Dashboard 文件夹；逻辑所有权是 `tab session + dashboard + run + canonical output reference`。刷新同一 tab 可恢复，跨 tab 请求必须拒绝。
- 每次计算在独立 Python 进程执行，支持 timeout、cancel、traceback、progress 和结构化运行证据。
- 缓存键至少包含上游 Output content hash、代码/依赖、已提交 Query Parameter 与声明消费的 Control delta。
- 新交互只取消当前 Dashboard 的目标分支，不干扰其他 Dashboard、tab 或用户。

### browser-js

- 运行在独立 Web Worker，不能访问 DOM。
- 继续作为开箱即用和导出 HTML 的默认 Interactive Runtime。
- 支持 Promise、timeout、supersede cancellation 和可序列化错误。

## 5. Named Output 与 Export Contract

Source、Dataset Transform 和两种 Interactive Transform 共用同一个 Named Output 协议。Renderer 不关心 Output 来自哪个 Runtime。

每个 Interactive Transform 必须声明导出模式：

```text
interactive  → 导出后仍可根据控件重新计算
snapshot     → 只导出当前已提交状态和结果
unavailable  → 导出页明确展示该分支不可用
```

约束：

- `browser-js` 可以使用 `interactive`、`snapshot` 或 `unavailable`。
- `server-python` 的声明仍需给出离线意图，但只要 Dashboard 的可达 Interactive DAG 中存在 `server-python`，HTML Export 就整体不可用；Runtime 必须引导用户创建分享链接，不能把重型计算伪装成静态分支。
- 分享链接固定创建时的 Query Parameter 与 Base Output，不允许再次 Run；Browser JS 继续在浏览器执行，`server-python` Interactive Transform 通过 Dataviz Server 执行。这是分享链接相对 HTML Export 唯一增加的计算能力。
- `snapshot` 必须把影响结果的 selection/compute Controls 以只读上下文展示，不能留下能修改但不会重算的假控件。
- `unavailable` 必须显示原因和需要 Server 的能力，不能静默留白。

一次百万次模拟不应该输出一百万个 UI 节点。Transform 应返回汇总、分布、置信区间和必要样本；Renderer 只消费适合展示的 Named Output。

## 6. Workspace 与分享边界

```text
workspace/
├── workspace.yaml
├── shared_caches/                 # Server 分享结果，不进入 dashboards/
│   └── <dashboard>_<timestamp>_<run>/
│       ├── manifest.json
│       ├── query-result.json
│       └── artifacts/
├── auth/
│   ├── adapters.yaml
│   └── adapters.local.yaml
└── dashboards/
    └── 业务分析##门店周报/
        ├── dashboard.yaml
        ├── presentation.yaml       # 可选
        ├── sources/
        ├── transforms/
        ├── data/
        ├── assets/
        └── canvas/                  # 可选的完整逃生口
```

- Dashboard 文件夹末级名称是导航显示名，不存在额外导航别名。
- `##` 前的片段表达逻辑目录；Dashboard 首次删除只把物理目录改名为 `__TRASH__##原完整名称`，不删除文件。回收站始终显示去掉该前缀后的完整物理名称，例如 `shein##sale_analysis`，而不是只显示叶子名。
- 空目录树没有可恢复的 Dashboard 资产，删除时直接从 `workspace.yaml` 移除，不进入回收站；Trash Loader 也不展示没有 Dashboard 后代的空目录。回收站右键“永久删除”必须再次确认，确认后才删除对应的 `__TRASH__##` 磁盘目录，且不可恢复。
- `dashboard.id` 是 CLI、API、DAG、缓存与状态使用的稳定机器 ID。
- 所有机器 ID 使用同一可移植语法：ASCII 字母或下划线开头，只含字母、数字、点、下划线、连字符，不能以点结尾或使用 Windows 保留设备名。显示语言属于文件夹名、title/label/description；机器 ID 不承担展示职责。
- `title`、`subtitle`、`description` 是页面内容，可以与文件夹名称不同。

`workspace.yaml` 只承担 Workspace 元数据、Runtime 配置、空目录和顺序等无法从 Dashboard 文件夹推导的状态。加载 Workspace 时按磁盘发现 Dashboard；单个损坏 Dashboard 不得拖垮整个 Workspace。

Dashboard 只引用逻辑 Adapter 名称，不保存账号、密码或连接 URL。分享 Dashboard 时，同事只需要绑定自己的 Workspace Adapter。Dataviz 自己不会把 Adapter secret 序列化进浏览器、HTML 或查询证据，并会从错误、日志和 traceback 中脱敏；但可信 Python Source 拿到 Adapter 后仍能主动把任意值作为业务 Output 返回，作者必须避免输出凭据。

Server 的 SHARE 菜单只保留“分享链接”和“导出 HTML”两个动作。分享链接为 `/shared/<share-id>`，每次创建都原子写入 `workspace/shared_caches/<dashboard>_<UTC timestamp>_<run>/`；目录保存 Query Result、Control 状态、清单和经过哈希验证的 Artifact，不污染 `dashboards/`。打开链接时 Server 为每个浏览器会话恢复一份不可变 Query Run：Query Parameter 只读且不能 Run，Browser Runtime 继续端侧交互，Server Python Interactive Transform 复用现有 Interaction endpoint。Server 重启后仍可从该目录恢复；v1 不自动过期、不随 Dashboard 修改或删除而清理，用户可以直接删除整个子目录。分享页仍依赖当前 Workspace 中兼容的 Dashboard/Transform 定义和正在运行的 Dataviz Server，不是离线文件，也不承诺跨不兼容代码变更继续运行。

Adapter 只有两个权威位置：提交到 Git 的 `auth/adapters.yaml` 保存非敏感定义，本地忽略的 `auth/adapters.local.yaml` 按同名键覆盖凭证。Runtime 不扫描根目录旧文件或 `*.example.yaml`，避免多个隐式来源造成覆盖顺序不确定。

## 7. 逻辑与呈现解耦

`dashboard.yaml` 是必需的逻辑文件，负责：

- 稳定 ID 和业务内容；
- Adapter、Query Parameter 与 scoped Controls；
- Source、Dataset Transform、Interactive Transform 与 Named Output；
- Dashboard、Section、View 的 scoped Control、writer 与 consumer binding；
- View 模板、字段编码和聚合；
- Section/View 的阅读顺序、结构模板、列数和 span。

`presentation.yaml` 是可选的稀疏覆盖，负责：

- Theme、颜色、密度和 design token；
- Section/View 容器外观和 Data Entry Component；
- Query 与 Dashboard/Section/View Controls 托盘的模板、宽度、列数与密度；
- 不改变业务语义的 Renderer options/config；
- 局部 CSS/JS 与 Canvas 资源。

这里的“结构布局”特指 Dashboard Canvas 中 Section/View 的顺序、分栏和占位。Controls 托盘内部的响应式列数、控件宽度和密度仍是 Component 的呈现配置，不进入 Layout Contract，也不能改变 Control 的值、作用域或依赖关系。

### 单一 Layout Contract

结构布局只能有一个 owner。目标声明式结构为：

```yaml
sections:
  - id: night_analysis
    title: 夜间分析
    template: grid
    columns: 12
    views: [daily_after_hour_detail, dow_hourly_sales]

views:
  - {id: daily_after_hour_detail, input: source:sales/main, template: table, span: 6}
  - {id: dow_hourly_sales, input: source:sales/main, template: line, span: 6}
```

Compiler 为每个 Dashboard 快照生成唯一的 `dataviz/layout-contract/v1`。契约包含 Canvas mode、Section 顺序、模板、列数、View 顺序、最终 span、确定性行分配，以及每个值来自显式声明还是模板默认。默认 Renderer、Server、HTML Export、AI context、Validator 与 `inspect layout` 消费该契约，不再从 CSS、Presentation 和 DOM 各自猜测布局。

模板提供结构默认值，不静默吞掉显式属性：`grid` 中显式 span 覆盖模板默认；`single` 必须恰好包含一个全宽 View，声明多个 View 或额外 span 属于确定性冲突；`split`、`comparison`、`chart-and-table` 等模板声明默认比例，并明确哪些结构属性允许覆盖。任意 View 的最终 span 和行位置都必须能由 `inspect layout` 解释。

完整自定义 Canvas 是显式逃生口，Layout Contract 只记录 `mode: custom`、声明的挂载点和稳定 View/Section ID，不尝试静态解释任意 HTML/CSS。其真实几何将由浏览器 `visual-check` 检查。Dashboard v9 与 Presentation v2 已删除 Presentation 的全局 layout、Section template/columns 和 View span；旧结构字段直接校验失败。

### 最终配置的 Semantic Validation

Schema 合法不等于配置有效。Semantic Validation 必须在 Dashboard、Presentation、Component/Renderer manifest 和 Layout/Dependency Contract 全部编译后运行，至少区分：

- `error`：确定无法执行或结构矛盾，例如 `single` 包含多个 View、行占用超过列数、Renderer 不接受声明属性；
- `warning`：能够运行但确定是 no-op，例如 span 被模板忽略、Selection 没有任何 View/Transform/内容 consumer；
- `advice`：依赖经验而非确定事实，例如大型 Table 放入 band、可疑的 `min_height`、Browser Transform 使用 `apply`。

`--strict` 只把 `warning/error` 作为门禁，不能因主观 `advice` 失败。所有诊断必须有稳定 code、文件/字段、最终有效值、冲突来源和最小修复建议；Validator 不得维护第二套 Layout 或 Dependency 推导。

产品外壳与分析画布属于两层视觉所有权，但默认不制造两张彼此竞争的“大卡片”。Server 与导出 HTML Header、Sidebar 及 Workbench 使用连续近白表面；Sidebar 只用轻微表面色差、发丝线和近乎不可见的环境阴影确认导航边界，不形成悬浮卡片。靛蓝用于当前项、主操作和默认分析序列，绿色只表示 Ready/成功等语义状态。这些稳定 Shell token 不跟随 Dashboard Theme 染色，因此切换 `business`、`editorial` 或 `terminal` 时操作入口仍保持一致且退居背景。Dashboard 默认 Theme 是 `business`：白色画布、白色分析卡片、靛蓝分析强调、轻边框、极低阴影和紧凑数据表。Plotly、普通 Table、Perspective 与 Data Entry Component 共同消费 Dashboard Theme token。`plain` 是更克制的中性版本，`editorial` 与 `terminal` 分别用于叙事报告和深色技术监控；Dashboard 可通过 token、`css_class` 和局部 CSS 覆盖画布视觉，但不得越界重写 Shell。

Server 与 portable HTML 是同一分析 Shell 的两个 Host，而不是两套独立主题。`presentation.shell` 唯一拥有 Header 高度、基础正文字号/行高、操作间距、Query Card、Panel 表面、字段 label 和输入控件尺寸；Server `server.css` 只拥有 Sidebar、导航、编辑器和 Server-only 诊断。Query Card 与 Canvas 使用同一个 `clamp(22px, 3vw, 48px)` 页面 gutter，不得再用独立 `max-width` 在宽屏上二次收窄。两种 Host 可以有不同操作能力，但同一个 Dashboard 从 Server 导出后，Header、Query/Control Panel 与正文排版不能发生视觉跳变。Dashboard 自定义 CSS 最后加载，只可有意覆盖 Canvas 内容，不应复制或重写 Host Shell。

Sidebar 默认宽度是 250px，可拖拽调整并按浏览器 Tab 记忆；双击分隔区恢复默认宽度。目录和 Dashboard 名称始终单行显示，空间不足时使用省略号，并只在确实发生截断时通过悬停或键盘聚焦显示物理目录中的完整名称。导航显示名不得回退到 Dashboard `title` 别名。

视觉语言也是公开 Authoring Contract，而不只是默认 CSS。AI 在编写 Presentation 或 Dashboard 自有样式前，应读取 `dataviz docs design-language --format json`；其中固定了信息层级、语义颜色、空间节奏、图表/表格/Data Entry 规则、渐进扩展顺序与验收清单。人类可阅读版本见 [Dashboard 视觉语言](docs/design-language.md)。品牌化可以改变 accent、字体和构图，但不能破坏状态色、弹层、键盘、滚动、响应式和 Renderer 生命周期语义。

删除 Presentation 后，`dashboard.yaml` 必须仍能生成一个朴素、完整、自上而下的看板。推荐扩展顺序是：

```text
声明式默认页面
  → 模板参数
  → Theme token / css_class
  → 单 View 自定义 Renderer
  → 完整 Canvas HTML/CSS/JS
```

默认布局是文档流。`grid`、`split`、`chart-and-table` 等只是可编译的语义模板，不是 Mosaic、拖拽坐标或固定画布协议。

Server Header 是横跨整个 viewport 的唯一全局栏。左侧依次是可点击的 Dataviz Logo/品牌名和 Query 节点信号灯，右侧依次放 SHARE、Dashboard Controls，最右侧固定为“查询 + ▼”分段按钮；Sidebar 与 Workbench 从 Header 下方开始。Logo 本身拥有 Sidebar disclosure，不再增加独立 Navigation/折叠按钮，Sidebar 也不重复显示 “Dashboards” 标题。查询主按钮执行 Query，右侧箭头整体显示或隐藏 Query Card；不再增加独立 Parameters 按钮，也不把执行入口放进可能被隐藏的 Card。Query Parameters 是 Workbench 正常文档流中的内联 Query Card，而不是浮层或 Header 的附属白条：Card 首行只显示“查询参数”，不保留查询按钮，也不显示参数数量、说明口号、Run ID 或 Dataset 状态。字段区统一采用“业务标题在上、输入在下”的响应式网格。Server 首次进入时默认展开，之后按浏览器 tab 与 Dashboard 记忆；导出 HTML 默认折叠，沿用同一分段按钮几何，其中查询主按钮只表达已固化的查询结果、不可重新取数，箭头用于查看固定参数快照。Card 展开后占据正常文档流并把 Canvas 向下推，滚动时自然离开视口。Server 的 Shell 与隔离 Canvas iframe 组成一个阅读面：向下滚动时先消费外层尚未离开的 Query Card，再滚动 Canvas；向上时先回到 Canvas 顶部，再恢复 Query Card，不能把两者暴露成顺序相反的嵌套滚动区。Query Card 不属于 Overlay Runtime，点击外部或按 `Esc` 不改变状态；没有 Query Parameter 时不显示箭头与 Query Card，但查询和 Dashboard Controls 仍保持可用。Dashboard Controls 的临时托盘才由外部点击或 `Esc` 关闭；consumer mode 与影响 View 数量继续存在于 Runtime 契约和诊断信息中，但默认界面只展示业务字段标签与组件，不重复呈现 DATA/LOGIC、Selections/Calculation、作用域或影响计数。Pipeline 也不占用操作区：Compiler 生成的每个节点在 Dataviz 品牌右侧拥有一个状态灯，颜色表达状态，悬停/聚焦只显示任务名，点击进入该节点的 SQL、日志和运行证据；`Ready` 与 `Dataset query completed` 等重复文字不常驻界面。Query Card 使用容器自适应网格：`columns` 是 1–6 的最大列数，`column_width` 是 160–600 px 的目标轨道宽度（默认 280）。Runtime 用 Card body 宽度决定能放下几列，但参数较少时不会用 `1fr` 把少数控件强行拉满整行；轨道保持目标宽度并在右侧留下自然空白，窄屏才收敛为单列满宽。控件默认 `span: 1`，只有 Presentation 显式声明 `span: 2` 才跨列。Dashboard/Section/View Controls 默认单列；局部 Controls 只有显式选择 `grid` 时才并排，当前不继承 Query 的自动密度策略。过高内容在面板内部滚动。Dashboard 可在 `presentation.yaml` 的 `control_panels.query`、`control_panels.dashboard` 中调整布局，Section/View 可在各自 Presentation 条目的 `controls` 中调整局部托盘。Presentation 不得重写值、consumer binding、校验、tab 隔离或执行事件；Query 在导出 HTML 中只是固定快照，scoped Controls 保持交互。

原生 Shell 遵守“分析内容优先”：固定导航和 Header 使用低对比暖中性色，只让主操作、活动导航与语义状态获得强调；默认只生成必要的操作名、状态和错误，不用编号、口号、教学句或重复标题占据视觉中心。Dashboard 自己声明的 title、subtitle、description 属于业务内容，Runtime 不擅自删除；但框架说明应进入帮助、tooltip 或诊断面板，而不是永久铺在画布上。

首次 Query 前的 Canvas 是安静的空状态，不是 Hero、结果卡片或错误页：使用白色连续表面，只显示 Dashboard 标题和一句行动提示，不使用大面积品牌色、阴影、夸张字号或占满视口的居中构图。Warning、Error 与 Query Contract Outdated 才能获得高强调状态样式。

导出 HTML 的便携式 Header 保留紧凑 Dataviz Logo 作为报告来源标识，但不携带 Server 的 Sidebar、导航、Reload 或诊断操作；品牌标识属于 Presentation Shell，不由 Dashboard 自定义 Theme 接管。

## 8. 内容绑定

页面内容可以安全引用产生当前结果的已提交状态：

```text
{{ parameters.<id> }}
{{ controls.dashboard.<id> }}
{{ controls.section.<section-id>.<id> }}
{{ controls.view.<view-id>.<id> }}
```

- `parameters` 只在新 Query Run 提交后更新。
- Control 内容按目标 consumer 的 applied revision 更新；如果分支使用 `trigger: apply`，结果区域必须标记 stale，直到重新计算完成。
- 引用本身就是依赖声明；跨不可见作用域、未知 ID 和任意模板表达式由 `dataviz validate` 拒绝。

### 自动分析状态

Runtime 为每个 tab/Dashboard/Run 维护统一的 `dataviz/state-snapshot/v2`，其中 committed Query Parameter 同时包含 values 与 intents，并与 draft Query Parameter、Control current/applied state、consumer applied revision 和 stale 状态严格分开。该快照是 Revert、导出、调试、动态文案和可选状态摘要的底层证据，但默认画布不机械复述所有 Query/Control 值。

只有当上下文本身具有分析价值、且无法由简洁标题自然表达时，作者才在 Presentation 中显式启用状态摘要：

```text
仓 5740 · 商品 980464683 · 2026-08-18 至 2026-08-24
周四 · 18:00 及之后 · 3 个日期
```

启用后，Dashboard 可展示 Query Parameter 与 Dashboard Control，Section/View 可展示对应局部 Control。长多选使用数量摘要并可展开查看，不把全部值塞进标题。摘要只描述真正产生当前结果的已提交值；存在未应用草稿时单独显示“待应用”，不能提前替换 committed context。`区县 全部（7）`、`最低值 0` 这类低信息复述不应默认出现；重要上下文优先使用作者编写的动态标题、subtitle 或 description。

## 9. 渐进执行、局部失败与隔离

Query DAG 和 Interactive DAG 都按依赖闭包渐进执行。假设：

```text
source1 + source2 → dataset:features → view1
source3                             → view2
dataset:features + dashboard:sales-overview/seed (mode: value)
                  → interactive:simulation → view3
```

- `source3` 先完成时，`view2` 先展示，不等待无关分支。
- `simulation` 只在自己的 Base Output 和已提交交互状态就绪后执行。
- Interaction endpoint 归属于 Query Run，而不是 Query 的最终状态；一个 Base Output 发布后，其下游 `server-python` 可以立即计算，不必等待无关 Query 分支完成。
- Interactive 计算不会创建新的 Query Run，也不会修改 Base Named Output。
- 分支失败只影响该分支下游；执行队列的 `queued` 在 View 层映射为 `loading`，Component 统一展示 ready/loading/stale/empty/error/cancelled/unavailable 七种状态。
- 新 Query Run 通过 `run_id` 隔离；同一 Run 内的新交互计算使用独立 generation/interaction id，不能混用旧结果。
- Run 与 Interaction 的内存事件流都有保留上限；截断使用单调 `event_offset`，轮询/SSE 不会把截断后的数组下标误当成全局事件序号。
- 活动 Query 以及仍有活动 Interaction 消费的已完成 Query Run 都受保留策略保护；清理不能在长计算期间移除它们的 Artifact 或缓存。
- Query Run 会持久化所有已发布 Base Output，既用于浏览器传输、报告证据，也用于后续交互。`server-python` 所需引用另有显式分类，但不会复制第二份数据。
- Source/Dataset 节点缓存的逻辑键包含 Dashboard 和节点 ID，tab scope 再由不可逆 session namespace 隔离；`scope: workspace` 只允许显式选择的确定性内容缓存。
- Server Interactive 只能读取所属 Query Run 的 Artifact。即使 Source 很慢、已经不可用或凭证变化，也不得在交互路径回退为重新查询；需要新数据时只能明确创建新的 Query Run。

父页面和 Canvas 通过 `dashboard_id + run_id + frame_id` 握手。Query 最终完成时只同步 endpoint 状态，不重载 Canvas；已经挂载的 View、Control 和 Worker 状态因此不会被整页替换。Control delta 与 Output 发布都必须显式：某类状态未变化要表达为空集合，不能被解释成“全部变化”。一个无关 Output 在 Interactive Transform 运行期间发布，也不能仅因派生 Output 尚未产生而取消或重启该分支。

浏览器状态以 tab 为边界：

- Server 中每个 Dashboard 拥有可复制的正式路由 `/dashboards/{dashboard_id}`；Query String 只承载该 Dashboard 的 Query Parameter 草稿。路径和参数共同构成可分享入口，不能在无法定位 Dashboard 的 Workspace 根路径上悬挂孤立参数。
- Dashboard 切换写入浏览器历史，Query Parameter 编辑只替换当前历史项；刷新、前进/后退和新标签页打开同一链接时，都先按 URL 恢复 Dashboard 与参数，再建立 tab-local Run 和交互状态。Control、Run ID 与凭据不进入 URL。
- 同一 tab 可以记住当前 Dashboard 的 Query Parameter，以及 scoped Controls 的草稿/已提交值。
- 不同 tab、浏览器和用户不共享交互状态、Run 或运行证据。
- 一个 Dashboard 的查询或交互计算不会触发、中断另一个 Dashboard。
- `sessionStorage` 与 Browser Runtime 的 `none/session` cache 只允许 tab scope。
- Source、Dataset Transform 和 `server-python` Interactive Transform 默认也按 tab/session 隔离；Source/Dataset 缓存键同时包含 Dashboard 与节点 ID，只有显式的 `ttl/persistent + scope: workspace` 才能按内容哈希跨 tab 复用确定性结果。
- Workspace cache 只复用 Artifact，不共享草稿、Control、Run、generation、取消信号或运行证据。

### 开发态 Workspace Hot Reload

`dataviz serve` 默认监听 Workspace，但“文件变化”不等于“重新查询”。Server 将一批连续编辑合并为单调 revision，加载并验证完整新快照，再通过 SSE 把影响范围通知每个浏览器 tab：

| 变化 | 影响状态 | 行为 |
| --- | --- | --- |
| title、description、Section/View、Presentation、CSS/Canvas 资源 | `canvas` | 重载 Canvas，保留当前 Run、Controls 和滚动位置 |
| browser-js、server-python Interactive Transform 或其 Control Contract | `analysis` | 使用已有 Base Output 重建并重算受影响交互分支，不查询 Source |
| Query Parameter、Adapter、Source、Source 数据文件、Dataset Transform 或 Query 可达图 | `query` | 当前 Run 标记 `Outdated`；不自动执行查询，等待用户明确点击“查询” |
| Dashboard 目录新增、移除、改名或逻辑目录变化 | `navigation` | 更新目录；未影响当前 Dashboard 时不重载 Canvas |
| Workspace Runtime 或进程级配置 | `server` | 保留当前页面并明确提示重启，不伪装成已经热应用 |
| 新配置无法加载或出现新的静态错误 | `invalid` | 保持当前 iframe，不把半写入状态发布给页面，展示诊断并等待下一次有效 revision |

分类依据是已经解析的声明、依赖图和实际引用资产的语义签名，而不是简单地把 Dashboard 目录中的每个文件都视作页面依赖；编辑器临时文件不会无故重载 Canvas。活动 Query 始终持有启动时的不可变 Workspace 快照。若其运行期间 Query Contract 发生变化，该 Run 即使成功也只能作为历史证据，不能提交为当前结果。保存 Source 后立刻点击 Query 时，Server 会先同步尚在 debounce 窗口内的文件批次，并让 Run 返回它实际捕获的 Workspace revision。页面刷新或 tab 状态恢复时，Server 也会再次核验 Run 与当前 Query Contract，不能只依赖曾经收到过的浏览器事件。

监听只覆盖 Workspace。修改 Dataviz 自身的 Python Server 源码或安装新 package 仍需要重新安装并重启进程；Workspace Runtime 中启动时创建的并发额度也需要重启。`--no-watch` 只关闭主动通知，请求时重新读取与 Workspace update 提示中的显式 Reload 仍是兜底路径。

## 10. 数据执行与可审查性

每个 Source、Dataset Transform 和 Interactive Transform 都必须有稳定状态、耗时、缓存来源、输入指纹、错误和运行证据。

SQL Source 还要展示：

- 便于人 review 的 Resolved SQL；
- 实际执行的参数化 Driver statement；
- bound parameters、Adapter、SQL 文件、timeout/retry 和 query hash。

Resolved SQL 只用于解释；真实执行始终使用参数化 statement。默认 SQL 单次超时 120 秒，明确超时后立即额外重试一次；SQL Source 可以覆盖 timeout 与 retry。连接、权限和语法错误不盲目重试。

可复用 SQL Output 应在每个查询阶段显式列出输出字段，避免 `SELECT *` 和 `table.*`。显式投影使 Output Schema、脱敏边界、content hash、下游依赖和 Catalog 精确折叠不会因上游表偶然新增字段而漂移。`count(*)` 是聚合语义，不属于该限制。作者文档和 Scaffold 必须使用显式字段示例；Semantic Validation 对 public 或 reviewed/certified SQL Output 中可确定的通配投影给出稳定诊断，但不用脆弱的字符串匹配代替 SQL parser。

Dataset Transform 与 `server-python` Interactive Transform 都是可信单机 Python，使用独立子进程、timeout、traceback、依赖指纹、结构化日志、多输入和多 Named Output。当前产品不把 Workspace Python 当作不可信多租户沙箱，也不设计 CPU/内存配额。

## 11. View、Section 与 Component

### 默认模板

- View：Metric、Line、Bar、Stacked Bar、Pie、Scatter、Heatmap、Radar、普通 Table、Perspective、Markdown、Image、Custom。
- Section：Single、Stack、Grid、Split、Hero Metrics、Chart and Table、Comparison、Band、Small Multiples、Selection Gallery。
- Data Entry：Input、InputNumber、AutoComplete、Checkbox、Switch、Radio.Group、Select、Checkbox.Group、Cascader、TreeSelect、DatePicker、RangePicker、Slider。
- Query Parameter 与 scoped Control 共用这套组件；二者由生命周期与 consumer binding 保留差异，不由组件决定执行语义。

值语义、作用域与展示组件是三个正交维度。`dashboard.yaml` 拥有 type/default/required/clearable/options/suggestions/min/max/step/path_fields 等可验证逻辑；Control 的 Dashboard/Section/View 位置拥有作用域；`presentation.yaml.control_components` 只选择 UI 组件及 `span` 等视觉排版。Single Select 只渲染声明的真实选项，不合成 `All`、`Select all` 或 `Invert`，但 optional Single Select 可以显式 `clearable: true`，从一个值回到明确空状态。Checkbox Group 只用于 2–5 个少量并列多选：可清空时直接取消最后一项，必选时保留最后一项，不额外显示 All/Invert/Clear 工具栏。更大的平面多选使用 Select，层级多选使用 Cascader 或 TreeSelect。

DatePicker 与 RangePicker 不使用浏览器原生 `date` 外观作为产品界面，因为其日期格式、图标、日历语言和弹层样式会随浏览器漂移。两者统一显示并保存 `YYYY-MM-DD`：输入连续八位数字时按 `yyyy → mm → dd` 自动分段，例如 `20260809` 变为 `2026-08-09`；粘贴和直接编辑 ISO 文本走同一路径，真实日期、min/max 与范围顺序继续按值契约校验。日历按钮只负责打开同款 Dataviz 浮层，不取代文本输入；浮层标题以年、月下拉框支持直接跳转，左右箭头只用于相邻月微调。RangePicker 在一个连续边框内提供两个无独立边框的可编辑端点，宽屏显示相邻双月、窄屏收敛为单月；preset、键盘导航与范围边界属于同一个 Component Contract，没有 preset 时不保留空工具条，没有 Clear/Apply 动作时也不重复显示已在输入框中可见的日期范围。组件语义不决定网格宽度，因此 RangePicker 默认也只占一轨。

Table 是默认的数据表达组件，而不是缩减版分析工具。它应覆盖列选择与顺序、标题、格式、对齐、宽度、固定列、排序、筛选、分页、展开、选择、自定义 header/cell/footer、虚拟化接入和可访问性等表格表达能力。Perspective 只在产品明确需要赋予终端用户临时分组、聚合、透视和多维探索能力时使用；普通明细、排行、对账、分组展示或格式化输出不应因为 Table 能力不足而退到 Perspective。

Table 默认只呈现列头和数据行，不为 `N rows` 单独占据一条元信息行；作者确实需要显式行数证据时才启用 `options.show_count: true`。空数据仍使用统一 Empty 状态，不能把“0 rows”元信息误当成空状态替代品。

Table 当前使用 framework-agnostic `@tanstack/table-core` 作为 headless 行为内核，不继续自研排序、筛选、列模型、分页、选择和扩展状态机。Dataviz 仍拥有默认语义 DOM、Theme、紧凑样式、滚轮边界、View lifecycle、Control Binding 和 Export，因此引入 TanStack 不等于引入另一套视觉系统，也不要求 React。

作者能力按三层展开：声明式 `table` 使用 Dataviz 默认列模型与样式；`options` 选择需要的 Table feature 和列呈现；可信 Custom Renderer 通过 `context.tables.tanstack` 使用完整 Core、ColumnDef、Table instance、state 和 feature/plugin 能力，并可完全控制 markup 与 CSS。平台托管入口负责 mount/update/empty/restore/interaction/resize/dispose/export；直接底层调用保留全部 DIY 能力，但作者自行承担订阅、重绘、事件解绑和资源释放。TanStack Runtime 固定版本、本地打包，并由 Server 与 portable HTML 共用同一资产。

`options.mode=static` 的 `choices` 是封闭候选集合，而不是动态数据域的标签缓存。维度成员来自 Source 时必须使用 `options.mode=infer`，由 `options.source` 或消费 View 的 Base Output 推导；否则 Source 新增但未写入静态枚举的值会被有意排除。候选域来源与初始选择意图分开，避免 Dashboard 同时维护数据和一份易漂移的默认值/白名单。

组件边界、值形状、状态和交互语义逐项对齐 Ant Design Data Entry，但 Runtime 不引入 React/Ant 依赖，以保持 Server、单 HTML 与离线报告同构。Checkbox 表达随所在流程提交的 boolean，Switch 表达立即反馈的 boolean；AutoComplete 接受自由 string，suggestions 不是封闭枚举；Radio.Group 不再借用 Segmented 语义。Form 是 `control_panels` 的组合职责，不制造新的 value type。TimePicker、Transfer、ColorPicker、Mentions、Rate、Upload 只有在形成明确分析语义后才进入 DSL。完整矩阵见 [Data Entry Component 语义契约](docs/data-entry-components.md)。

Table 和 Perspective 是不同产品层级：Table 是默认表达层，Perspective 是显式分析工作台。只有需求包含“让看板使用者现场改变分析维度或聚合方式”时才选择 Perspective。Small Multiples/Selection Gallery 从共享 Named Output 和一个 View 蓝图生成实例，不复制查询或计算。

每个 Component 都有明确 owner Package；Package 是 headless controller、Runtime Adapter、功能 CSS、Story 和测试声明的唯一实现来源。浏览器主机源码按 Runtime Manifest、Value Contract、Named Output Store、Interactive Scheduler、Selection Binding、Renderer Lifecycle 与 bootstrap 分布在 `src/dataviz/server/runtime_src/`，不再以一个手写巨型文件承载全部职责。`tools/build_canvas_runtime.py` 按固定顺序确定性生成唯一对外资产 `server/static/canvas-runtime.js`；生成文件不得手工修改，回归必须执行构建器 `--check` 和 JavaScript 语法检查。Runtime 不再实现声明式 View、Repeat Section、Presentation 或 Data Frame/Interactive Adapter，也不保留已删除的 `declarative-runtime.js` 同功能副本。

Workspace 加载采用同样的物理 owner 边界。`workspace/loader.py` 只保留稳定公共 façade，现有调用方无需感知拆分；`workspace/loading/parse_load.py` 拥有 YAML/Schema 解析和 Dashboard 装载，`loaded_types.py` 拥有不可变加载快照，`catalog_navigation.py` 拥有 Workspace 目录、回收站与导航投影，`asset_validation.py` 拥有本地代码、依赖和浏览器资产检查，`contract_validation.py` 拥有跨文件语义契约。物理拆分不得改变错误 code、诊断顺序、字段路径或 CLI 文本。

核心 owner 的边界是：

| Package | 唯一拥有的行为 |
| --- | --- |
| `data.pipeline` | Frame/Grouped Frame、Named Output 数据 API、Selection-before-Compute 输入边界、两种 Interactive Runtime Adapter |
| `view.declarative` | View descriptor、内置 Renderer、Perspective/Table/Chart 生命周期与 View 状态边界 |
| `section.declarative` | Section 编排、Repeat/Selection Gallery、懒挂载与 Section 聚合状态 |
| `presentation.shell` | Theme/Layout shell 与七状态语义、ARIA 映射 |
| `runtime.control` | canonical native value、共享事件、键盘与浮层桥接 |
| `control.*` | 每个 Data Entry Component 的唯一 controller、adapter、CSS、Story 与测试声明 |

Package 内的 `test.yaml` 是机器可读验收声明，不是测试执行器；`dataviz components check` 验证 Package 元数据、资产和声明，真实行为由 pytest 与浏览器 E2E 执行。当前 Registry v5.6.0 有 21 个 package-owned Package，其中 14 个是独立 `control.*` Data Entry Package，不存在 bridge implementation。

Gallery 是这些契约的可执行说明，而不是截图目录。Control、View、Section 各自拥有 ready/loading/stale/empty/error/cancelled/unavailable 七状态矩阵；Select 另外提供真实含 10、100、1,000 个原生 option 的 Story，验证搜索、自动虚拟化、键盘和有界可视 DOM。

公开浏览器边界是版本化 Runtime Manifest、Output Store 和稳定事件。Vanilla JS、Web Component 或未来 React/Vue Adapter 只能消费公开协议，不能依赖 Python Renderer 私有结构或默认 Runtime 内部函数。

自定义 Renderer 的作者接口保持最小：

```text
validate → mount → update → dispose
```

这四项是实现 hook，不等于完整产品行为。所有内置或托管 Renderer 必须由平台通过统一行为矩阵：

```text
mount → update → empty → restore → interaction → resize → dispose → export
```

`view.declarative` 宿主统一识别空数据、发布 Empty、释放旧实例并在数据恢复时重新 mount；Renderer/Chart Service 负责交互事件与 ResizeObserver；Export 必须加载同一 Runtime 和 Adapter，不能另写静态渲染分支。首屏 Python 生成的 Plotly/Perspective bootstrap 也必须注册到同一 View ID 状态表，不能绕过后续 update/dispose。命令式资源必须归属具体 Renderer 实例：Plotly View 必须 `purge`，Perspective 的 Worker、Table 与 Viewer 一同 mount/dispose，不能把资源隐藏成 Canvas 全局单例。异步 mount/update/dispose 必须在平台时限内进入 Ready、Fallback 或 Error，不能永久停在 Loading。矩阵至少同时覆盖 Plotly 与 Perspective 的 Server Canvas 和 portable HTML。

Custom Renderer 的目标默认路径不是直接调用全局图表对象，而是使用平台 Plotly Chart Service：

```javascript
await context.charts.plotly.mount(element, {data, layout, config})
```

Plotly 是唯一的作者图表接口，能力按需展开，但不能按层级削弱：

1. 内置 line/bar/stacked-bar/pie/scatter/heatmap/radar 把字段映射编译为 Plotly traces 与 layout；
2. 常见视觉覆盖使用 View `options.trace`、`options.layout` 与 `config`，不引入第二套图表语法；
3. 需要自定义 trace、函数、事件或命令式状态时，可信 Custom Renderer 可使用托管 Chart Service，也可直接访问页面内嵌的完整 Plotly.js API。

第三层拥有 Plotly.js 提供的完整开发能力；Dataviz 只约束数据来源、Control Action、View 生命周期、资源释放、页面滚轮和 Export，不建立需要持续追赶上游的封闭能力白名单。托管 Service 是默认入口，因为它自动继承平台策略；直接底层调用是受支持的完整能力逃生口，作者必须自行承担 Theme、Resize、Update、Purge、事件解绑和滚轮所有权。

Dataviz 固定并直接内置 Plotly.js 4.0.0，不安装或调用 Python `plotly`。Server 负责生成 canonical Named Output 与稳定的 View 字段映射；Browser Adapter 只把这些已计算数据投影为 Plotly `data`，并合并容器尺寸、主题、交互策略与作者覆盖，形成最终 `layout/config` 后调用 Plotly.js。该投影不得重新解释指标口径；之所以保留在浏览器，是为了让 Control、browser-js Derived Output 与 portable HTML 无需回到 Server 也能更新图表。Server 与 portable HTML 使用同一份经过完整性校验的浏览器资产，因此不存在 Python wrapper 与浏览器版本漂移。视觉选型优先参考 [Plotly JavaScript 官方文档](https://plotly.com/javascript/) 与 [Chart Studio Gallery](https://plotly.com/graphing-libraries/)，Dataviz Recipe 只保存少量经过接入和回归验证的起步代码，不抓取、复制或替代官方资料。AI 应先明确分析问题，再将选定的 traces、layout、数据映射和交互接入 Named Output、Controls 与 Renderer 生命周期。

官方示例是参考输入，不是可直接执行的 Dataviz Contract。适配器必须替换示例中的独立 DOM、内联数据与事件宿主，声明需要的本地/网络资产，并把实例创建、事件、Resize 和 Purge 交回 Renderer 生命周期。只有完成这些适配并通过 `validate → report → visual-check` 的代码，才可成为 Dataviz Recipe。

作者契约只有 Plotly：View 不填写 `engine`，Scaffold、Gallery、Recipe、focused docs 和 Component contract 不暴露图表包分支。

Service 与内置 View Adapter 共用 Theme、responsive、page-first wheel、resize、update、dispose、错误状态和 HTML Export 策略。直接访问底层库仍是显式逃生口，但不会自动继承平台默认值；Scaffold、Gallery 和 AI 文档优先生成 Plotly Service 调用。`view.declarative` Package manifest 声明 `service.charts` 能力，Semantic Validation 可据最终 Renderer 配置判断属性是否生效。

Server 页面与导出 HTML 必须使用同一组件实现。

## 12. Server、CLI、HTML 与 AI

- **Server** 面向人：提交 Query Parameter、操作 scoped Controls、运行 Interactive Transform、查看 Source/Transform 证据。
- **CLI** 面向 AI/自动化：validate、inspect、catalog、run、result、report、docs、schemas、components、scaffold 和 benchmark。
- **HTML** 是一次 Query Run 的可移植快照：Query Parameter 固定；Browser Interactive Transform 可以继续执行；Server Interactive Transform 只能保留 snapshot 或 unavailable。

AI 新建任务先调用 `dataviz docs --task minimal|interactive|custom-renderer --format json`；已知目标 Component 时可调用 `dataviz docs --component <id> --format json` 自动路由。修改既有看板时再使用 `dataviz inspect context WORKSPACE DASHBOARD --focus <kind:id>` 获取目标组件的真实依赖闭包。前者控制“这类任务应阅读哪些概念”，后者控制“这个具体实例应读取哪些文件和依赖”，两者不能互相替代。

`run` 采用 Result-centric 交互：默认 stdout 是高密度纯文本，包含状态、Result ID/路径、目标闭包、每个最终表格 Output 的 head 10 和下一步命令；只有显式 `--format json` 才返回机器 envelope。完整 Node、Artifact、Resolved SQL、bindings、provenance 和 diagnostics 由 `result inspect` 的渐进详情提供。精简不能删除失败所需的稳定错误 code 和下一步建议，也不能让文本/JSON 或 summary/full 使用两套执行逻辑。

目标布局与视觉检查分为两层：

1. `dataviz inspect layout WORKSPACE DASHBOARD --format json` 只读取编译后的 Layout Contract，输出 Section/View 行列、span、默认来源、冲突和 `mode: declarative|custom`，不启动浏览器；
2. `dataviz visual-check WORKSPACE DASHBOARD` 使用真实浏览器和固定 viewport 检查溢出、重叠、零尺寸、弹层裁切、稳定后永久 Loading、Perspective 容器高度、Console error 等客观事实，并可输出 Screenshot 与机器可读 geometry report。

`visual-check` 不声称判断配色、信息层级、业务图表选择或“是否好看”。自定义 Canvas 的任意 CSS 无法由静态 Contract 完整解释，必须走浏览器检查；视觉模型或人工审阅仍是主观质量的最终证据。

AI 的默认工作应该是选择模板、绑定 Output、填写状态依赖和业务表达式，而不是每次生成整页前端代码。安装包必须提供严格 Schema、静态 validate、机器可读 docs/components/inspect、Scaffold、Gallery 和稳定错误码。Authoring 成对评测与真实 Token/会话日志属于仓库维护工具，不进入正式安装包。

`validate` 不执行查询或计算；静态通过后，再按 Source、Base Output、Interactive Output、View 的顺序动态验证。框架是否节省 Token 必须通过相同任务与完整 HTML 对照，不能由模板数量自行推断。仓库内独立的 `tools/authoring-evaluation/` 维护固定任务、严格的 `authoring-event/v3` 日志和 identity/quality-gated 成对比较；它不属于产品 CLI。Trial 会固定任务契约与输入 SHA-256；每条验收条件必须记录 human/automation/mixed assessor 和证据，只有两种方案均保持输入完整并通过全部验收时才进入聚合。在积累真实重复 trial 前，不发布节省比例。

## 13. AI Analysis Plane

Dashboard 不只是给浏览器渲染的一张页面，也是一份可执行、可搜索的数据分析定义。AI 不应先识别图像像素或反向解析 Renderer 才能理解看板；平台应直接向 AI 暴露看板已经声明的数据口径、分析口径、依赖闭包和结构化结果。

Analysis Plane 与 Server 页面共用同一 Compiler、Dependency Contract、Executor、Interaction Runtime 和 Named Output Store。它是现有执行面的机器可读投影，不是第二套 DAG、第二套计算框架或绕开权限边界的查询入口。

Analysis Plane 已闭合发现、试验和人工晋升两个循环：

```text
正式 Named Output → Catalog 发现 → Target + 可选 Overlay → run → 不可变 Result
不可变 Result → Evidence → 人审阅 → Promote dry-run/补丁 → 正式 Output / 测试 / caveat → Catalog
```

前者是“可执行分析资产”的复用闭环；后者把审阅后的试验沉淀为普通 Workspace/Git 变更。Promote 已实现预览、校验和补丁生成，但故意不自动 apply 或 certified。Catalog 不能因为对象可搜索、可执行，就默认它具有可信的业务语义。

### 13.1 三层可分析对象

| 层级 | 稳定对象 | 含义 | AI 默认消费方式 |
| --- | --- | --- | --- |
| 取数口径 | Base Named Output | Query Parameter → Adapter → Source → 可选 Dataset Transform 的结果 | 结构化表、Schema、语义、参数闭包与 provenance |
| 分析口径 | Derived Named Output | Base Named Output + resolved Controls → Interactive Transform 的结果 | 结构化表、有效 Control、Runtime 与 lineage |
| 呈现口径 | View | Named Output 到 title、x/y、series、columns、aggregation 等视觉编码的映射 | View spec 与输入引用；Screenshot 只用于视觉 QA |

Source 是取数节点和 lineage 起点，不是最终复用单位。Catalog 以 Named Output 为主记录；没有 Dataset Transform 时，Source Output 自然就是 Base Named Output。所有 Base Named Output 都应可独立检查和导出为表。Derived Named Output 也应保持数据结果，不把 Plotly View、Perspective 或 DOM 实例当作分析结果。

View 图像适合人快速识别模式，但 AI 通常更适合读取结构化 Output 与 View mapping。只有判断布局、裁切、视觉层级或图形是否误导时，才启动浏览器并读取 Screenshot/geometry；不能把视觉识别作为数据分析的必经路径。

### 13.2 Output 语义、可见性与可信度

AI 作者在定义可复用 Output 时，应同时记录它为什么存在，而不仅是技术名称。Dashboard schema 在每个 Base/Derived Named Output 附近提供 Output 级 `semantics` 契约；不再用 Dashboard 级 grain 代替不同 Output 的行粒度。当前最小契约为：

```yaml
semantics:
  visibility: public
  title: 区域收入明细
  purpose: 按区域和统计周期提供收入、订单和客户规模，供经营分析复用。
  grain: 每个区域、每个统计周期一行
  caveats: [退款在次日批处理后回写]
  assurance:
    status: reviewed
    owner: finance-analytics
    reviewed_at: 2026-08-28
    evidence: [evidence/revenue-contract.md]
  time: {field: period, timezone: Asia/Shanghai, meaning: 自然月}
  measures:
    revenue: {unit: CNY, aggregation: sum}
  relationships:
    - {fields: [region_id], cardinality: many-to-one, target: dim_region}
```

`visibility: public | internal` 只决定默认可发现性，不代表可信度。显式 public Output 必须提供非空 `title`、`purpose` 和 `grain`；internal Output 仍保留 lineage，并可按精确引用或 `--include-internal` 检查。`assurance.status: draft | reviewed | certified | deprecated` 独立表达可信度：reviewed/certified 必须记录 owner、reviewed_at 和 Dashboard 内可定位 evidence；deprecated 必须给出 reason 或 replacement。默认可信发现只返回 reviewed/certified，维护者可用 `--include-untrusted` 审计 draft/deprecated。`purpose` 是 Catalog 搜索和 AI 选数的首要证据；`grain` 用于防止错误 join 或重复聚合；`caveats` 记录数据延迟、过滤边界和已知限制。字段 Schema 仍由现有 Output Contract 管理。存量未声明 semantics 的 Output 保持可执行并给出稳定迁移 advice；Scaffold 和新示例直接生成显式 semantics。

P1 不强制 tag，也不建立全局 tag 词典。时间字段/时区/口径、指标单位/聚合语义和关联字段/cardinality 是可选结构，只在 Output 确实包含这些概念时声明，不让最小作者路径填写空表单。

Catalog 每个 Base/Derived Named Output 至少投影：

- Dashboard ID、Output 引用、Base/Derived 阶段与人类语义；
- 编译得到的 Query Parameter 最小闭包、上游 Source/Dataset/Interactive lineage；
- Source 类型、Adapter/Auth 引用，但绝不写入凭据；
- Output kind、Schema、grain、下游 View 与 Derived Output；
- Output 的 visibility、title、purpose、grain 与 caveats；
- Derived Runtime：`server-python | browser-js`；
- Workspace 相对的定义与代码路径，避免绝对路径泄露和无谓 Token；
- 定义指纹、Catalog generation 与更新时间。

Catalog 不生成第二套短别名。所有命令、机器结果和 `next_actions` 都复用 `dataviz/target-reference/v1` 的规范物理引用，例如 `chart-gallery::source:metrics/main`、`sales::dataset:monthly/revenue` 或 `sales::view:overview`。引用由 Dashboard ID、节点种类、稳定节点 ID 和可选 Output 名组成；修改 SQL、Python 或语义说明不会改变引用，重命名物理对象则明确改变引用。定义版本、缓存失效和执行证据继续使用独立 `definition_hash`，不能让引用承担版本号职责。

Dashboard YAML 只声明作者无法可靠推导的语义。参数闭包、lineage、代码路径、下游 View 等都由 Compiler 和 Dependency Contract 计算，不能要求作者重复维护。

搜索覆盖 title、purpose、Dashboard/Source/Output 名称、Query Parameter、字段、类型、相对路径、Adapter 和下游 View；默认支持不区分大小写、类似 grep 的正则表达式，例如 `收入|工资|年入|月入`，避免单一关键词召回不足。`--literal` 用于按原文搜索包含正则符号的内容；无效或过长正则返回稳定诊断。同时保留 `--dashboard`、`--kind`、`--source-type`、`--parameter` 等确定性过滤，并先过滤再匹配文本。搜索结果必须返回稳定引用，供后续 `describe` 和 `run` 直接消费。

`catalog list/search` 共用一份语义密集的默认文本 renderer，区别只在于 search 额外显示命中原因。每条结果以 title/purpose/grain/assurance 为主，物理 reference、kind 和 Dashboard 退居次级；同时紧凑显示 Query Parameter 的 ID、类型、required/default、候选模式/数量/依赖，Output kind/字段数、最短执行闭包、相关 View 和精确折叠 occurrence count。默认不展开完整候选池、Schema、SQL、代码或所有 occurrence。Source 和 View 默认附着在主要 Base/Derived Output 下作为 lineage/consumer，不与可复用 Output 平铺竞争；只有显式 `--kind source|view` 才独立列出。

默认文本的视觉层级参考如下；它是确定性文本契约，不要求终端图布局库：

```text
城市季度经营指标
  比较城市季度收入、订单与客户表现。
  Grain: 每行一个城市季度 · Certified · 10 rows / 6 fields
  Inputs: 无 Query Parameter
  Used by: 城市收入排行、订单与收入关系、季度收入轨迹
  Ref: chart-gallery::source:metrics/main · Base Output
  Match: purpose「收入」
```

无值的行直接省略，不输出 `none`、空数组或冗长 JSON 占位。`Ref` 必须能整行复制给 `describe` 或 `run`；相同信息在 text/JSON 中来自同一 summary model，不能维护两套独立拼接逻辑。

搜索默认是低 Token 概览，不承诺解决语义等价性。Catalog 为每个定义和代码资产保留 content hash；在文本匹配和结构化过滤之后，只对“实现资产 hash、Source/Runtime、Adapter 逻辑引用、Query bindings 与 Output Contract 完全一致”的 occurrence 做精确折叠。折叠结果返回一个稳定 representative、`occurrence_count` 和可按需展开的 canonical references；任何 hash 或契约差异都保留为独立结果。这是概览压缩，不是语义去重，也不会删除 Dashboard 文件中为了独立分享而保留的 SQL/代码副本。`top N` 在折叠后输出；排序策略尚未用真实数据验证前，继续使用稳定确定性顺序，不预设使用次数权重。

### 13.3 Catalog 一致性与并发

Catalog 是可重建的派生索引，不是事实来源。Workspace 内建议使用：

```text
.dataviz/catalog/
├── CURRENT.json
├── catalog.lock
└── generations/
    └── catalog-000001.sqlite
```

每个 Dashboard 的定义指纹由排序后的 Workspace 相对路径和文件 SHA-256 闭包组成，闭包包含 `dashboard.yaml`、被引用的 Source/Dataset/Interactive 定义及代码；大型业务数据文件的内容不进入定义指纹，因为 Catalog 描述的是口径定义，不承诺数据此刻是否变化。

重建遵循以下规则：

1. 写者获取跨进程独占锁，等待者拿锁后必须重新检查 freshness；读者继续读取 `CURRENT.json` 指向的不可变 generation，不获取写锁。
2. 只重新编译指纹发生变化的 Dashboard，并从新 generation 删除已经不存在的 Dashboard。
3. 在临时 generation 中完成构建和完整性校验，再原子切换 `CURRENT.json`；失败时旧 generation 始终可读，不能暴露半份索引。
4. 构建期间若定义文件再次变化，丢弃本次结果并基于稳定快照重试。
5. Generation 文件避免在 Windows 上替换仍被读者打开的 SQLite 文件；过期 generation 延迟清理。
6. CLI 在查询 Catalog 前惰性检查 freshness；Server 文件监听经 debounce 后异步刷新。两条路径共用同一 builder 和锁协议。

### 13.4 使用统计

使用统计是本地排序证据，不是 Dashboard 契约或 Catalog 事实。Workspace 使用独立的 `.dataviz/usage.sqlite`，只保存每类行为的累计次数和最后一次成功时间；删除该文件只会使统计归零，不影响执行、Catalog 或 Dashboard 可移植性。

表结构不把当前两种行为固化为专用列，而是保留可扩展的统计维度：

```sql
CREATE TABLE usage_stats (
    subject_kind TEXT NOT NULL,
    subject_ref TEXT NOT NULL,
    action_kind TEXT NOT NULL,
    actor_kind TEXT NOT NULL,
    use_count INTEGER NOT NULL DEFAULT 0,
    last_used_at TEXT NOT NULL,
    PRIMARY KEY (subject_kind, subject_ref, action_kind, actor_kind)
);
```

`subject_kind` 可在未来扩展 dashboard/output/view 等对象，`action_kind` 和 `actor_kind` 也是由应用层校验的稳定字符串，新行为只增加新行，不需要修改表结构。当前只写入两种成功行为：

| 触发点 | subject | action | actor | 更新 |
| --- | --- | --- | --- | --- |
| 人明确执行 Dashboard Query 并成功 | `dashboard` + Dashboard ID | `query_succeeded` | `human` | `use_count + 1`，记录完成时间 |
| AI 执行 `run TARGET` 并成功 | `output` + canonical Output reference | `run_succeeded` | `ai` | `use_count + 1`，记录完成时间 |

`catalog list/search/describe`、页面打开/刷新、失败、取消和其他行为当前都不记录。是否将它们加入、以及统计如何参与搜索排序，都等真实使用数据出现后再决定。

多线程/多进程不读取后在 Python 中执行 `count + 1`，而是使用单条 `INSERT ... ON CONFLICT DO UPDATE SET use_count = use_count + 1`原子更新，并将 `last_used_at` 取为已存值和新值中较晚者。每个进程创建自己的 SQLite connection，使用 WAL、有界 `busy_timeout` 和短事务；统计更新是 best-effort，最终失败只写 warning，绝不使已成功的人类 Query 或 CLI Run 变为失败。`usage.sqlite` 不进入 Dashboard/Catalog fingerprint，也不触发 Workspace hot reload。

### 13.5 Python CLI 分析协议

发现与执行入口保持短而稳定；一次执行封存不可变 Result，后续查看、解释和复制都消费该 Result，不重新运行 DAG：

```text
dataviz catalog list WORKSPACE [--kind base|derived|source|view|all]
dataviz catalog search WORKSPACE QUERY [filters...]
dataviz catalog describe WORKSPACE REFERENCE...
dataviz run WORKSPACE REFERENCE \
  [--query-param NAME=VALUE] [--control NAME=VALUE] \
  [--output NAME] [--runtime auto|server|browser] \
  [--also REFERENCE] [--overlay FILE|-] [--format text|json]
dataviz result show WORKSPACE RESULT_ID [OUTPUT] [--offset N] [--limit N]
dataviz result inspect WORKSPACE RESULT_ID [--format text|json]
dataviz result export WORKSPACE RESULT_ID OUTPUT --to PATH
dataviz evidence create WORKSPACE RESULT --question TEXT --conclusion TEXT
dataviz evidence promote WORKSPACE EVIDENCE PROPOSAL --dry-run
```

`REFERENCE` 只接受 `dataviz/target-reference/v1` 的 canonical 物理引用。`catalog list` 默认只返回 public Base 取数口径的 title、purpose、grain、Dashboard、参数和物理引用，不返回 SQL、bindings 或代码。典型 AI 流程是 `catalog search → catalog describe → run`。

`describe` 是 Run 前的只读 Invocation Contract，不展示或读取 Result。它一次接受一个或多个引用，只加载同一 Catalog generation，按输入顺序解析并对同一 canonical reference 去重；每项返回语义、参数闭包、参数类型/required/default、候选模式与数量、Control 摘要、Output 摘要、紧凑 DAG/lineage、代码位置和可复制 Run 命令。候选值默认不展开，显式参数详情才读取候选池。批量中单项解析失败不吞掉其他有效项；文本/JSON 都返回逐项状态，任一失败时最终退出码非零。`describe` 不执行 Source、候选查询或 Transform，也不创建 Result。

`run` 按 Target Reference 种类解释目标：Source 执行该 Source 的最小闭包并封存其全部声明 Output，或用 `--output` 选择一个；Base Output 直接封存该 Named Output；Derived Output 自动运行 Base 闭包和对应 Interactive Runtime；View 封存全部直接数据输入并附带呈现映射。

`run` 是唯一公开执行入口，提供最小依赖闭包、Runtime dispatch 和统一 Result 契约。它永远完整执行并保存最终 Artifact，默认只在终端预览每个最终表格 Output 的前 10 行；`--preview-rows` 只改变展示，不裁剪实际结果。

默认文本不倾倒未经加工的 JSON，也不一开始输出 Schema、definition hash、Catalog generation、完整 provenance 或 Node diagnostics。表格使用紧凑 Markdown/纯文本形式展示列名和 head 10；标量使用一行值。stdout 是 TTY 时可复用现有 Rich 依赖显示标题、状态和 Tree；非 TTY/AI 消费时输出无 ANSI、确定性、按拓扑排序的节点列表。真正的 DAG 可能包含共享依赖，不引入 NetworkX/Graphviz 或外部布局二进制：默认只列 `node <- dependencies`，TTY Tree 中重复节点使用引用标记而不伪装成另一棵执行树。Schema、参数、完整 DAG、lineage、hash、时序和 provenance 统一由 `result inspect` 渐进披露。

`result show` 从已封存 Artifact 分页读取一个 Output，不重新执行 Source/Transform；未指定 OUTPUT 时，单 Output 直接展示，多 Output 先列出可选规范物理引用并展示各直接最终 Output 的紧凑预览。`result export` 必须显式指定一个 Result 内 Output，只把其原生 Artifact 原样复制到 `--to`，不在 Arrow、Parquet、CSV 等格式之间转换，也不修改 Result manifest 或内部路径。View 有多个 Output 时重复执行 export 选择所需 Output，不设计“导出整个 View 文件夹”的特殊协议。格式转换若未来有真实需求，应是独立能力，不能重新塞回 `run` 或冒充 export。

执行必须复用现有 Runtime：

- Base Source/Dataset Output：由现有 Executor 只运行该 Output 的最小 Query DAG 闭包；
- `server-python` Derived Output：在不可变 Query Run 上调用现有 InteractionExecutor；
- `browser-js` Derived Output：启动无头浏览器，加载现有 Dataviz HTML/Browser Runtime，再从 Named Output Store 提取结果；不得在 Python 中重写 JavaScript 语义。

未显式传入 `--control` 时，使用契约解析后的默认 Control。CLI 不需要呈现 Control UI，但 provenance 必须保留最终 Control state 与 applied revision。浏览器执行应使用隔离临时 profile，默认限制非必要网络；只有依赖 CDN 等显式场景才允许 `--allow-network`。初版只执行本地可信 Workspace 代码，不把它描述为不可信代码沙箱。

Browser Runtime 冷启动成本需要实测而非承诺。实现应支持一次浏览器会话批量提取多个 Output、Server 侧复用受控 browser pool，并优先使用 Arrow 传输。Derived 缓存键至少包含 Base Artifact hash、resolved Control snapshot、Transform code hash 和 Runtime version。

### 13.6 稳定结果与 provenance

Analysis Plane 独立版本化机器契约：

- `dataviz/analysis-entry/v1`：Catalog 单条口径；
- `dataviz/analysis-catalog/v1`：搜索与列表结果；
- `dataviz/analysis-result/v1`：实际执行结果与证据。

执行结果至少记录 reference 与 definition hash、stage、runtime、Query Parameter、effective Controls、输入 Artifact/hash、输出 kind/schema/rows/hash、duration、lineage 和稳定错误 code。一次显式 `run` 进入终态后产生一个可寻址、完成后不可变的 Result；ready、partial、failed、cancelled 都可以封存，preflight 失败不创建 Result。Result ID 是后续 AI 分析的句柄，不只是日志编号。默认托管布局为：

```text
.dataviz/results/
├── index.sqlite
└── result_20260829_014230_1c1969f3/
    ├── manifest.json
    └── outputs/
        ├── source_metrics_main--HASH.parquet
        └── ...
```

执行先写 `.staging/<result-id>/`，完成并校验 manifest/Artifact hash 后再原子发布为最终目录；最终目录、manifest 和其中的平台托管 Artifact 不再修改。Result manifest 是事实来源，记录 Result 当时的 target、参数、Controls、执行闭包、Artifact 映射、原生格式、rows/hash、定义版本和 provenance；`index.sqlite` 只记录 `result_id → Result path`、状态、创建/最后访问时间和清理信息，删除后应能通过扫描托管 manifest 重建。`show/export/inspect` 只更新 SQLite 的访问时间，不能回写 Result 目录。Export 的外部副本不注册为新 Artifact，也不更新 Result 内部路径。

SQL、Dataset Transform、Server/Browser Interactive Transform 等本次执行新产生且没有其他稳定来源的数据，由 Result 以 Runtime 已经生成的原生 Artifact 格式托管，不为统一扩展名重复转码。File Source 的直接 Output 若原文件本身就是完整数据，不再复制一份到 `.dataviz`；manifest 保存只读读取收据：Workspace 相对路径、实际读取时间、size、content hash、reader/Output contract hash。Run 必须已经成功读取而不是只检查文件存在；以后 `result show/export` 再验证文件存在且 content hash 一致，变化或缺失时返回稳定 `analysis_result_source_changed|missing`，绝不静默读取新内容或重跑。选择“不复制原文件”意味着源文件变化后不能永久复现旧内容，这是显式边界；需要自包含快照时应由未来独立 snapshot 需求触发，不让默认 Run 复制所有大型输入文件。

Result 不在普通查询命令中机会式清理。`dataviz prune` 统一预览 Result、Execution Artifact 和缓存的清理候选，只有显式 `--apply` 才删除；读取租约保护并发消费者。Export 到 Workspace 外的副本以及被引用的原始 File Source永不由 prune 删除。

默认文本 summary 提供 Result ID/路径、目标、紧凑执行闭包、每个最终 Output 的总行数/head 10、耗时和下一步命令；显式 JSON、`result inspect` 的 debug/full 才展开 Schema、节点、代码路径、完整 provenance 和诊断。不同展示层只能改变证据量，不能改变执行逻辑或生成第二份 Result。JSON Schema、错误协议和 Result 生命周期是发布契约，不能只由 CLI 当前实现隐式决定。

为了支持审阅与后续沉淀，`dataviz/analysis-evidence/v1` 在一个 Result 之上记录问题/假设、结论或断言、结果 hash、来源 lineage、生成者、审阅者和审阅状态。Evidence 不复制整份大结果；它通过 hash 和可选小型 snapshot 使结论可核验，并明确标记原始数据已变化时的不可重现性。

### 13.7 临时分析覆盖层

AI 分析经常需要回答“如果这段 SQL、输入文件或计算逻辑换成另一版，结果会怎样”。复制完整 Dashboard 会制造无意义分支和过期副本，因此 Analysis Plane 支持只作用于一次 CLI Run 的 Overlay：

```yaml
schema: dataviz/analysis-overlay/v1
replacements:
  source:orders:
    code: ./experiments/orders.sql
  source:exchange-rates:
    path: ./fixtures/new-rates.csv
  dataset:customer-score:
    code: ./experiments/customer_score.py
  interactive:scenario:
    code: ./experiments/scenario.js
```

调用形式为 `dataviz run WORKSPACE TARGET --overlay experiment.yaml`；`--overlay -` 从 stdin 接收临时 JSON/YAML。Overlay 解析相对于自身文件位置的资产，构建不可变的 in-memory Analysis Variant，然后仍由原 Compiler、Dependency Contract 和 Runtime 执行。

第一版 Overlay 遵守“接口不变、实现可替换”：

- SQL Source 只替换 statement 文件；Adapter、query inputs、timeout 和 Named Outputs 不变；
- File Source 只替换同类数据文件，可显式确认 format，但必须通过原 Output Schema；
- Python Source、Dataset Transform 与三种 Interactive Transform 只替换代码和显式 code dependencies；Runtime、输入、Control/Query bindings 和 Named Output Contract 不变；
- 不允许修改 node/output ID、DAG 边、Adapter/Auth、Control scope 或 Named Output Contract；需要这些变化时应进入显式 Analysis Draft。

`dataviz catalog describe WORKSPACE TARGET --detail full` 返回目标闭包内所有定义/代码的 Workspace 相对路径、content hash，并在显式 `--include-code` 后返回已脱敏的文本内容；Adapter secret 和大型数据文件不能混入上下文。

Overlay 不写回 Dashboard，也不进入 Catalog。每次执行生成独立 Result ID；结果 provenance 记录原资产 hash、替代资产 hash、Overlay hash、调用参数、有效 Controls 和最终 lineage。Node/Derived cache namespace 必须包含 Overlay hash，不能污染或命中正式 Dashboard 的同名缓存。Overlay 的最终 manifest、原生 Output Artifact 和结果证据进入同一 `.dataviz/results/<result-id>/` 封存协议；替代 File 输入仍只记录经过实际读取的 path/hash 收据，不默认复制大型文件。

Overlay 仍执行本地可信代码，不是沙箱。Overlay 只解决“契约不变时替换实现”的 what-if；新增 DAG 节点、组合多个 Output 或改变 Output Schema 必须进入显式 Analysis Draft，不继续扩张 Overlay 使其变成另一套开发系统。

### 13.8 Analysis Evidence 与 Promote

`.dataviz/results/<result-id>/` 中的 manifest 是不可变运行证据，不自动成为组织知识。一次分析只有经过明确审阅和 Promote，才能产生以下一种或多种正式变更：

- 新的 Source / Dataset Transform / Interactive Transform 与 Named Output；
- 对现有 Output semantics、caveat 或 deprecation 的修订；
- 可重现的契约测试、数据断言或小型证据 snapshot；
- 引用 Result hash 和 lineage 的审阅记录。

Promote 不直接修改原 Dashboard，不自动把 Output 标成 certified，也不建立独立知识数据库。`evidence promote ... --dry-run` 只生成统一 diff，在排除 `.dataviz` 临时状态的 Workspace 副本中执行 Schema、Dependency 与 Semantic Validation，并返回稳定 diagnostics。

Analysis Draft 是普通 Workspace 定义的临时分支或生成补丁，继续使用现有 Schema、Compiler、Runtime 和 validate。它不需要另一套 Draft DAG、隐藏状态或网页开发器。

### 13.9 当前范围与顺序

Analysis Plane 当前完成 Workspace 内的本地分析资产闭环：

1. Output 级 semantics、public/internal visibility、独立 assurance 和按需的时间/指标/关系语义；
2. 稳定 JSON Schema、错误协议、summary/debug/full 与分层 provenance；
3. compact Evidence、人工 reviewed 状态和三类 Promote dry-run/validate/Git diff；
4. Arrow/Parquet 文件产物，以及 Base/server-python/Browser 多 Output 批量执行与提取。

Catalog generation、并发/失败回退与 Server 异步刷新是这些能力共用的已落地执行基础。Promote 故意不提供自动 apply 或自动 certified；正式资产变更仍要求人审阅 patch。

语义发现与 Result-centric CLI 已完成：`catalog describe` 支持多物理引用 Invocation Contract，`catalog list/search` 默认使用语义密集摘要；`run` 完整执行并封存不可变 Result，分页、检查和原样复制分别由 `result show/inspect/export` 承担。

HTML 导出和现有分享链接继续作为人类消费看板的已有能力；当前不设计 HTML Analysis Capsule、HTML Output 提取或远程分享链接分析，也不为它们预埋 Manifest、执行协议或安全层。未来只在真实需求证明本地 Workspace 闭环不足时重新立项。

## 14. 当前实现边界

当前执行契约：

| 契约 | 版本 |
| --- | --- |
| Dashboard schema | `dataviz/dashboard/v11` |
| Presentation schema | `dataviz/presentation/v2` |
| Source schema | `dataviz/source/v3` |
| Dashboard Dependency Contract | `dataviz/dependency-contract/v7` |
| Dashboard Layout Contract | `dataviz/layout-contract/v1` |
| State Snapshot | `dataviz/state-snapshot/v2` |
| Browser Runtime Manifest/Event | `dataviz/runtime/v6` |
| Dataset Transform schema | `dataviz/dataset-transform/v3` |
| Interactive Transform schema | `dataviz/interactive-transform/v3` |
| Component Registry | `5.6.0` |

已经实现：

1. Query Parameter 与 scoped Controls 是两个一级入口；Control 统一保存 Input State，writer/consumer binding 与 trigger 决定提交周期和失效路径。
2. Query DAG 与 Interactive DAG 分离；Base Output 对一次 Query Run 不可变，Derived Output 由 generation 隔离；快分支可在无关 Query 分支仍运行时进入 Server/Browser Interactive 计算。
3. Dataset Transform 使用 `server-python`；Interactive Transform 支持 `server-python` 和 `browser-js`。
4. 两种 Interactive Runtime 只接收显式状态和 Named Output，不访问 View DOM；Interactive Runtime 不持有 Adapter。
5. Query 与 Interaction 都支持局部并发、分支失败隔离、timeout、cancel、progress、缓存证据和资源释放。
6. Python 节点支持 `context.log(message, level=..., **fields)`；实时事件和 `dataviz/execution-log/v1` Artifact 保留结构化日志及完整失败 traceback，并可通过 session 隔离 API 与 Sources 证据面板检查。
7. HTML Export 强制声明 `interactive`、`snapshot` 或 `unavailable`；Server Python 不伪造离线交互。
8. `validate`、`run`、`result`、`docs`、`schemas`、`components`、`inspect` 和 Scaffold 使用同一当前契约。
9. 同一 tab 的状态可恢复，不同 tab、Dashboard、用户、Query Run 与 Interaction generation 相互隔离；父页面/Canvas 消息还校验当前 frame identity。
10. 仓库维护工具 `dataviz-authoring-eval` 可以用固定任务、经过完整性校验的 approach prompt、输入完整性、逐项验收证据、真实客户端 Token、首次成功率、修正轮次和耗时对比 Dataviz 与 standalone HTML；它不进入正式产品包，缺失 Token 不做估算。
11. `runtime.control`、`data.pipeline`、`view.declarative`、`section.declarative`、`presentation.shell` 已完整迁入物理 owner Package；Runtime v6 通过公开 ready event 装配且 dispose 幂等。
12. Gallery 已覆盖四类组件的七状态矩阵，以及真实 10/100/1,000 选项 Select Story；Story 元数据、页面目标与 Chromium 行为测试使用同一 Package。
13. `control_inputs` 在 Server `ExecutionContext` 和 Browser Runtime 的公共输入边界统一投影；filter binding 先裁剪声明的表输入，value binding 再提供局部值。
14. 动态 Control option domain 从 Base Output 建立；首次运行先 hydration/reconciliation，再渲染与调度 Interactive 分支。`canvas-ready` 只在首次 canonical state 提交后发布，Browser Interactive 状态通过 frame identity 约束的事件同步到 Server `Pipeline` 面板。
15. Query、Interactive、Control、Output 与 View 的所有边由单一 Dependency Contract 编译；Planner、Server、Browser、Export、CLI 与 AI context 只消费其投影。Query/Interactive 节点只能读取声明的参数，Browser 注册与契约漂移会立即失败。
16. Control 的唯一状态是 `{value, revision, intent?}`；Component、Repeat、View、两种 Interactive Runtime、tab 恢复与 HTML Export 共用 resolver。`explicit + []` 是明确空集，`all_available` 随候选域变化。
17. View 可通过一条 `control_binding` 写现有 Control。Dependency Contract v7 编译唯一 writer 与普通 consumers；Plotly、Table 和 Custom Renderer 只通过类型化 Adapter Action 写 canonical state，并拒绝越界、第二 writer、旧 generation 与反向作用域依赖。
18. Layout Contract v1 是声明式页面结构的唯一编译结果；Dashboard 拥有顺序、模板、columns 与 span，Presentation v2 只拥有视觉。默认 Renderer、Server、HTML、AI context 与 validate 共用该契约，自定义 Canvas 只暴露稳定 mount points。
19. Semantic Validation 在最终 Layout/Dependency/Renderer 配置上输出稳定 error/warning/advice；`inspect layout` 公开编译后的行列与来源，不维护第二张布局图。
20. `state-snapshot/v2` 是当前分析状态的只读证据；默认画布不展示状态胶囊。作者显式启用后，Dashboard/Section/View 才展示 committed/applied 值，并把尚未应用的 Control revision 明确标成待应用。
21. browser-js 默认 `auto`，server-python 默认 `apply`；显式 trigger 仍优先。`run` 默认返回高密度 Result 摘要，调试证据通过 `result inspect` 的渐进详情获取。
22. Custom Renderer 通过 `context.charts.plotly` 复用平台 Theme、滚轮、Resize、Update 与 Dispose；`visual-check` 对 Server/Report 执行真实浏览器几何和永久 Loading 检查并保存截图。
23. AI Analysis Plane 提供可重建 Catalog、规范物理 Target Reference、语义密集 `catalog list/search`、批量 `catalog describe`、Result-centric `run`、`result list/show/inspect/export`、Base/Derived/View 调度、两种 Interactive Runtime 与本地 Analysis Overlay；它们复用现有 Dependency Contract 与 Runtime。

仍属于后续优化，而不是隐藏的兼容工作：

1. Arrow 已优化传输和浏览器 Interactive Transform 输入；通用 Control filter 与部分 Renderer 首次消费大表时仍可能物化 JavaScript 行对象。
2. 固定 10K/100K/1M Query → Arrow → browser-js → Renderer 基准已经记录进程树 RSS、页面耗时和三轮 dispose 回落；流式 groupBy 由该证据触发，而不是凭行数猜测优化。
3. Server 尚未提供通用服务端分页或按需 Record Batch。现有 1M 聚合链路不足以证明需要扩张 DSL，也不能外推为 1M 原始 Table/Perspective 安全；二者都必须由各自基准触发。
4. authoring 评测工具已实现，但尚未积累足够的重复真实 trial，不能声称固定 Token 节省比例。
5. Chromium/Firefox/WebKit 已覆盖 390×520 弹层几何、内部滚动、键盘、ARIA、外部关闭，以及 Perspective 重复 dispose/reload/wheel 恢复；新增组件必须继续进入同一矩阵。
6. 当前协调模型是单进程：`dataviz serve` 启动一个进程，Run、Navigation、Cache 与报告发布锁不提供跨进程互斥；多个进程不得同时写同一 Workspace/输出路径。Runtime 并发上限在启动时捕获，修改配置后需重启。
7. Server 不提供账号体系或 HTTP 鉴权，默认只绑定回环地址；非回环 `--host` 必须显式使用 `--allow-remote`，访问控制由可信网络或外部代理承担。`session_id` 是 tab 状态命名空间，不是身份认证。
8. Semantic Validation 只判断确定性 no-op 与保守启发式；它不会根据未知真实数据规模判定图表是否适合，也不会替代人工审美判断。
9. 可选分析状态摘要覆盖默认 Canvas；完整自定义 Canvas 即使启用摘要，也需要显式放置稳定的 state-summary mount，平台不会猜测任意 HTML 的标题区域。
10. visual-check 判断溢出、裁切、重叠、零尺寸、永久 Loading、Perspective 高度和 Console error，不判断配色、业务图表选择或叙事质量。
11. Analysis Plane 已完成 Output semantics/assurance、版本化机器 JSON Schema、稳定错误 envelope、generation Catalog、规范物理 Target Reference、完整执行 provenance、compact Evidence、三类 Promote dry-run、不可变 Result 和多 Runtime 批量 Output；Promote 不自动 apply/certified，正式知识仍以人审阅后的普通 Workspace/Git 变更为准。
12. HTML Analysis Capsule、HTML Output 提取和远程分享链接分析不在当前路线图中；现有 HTML 导出和分享链接仍只是人类消费看板的产品能力。

Component Registry 独立版本化，只在公共组件契约变化时升级，不跟随 Dashboard schema 机械改号。

## 15. 设计非目标

以下内容不属于当前产品方向：

- 不以中心 Server 数据库保存页面和多人编辑状态；Git/文件夹是协作边界。
- 不提供可编辑数据逻辑、依赖、布局和样式的通用网页开发器；Server 只保留默认值、静态候选项与同级顺序的受限人工调参面。
- 不提供 exclude、任意 Filter Group 或隐藏谓词状态；第一版 filter binding 只表达 include，并显式区分空值 `passthrough | match_none`。
- 不把 Query Parameter 与 Control 合并成无生命周期的全局参数袋，也不把 typed value、candidate intent、writer 和 consumer effect 混回一个字段；必须保留类型、作用域、binding mode、trigger 和 applied revision。
- 不支持任意 Filter Group 或一个 View 同时归属多个组。
- 不提供 Mosaic、Widget 坐标或拖拽画布协议。
- 不把凭证写进 Dashboard，也不让 Dataset/Interactive Transform 获得隐式 Adapter。
- 不为实验性字段、Schema 或 Runtime 保留 alias、自动迁移或双协议分支。
- 不要求普通 Dashboard 编写自定义 HTML/CSS/JS；完整 Canvas 只是最后逃生口。
- 不为 AI Analysis Plane 复制 Dependency Contract、Query Executor、InteractionExecutor 或 Browser Runtime。
- 不把 Renderer 像素识别当作 AI 获取分析数据的默认路径。

## 16. 演进规则

1. 先固定状态与执行语义，再实现 Runtime，最后扩展 UI 模板。
2. 阶段和执行位置必须正交；不能再以 Server/Browser 命名业务阶段。
3. 新 Runtime 必须输出相同 Named Output，并遵守相同局部失效、错误和 dispose 契约。
4. 新组件由真实 Dashboard 需求触发，不能因为某个 UI 库存在就照单全收。
5. Schema、Runtime protocol、Component Registry 和 Package 独立版本化。
6. 0.x 阶段不为未投入生产的旧设计保留兼容分支。
7. 文档声明必须能由当前 Schema、CLI、Runtime 或测试证明；尚未实现的目标必须明确标记。
8. Catalog 只能投影当前契约并可随时重建；它不能成为 Dashboard、依赖或权限的第二事实来源。
9. 不为当前目标预埋 HTML 分析提取、远程执行或另一套知识存储；未来能力由真实需求重新立项。

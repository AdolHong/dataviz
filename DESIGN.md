# Dataviz 设计

> 快速安装和当前可用命令见 [README](README.md)；后续工作见 [plan.md](plan.md)。安装版本真正接受的字段始终以 `dataviz schemas`、`dataviz docs` 和 `dataviz components` 为准。

本文记录已经落地并可由当前 Schema、CLI、Runtime 和测试证明的契约，以及明确标注的后续目标。当前严格契约是 `dataviz/dashboard/v8`、`dataviz/presentation/v2`、`dataviz/dependency-contract/v5`、`dataviz/layout-contract/v1`、`dataviz/state-snapshot/v1`、`dataviz/runtime/v5` 与 Component Registry `5.4.0`。统一 Selection State、Control Binding、Layout/Semantic Contract、自动分析状态、Runtime-aware trigger、Chart Service、Renderer 行为矩阵、inspect-layout 与 visual-check 已进入实现；当前代码不保留 Dashboard v6、Presentation v1、旧 `cascade`、Source/Transform v1、`query_params` 或旧 Selector 字段。

Dataviz 是一个 workspace-first、AI-friendly 的数据看板工具。看板是普通文件，能够被 Git 管理、复制和审查；Server 面向人提供交互页面，CLI 面向 AI 与自动化提供校验、查询和 HTML 导出。

项目长期只用两个维度衡量价值：

1. 模板和组件是否可靠、易懂、可扩展，能减少用户困惑与 AI 试错。
2. AI 开发新看板所需的输入上下文、输出代码和修正轮次是否更少。

第二项必须通过真实任务测量，不预设没有证据的 Token 目标。第一优先级始终是先把工具做得好用。

## 设计原则：复杂度必须下沉

Dataviz 可以支持复杂数据流，但不能要求普通作者理解 Runtime 内部实现。作者面对的稳定模型只有五件事：取数参数、数据节点、Controls、Views/Sections、布局；`presentation.yaml`、Transform 代码和 Custom Renderer 都是按需逃生口。Dependency Contract、拓扑排序、状态事务、revision、缓存和 Renderer 生命周期由 Compiler/Runtime 自动生成，不能变成 Dashboard 的手写负担。

| 作者想做的事 | 唯一默认路径 |
| --- | --- |
| 改变取数范围 | Query Parameter |
| 在已有数据中选择样本 | `kind: selection` Control |
| 改变查询后的计算逻辑 | `kind: compute` Control + Interactive Transform |
| 点击图/表联动其他 View | View event 写入一个既有 Selection Control |
| 编排 Section/View | `dashboard.yaml` 的语义模板与 span |
| 调整颜色、容器和局部样式 | 可选 `presentation.yaml` |

普通路径必须满足“一个需求、一种写法、一个状态 owner”。平台不会为 View 联动再创建隐藏 filter，不允许 View 直接调用另一个 View，也不会要求作者手写事件总线。只有字段映射、触发策略或视觉行为确实偏离默认值时才展开高级配置。若一个常见看板必须写回调、复制状态、理解 canonical key 或阅读 Runtime 源码才能完成，应把它视为框架缺口，而不是作者责任。

### AI 开发与人工调参的边界

AI/代码仍然拥有 Dashboard 的结构和逻辑：ID、类型、作用域、依赖、Adapter、Source/Transform、View、Section、布局、Presentation 与自定义资产只能通过文件开发并接受 `validate`。Server 只提供一个受限的人工调参面，不发展成第二套可视化开发器：

- 可编辑 Query Parameter、Dashboard Control、Section Control 和 View Control 的 `default`；
- 可编辑 `options.mode: static` 的候选项及候选项顺序；
- 可调整同一作用域内参数/Control 的陈列顺序；
- `options.mode: infer` 的候选项和默认值只读，因为它们由数据契约决定；
- 不允许新增/删除参数，不允许修改 ID、type、kind、required、作用域、`depends_on`、输入绑定、布局或样式。

编辑器直接对当前 Dashboard 的 `dashboard.yaml` 做保留注释与格式的 round-trip 更新，不创建数据库或第二份配置。保存使用 revision 乐观锁、进程内写锁、完整 Dashboard Schema 校验和原子替换；若 AI 或其他编辑器在弹窗打开后修改了文件，本次保存必须冲突失败，不能覆盖新内容。编辑器改变的是下一次初始化使用的默认配置，不得悄悄改写当前 tab 已经提交的 Query/Selection/Compute 状态。它只存在于 Server authoring surface，导出 HTML 永远是只读分析报告。

编辑入口复用现有操作对象，不向任何 Control Panel 添加常驻工具条：右键 Run 打开 Query Parameter 编辑，右键 Dashboard/Section/View Controls 触发器打开对应作用域编辑；左键仍只执行 Run 或开合 Controls。没有可编辑项时保留浏览器原生右键菜单。此入口属于熟练用户的低频 authoring 动作，不与高频分析操作争夺视觉注意力。

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

Control Component ──────────────→ scoped Controls（Dashboard / Section / View）
View user event ─→ Selection ───┘      ├─ kind: selection → 选择数据
                                      └─ kind: compute   → 改变计算逻辑

Base Named Output + resolved Controls
             ├─→ View Renderer → Presentation
             └─→ Interactive Transform（可选）
                   ├─ server-python
                   ├─ browser-python
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
- **Control**：Query 后唯一的交互状态入口；Control Component 和目标 View 的用户选择只是同一状态的不同 writer，由作用域和 `kind` 定义可见范围与数据/计算语义。
- **Interactive Transform**：不重新取数，只根据 Base Output 与显式 Control 输入产生交互结果。
- **Derived Named Output**：Interactive Transform 的标准命名结果。
- **View Renderer**：把 Base/Derived Output 渲染为图、表、指标、文本或自定义组件。
- **Dashboard Composition**：拥有 Section/View 顺序、结构模板、列数和 span；删除 Presentation 后仍能确定完整阅读结构。
- **Presentation**：按稳定 ID 调整主题、容器外观、组件外观、Renderer 视觉参数和局部样式，不拥有结构布局或分析语义。

“Dataset”不是额外的隐式对象。表格 Dataset 是一种 Named Output；所有节点必须通过显式 Output 引用连接，Runtime 不暗中猜测数据来源或执行隐藏聚合。

### 单一 Dependency Contract

每次 Workspace 载入或热更新都会创建新的不可变 Dashboard 快照；每个快照只编译一次版本化的 `dataviz/dependency-contract/v5`。同一快照内的执行、交互和渲染层共享同一个契约对象，不能重复编译或各自解释 DSL。它包含：

- Query 节点的输入 alias、上游节点、Named Output、拓扑顺序、下游 View/option Control，以及每个节点允许读取的 Query Parameter；
- 每个 Query Parameter 的直接消费者和最终受影响 Query 节点、Interactive 分支、option Control、内容字段与 View；
- Interactive Transform 的 Base/Derived 输入、Query/Selection/Compute 输入 alias、Runtime、Named Output、直接/完整下游 View 和拓扑顺序；
- View 的有效输入、继承后的 Control、View-specific Selection binding，以及按拓扑排序的 Query/Interactive `pipeline_nodes`；
- Control 的作用域、显式直接父节点、传递祖先/后代、拓扑顺序、候选域 Base Output、直接数据 View、Interactive consumer、派生 View、内容绑定和最终影响上界；
- Named Output 到直接 View consumer 的反向索引，以及首次水合的固定顺序。

下面这些层只能消费或投影该契约，不能各自再推导一张“差不多”的图：

```text
Workspace validation
Query Planner / Interactive Planner
Server Pipeline / AI context / dependencies CLI
Canvas Runtime / HTML Export / Web Component Adapter
```

诊断 UI 也是该契约的只读投影，不维护第二份依赖图：Header 只显示 Source 与 Dataset Transform 的 Query 层状态；每个 View 的标题栏按拓扑序持有自身可达的 Query/Interactive 节点和最终 Renderer 状态。View 信号灯只在 `queued/loading/stale/error/cancelled/unavailable` 时出现，`not_run/ready/empty` 自动隐藏。这样正常阅读没有常驻技术噪音，分支卡住时又能直接定位到具体 Source、Interactive Transform 或 Renderer；导出 HTML 的 Query 节点已经固化为 Ready，因此只会短暂显示端侧计算和渲染状态。

Browser Runtime 注册 Transform 和 View 时会核对 data inputs、Control inputs、Query Parameter inputs 与 Output names；任何注册结果和编译契约不一致都会直接失败，不能静默运行另一张图。注册 payload 只承担 drift assertion，调度器、View 等待态和声明式 Renderer 实际读取的输入都来自 Dependency Contract，不会“校验契约后又执行原始配置”。浏览器不根据 DOM 或作用域层级猜测 Control 依赖，统一使用契约中的 `control_order`、`depends_on` 与 `dependency_ancestors`。

Selection Control 使用 `depends_on` 只声明直接父节点。引用采用相对 owner 的稳定前缀：`dashboard.<id>`、`section.<id>`、`view.<id>`。Dashboard 只能引用当前 Dashboard；Section 只能引用当前 Dashboard 或本 Section；View 只能引用当前 Dashboard、所在 Section 或自身 View，不能跨兄弟容器。Compiler 解析 canonical key、计算传递闭包和拓扑顺序，并拒绝未知引用、Compute 父节点、越界和完整环路径。Runtime 按拓扑顺序协调候选域并一次提交 canonical Selection 快照；链 `A depends_on B`、`B depends_on C` 只写两条直接边，A 自动拥有 B/C 两个有效祖先。Server 与 HTML 共用该事务，不允许组件各自实现另一套级联。

契约缓存使用并发安全的首次初始化。同一 load snapshot 即使同时收到多个 Planner、Server 或 Canvas 请求，也只编译一次并返回同一个对象；热更新才创建新的快照和契约。

契约必须“可执行才存在”。编译器会直接拒绝环、未知 Output、`server-python` 依赖浏览器 Runtime，以及 Interactive Transform 消费其下游 View 作用域之外的 Control。`validate` 在契约无法形成时可用容错扫描补充定位信息，但该扫描不是第二张运行时 DAG。

Query/Interactive Python 上下文只暴露节点显式声明的参数。仅仅因为某个值存在于 Dashboard 全局状态，不代表节点可以读取它；否则缓存指纹和依赖图都会失真。

Selection 的 `scope_views` 表示结构作用域，不等于每个 View 都一定含有可筛字段。契约进一步记录每个 View 的字段、operator 和输入 Output：Output Schema 已保证字段时标为 `declared`；表格 Schema 未保证时标为 `runtime`，在真实数据水合后检查；无表格输入时标为 `not_applicable`。因此 `affected_views` 是保守影响上界，实际重绘仍按当前 Output 的字段契约收窄，不伪造静态精度。

人和 AI 可以在运行前检查同一份图：

```bash
dataviz dependencies WORKSPACE DASHBOARD
dataviz dependencies WORKSPACE DASHBOARD --format json
```

## 2. 两个入口与两种 Control 语义

用户和 AI 只面对两个一级入口：

| 入口 | 声明位置 | 语义 | 修改后发生什么 | HTML 导出 |
| --- | --- | --- | --- | --- |
| Query Parameter | `dashboard.query_parameters` | 决定取什么数据 | 新建 Query Run，重新执行 Source/Dataset Transform | 固定为导出时已提交值 |
| Control | Dashboard/Section/View 的 `controls` | Query 后选择数据或改变计算 | 局部筛选、重绘或重算 Interactive Transform | 保持交互；能力取决于 Runtime/export mode |

Control 不是无类型参数袋。每一项必须显式声明 `kind: selection | compute`；统一入口只消除重复的 authoring/UI 结构，不抹掉两者在 Runtime 中的不同 delta、提交周期和失效语义。

View 点击、框选或表格行选择不是第三个一级入口，也不拥有独立状态；它只是修改既有 Selection Control 的另一种输入手势。因此 Header/Panel、View event、tab 恢复与 HTML Export 始终看到同一份 canonical Control state。

### Query Parameter

- 只在用户执行 **Run query** 后提交。
- Dashboard 保存 canonical 值；Source/Dataset/Interactive Transform 必须用 `query_inputs` 映射到节点本地 alias。
- 进入节点执行上下文和缓存键的是投影后的本地 `context.query_inputs`，未声明的全局参数不可读取。
- 修改草稿但没有重新查询时，页面仍展示上一次 Run 的已提交值和结果。

`query_inputs` 的 key 是节点本地名称，也是 SQL named placeholder 或 Python/Browser Context 的 key；value 是 canonical Query Parameter id。字符串是直接绑定的简写，结构化绑定可投影 `range_input/date`：

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
```

```sql
where warehouse_id = :warehouse_id
  and job_date between :start_date and :end_date
```

相对日期不是自由格式字符串。当前严格语法只接受 `anchor: today` 与整数日偏移 `offset: ±Nd/0d`。日期范围是两个独立 Date Atom 的有序对，每个端点可以是固定 ISO 日期，也可以是相对表达式，因此可以表达“固定开始日 + 相对结束日”。默认值编辑器也直接编辑这两个 Atom：每个端点只有“固定日期/相对今天”模式和一个随模式切换的值控件，不同时维护隐藏的 fixed/offset 副本，不使用 `start_offset/end_offset` 范围对象；固定模式复用运行界面的 ISO DatePicker 输入、日历与校验，相对模式使用整数 offset。`today` 按 `workspace.context.timezone` 求值，并在 tab 首次构建参数表单或 CLI Run 开始时解析为具体 ISO 日期。Query Run、缓存指纹、SQL 绑定和 HTML Export 保存的都是这个具体值；导出页不会在第二天重新解释“today”。Server 启动时不预计算，避免跨午夜后继续使用旧日期。

### Selection Control

`kind: selection` 只有 include 语义，不承担任意表单参数职责。三个固定作用域是：

```text
Dashboard Control → 所有绑定 View
Section Control   → 所属 Section 的绑定 View
View Control      → 单个 View
```

一个 View 的有效 Selection Control 由它可见的三个作用域合成，不支持任意 Group、多个归属或隐式同名联动。相同业务含义需要联动时使用同一个上游 Control；不需要联动时使用不同稳定 ID。

Selection 有两种不同的候选关系：

1. **Control DAG**：下游用 `depends_on` 显式声明直接上游 Selection；上游改变可用数据域后，Runtime 按编译拓扑立即重算下游候选并协调失效值。
2. **组件内路径级联**：一个 Selection Control 用 `path_fields` 表达省/市/区、组织/团队等完整路径，由 Cascader 或 Tree Select 展示父级上下文。

Selection 的有效状态不能只看 raw value，必须由 `intent + values + current option domain` 共同解析：`all_available` 表示包含当前全部候选并随候选域扩张；`explicit + values` 表示显式子集；`explicit + []` 表示不包含任何样本。交互上的“全选”进入 `all_available`，从而允许继续反选或取消少量项；清空进入 `explicit + []`；上游域变化后再做确定性 reconciliation。Control summary、内容绑定、普通 View、Repeat、三种 Interactive Runtime、tab 恢复和 HTML Export 必须消费同一个解析结果，不能分别从空数组猜测 All 或 None。

选择基数、是否必填与是否允许清空是三个正交契约，不能再把“单选”解释成“永远必须有一个值”：

| 类型 | `required` | `clearable` | 合法状态与交互 |
| --- | --- | --- | --- |
| `single_select` | `true` | 只能为 `false` | 始终恰好一个真实值 |
| `single_select` | `false` | `false` | 可以从空状态开始；选中后 UI 不提供 Clear |
| `single_select` | `false` | `true` | 可以从空状态开始、选择一个值，并再次 Clear 回明确空状态 |
| `multiple_select` | `true` | 只能为 `false` | 至少一个值，可提供不会产生空集的批量操作 |
| `multiple_select` | `false` | `true/false` | 允许或禁止用户主动进入明确空集；仍可独立使用 `all_available` |

单选的 Clear 是 `explicit + []`，不是 `All`、不是“未初始化”，也不是恢复默认值。单选不合成 `All`、`Select all` 或 `Invert`；`reset` 才恢复声明的初始状态。Query Parameter/Compute Control 的可空单选对外投影为 scalar 或 `null`，Selection Control 则仍由统一 resolver 保存明确空意图。`required: true` 与 `clearable: true` 在编译期冲突。Radio.Group 本身没有自然的清空手势，因此可清空单选默认使用 Select；作者显式要求 `radio-group + clearable: true` 时，Semantic Validation 必须报错，而不是静默丢掉 Clear。

Select 型 Selection 的“选项域”和“被筛选 View 数据”是两个不同契约：

- 封闭业务枚举使用 `options.mode: static` 并声明 `options.choices`。
- 数据维度使用 `options.mode: infer`；不得用 `default` 复制一份会随 Source 漂移的成员列表。
- `infer` 默认沿消费 View 的输入向上穿过 Interactive DAG，追溯到不可变 Base Named Output；多输入或需要消除歧义时使用 `options.source` 显式指定。
- `options.source` 只允许表格 Base Output，不允许 Interactive Output。后者可能依赖当前 Selection，会形成 `options → Selection → Interactive Transform → options` 的启动环。
- `infer` 多选的 `initial: auto` 编译为 `all_available` 意图；需要初始不选时使用 `initial: empty`，而不是列举具体默认值。

Runtime 的首次启动顺序固定为：

```text
hydrate Base Output → reconcile Selection option domains
→ commit canonical Controls → render Base Views → start reachable Interactive branches
```

因此一个无关或直接消费 Base Output 的 View 不会再因为另一个必填动态 Selection Control 尚未生成 DOM option 而停在 `Waiting for dataset`。渐进 Query 尚未发布 option domain 时保留已验证 canonical 值；Base Output 到达后再做确定性 reconciliation。

`canvas-ready` 是完成上述初始化后的生命周期事件，不是脚本加载通知。Server Shell 只有收到当前 dashboard/run/frame identity 的 ready 后，才把该 tab 记忆的 Control state 回灌 Canvas；Canvas 在初始化窗口内捕获到的用户输入先进入 canonical state，因此不会被迟到的默认值覆盖。

父页面与 Canvas 的双向同步遵守字段所有权，而不是互相发送可能过期的全量影子：首次握手允许父页面恢复完整 tab snapshot；之后 Header 只向 Canvas 发送它拥有的 Dashboard Control patch，Canvas 负责合并、按 `control_order` 协调 Section/View 候选域，再回传完整 canonical snapshot。消息携带 parent selection epoch，并同时校验 dashboard/run/frame identity。这样延迟到达的 Header 消息既不能覆盖 Canvas 刚提交的 Section/View 值，旧 Canvas 消息也不能恢复更新前的 Dashboard 值。

动态多选的 canonical value 与选择意图是两类状态。Runtime 用 `all_available` 表达“始终包含当前可用域”，用 `explicit` 表达“用户指定的有限集合”：上游收缩再扩张时，前者自动纳入重新可用的项，后者只保留有效交集且不会因暂时覆盖整个小域而被误判为全选。该意图由共享 Control Runtime 协调，并随 tab 恢复、Canvas 握手和 HTML 导出保存；Checkbox Group、Select、Cascader 与 Tree Select 不得各自实现不同的级联规则。

#### Control Binding / Linked Views

表格选中一行、图表点击一个点或框选一组点，本质上不是建立 `View A → View B` 回调，而是在读写一个已经声明的 Selection Control。Control 是唯一变量与状态 owner；普通 Control Component 和一个可选的 View Adapter 都只是它的交互入口，其他 View 与 Interactive Transform 只是 consumer：

```text
Control Component ─┐
                   ├─→ canonical Selection Control ─→ View / Interactive Transform
bound View event ──┘                  │
                                     └─→ bound View projection
```

这意味着 Control 不关心下游是散点、地图、表格行还是某个 cell，也不声明 `effect: highlight`。读写投影属于绑定它的 View Adapter：Plotly/ECharts 可以把 Control 值投影为 selected point，Table 可以投影为 selected row/cell，Custom Renderer 必须实现相同的类型化 Adapter Contract。上游只提供值、候选域、作用域和 Selection 语义，不了解 Renderer。

当前 author-facing DSL 只在 View 侧增加一条 `control_binding`：字符串用于目标字段与 Control 字段一致的常见情况，对象形式可显式写 `field`：

```yaml
sections:
  - id: stores
    controls:
      - id: province
        kind: selection
        type: single_select
        field: province
        options: {mode: infer, source: source:stores/main}
      - id: city
        kind: selection
        type: single_select
        field: city
        depends_on: [section.province]
        options: {mode: infer, source: source:stores/main}
      - id: selected_store
        kind: selection
        type: single_select
        field: store_id
        required: false
        clearable: true
        depends_on: [section.city]
        options:
          mode: infer
          source: source:stores/main
          initial: empty
    views:
      - id: store_map
        template: scatter
        input: source:stores/main
        control_binding:
          control: section.selected_store
```

标准 Adapter 默认从目标 Control 的 `field`/`path_fields` 读取事件 datum，并按 View 模板选择 point、row 或 selected item 投影；字段不一致、Table cell 或自定义图元才展开 Adapter 参数。Control 定义中不得出现 Renderer 名称、highlight/filter、row/cell 或事件回调。Presentation 可以把同一个 Section Control 的面板放到某个 View 附近，但不会改变它的语义作用域。

绑定基数刻意受限：一个 Selection Control 最多绑定一个可读写 View；标准 Control Component 仍可同时修改它，任意数量的其他 View/Transform 可以只读消费它。一个 View 可以读取所有可见的 Dashboard/Section/View Controls，但第一版最多拥有一个可读写 Selection Binding。需要两个图都能写同一变量、多目标 fan-out 或任意 callback 时，先用真实案例证明必要性，不能提前把 Runtime 变成事件总线。

Control 候选域只由它声明的 `depends_on` 祖先决定，计算时不应用它自身或后代 Selection。依赖作用域只能保持或收窄：

| Control 所在作用域 | 允许依赖 |
| --- | --- |
| Dashboard | 同 Dashboard Control |
| Section | Dashboard Control、同 Section Control |
| View | Dashboard Control、所属 Section Control、同 View Control |

同级链式依赖合法，例如 `A depends_on B`、`B depends_on C` 时只声明这两条直接边，由 Validator 检查未知引用、越界、重复边和环；更窄作用域永远不能反向决定更宽作用域 Control 的候选域。尤其当 View 绑定了 Section/Dashboard 的 `selected_store` 时，该 View 中任何会缩小门店候选域的 province/city Selection 也必须提升到同一或更宽作用域，并通过 `depends_on` 接入同一 Control DAG。第一版 Semantic Validation 直接拒绝“Section selected_store 绑定到 View，但该 View 又以 View Selection 缩小其可选门店”的结构；View 级 Compute/纯展示 Control 不改变候选域时仍然允许。

Bound View 的数据投影也必须避免自我收缩：它接收应用了目标 Control 祖先后的候选数据和目标 Control 当前值，由 Adapter 显示完整候选上下文并选中对应 point/row/cell；目标 Control 自身不先把 Bound View 裁成一行。其他 consumer 继续按普通 Selection include 语义筛选。因此 `selected_store = explicit + []` 时，地图仍展示当前省市下所有候选门店但没有高亮，而依赖 selected_store 的明细 View 显示空状态；选中 S001 后地图高亮 S001，明细 View 只分析 S001。

Dependency Contract 必须明确区分三类边：

1. `Control → Control`：候选域 `depends_on` 边，参与拓扑和环检查；
2. `View user event → Control`：一个真实用户事件 writer binding，不是自动执行边；
3. `Control → View/Transform`：普通只读 consumer 或 Bound View projection。

作者只声明 Control、直接 `depends_on` 和一条 View 侧 `control_binding`；Compiler 生成其余索引。程序化 selected point/row 更新、状态恢复和 Renderer 重绘绝不能重新发出用户事件，从根源上阻断 `View → Control → View` 反馈循环。所有 Control Component、Bound View event、tab restore 和 API 写入共用同一个原子事务：校验 action → 更新目标 Control → 按 `control_order` 协调下游候选域 → 提交 canonical snapshot → 计算一次 delta → 调度 consumer。若有效状态没有变化，不重绘；每个受影响 consumer 每次事务最多更新一次。

View event envelope 由 Adapter 携带 dashboard/run/frame/view/render generation；旧 frame、已 dispose View 或旧 generation 的事件直接拒绝。较早的 Browser/Server Interactive 结果若在新 revision 后完成也必须丢弃。Table、Plotly 与 ECharts Adapter 只把真实用户操作归一化为 `select`、`select_many` 或 `clear`；Custom Renderer 只通过类型化出口发送 datum，不得修改 Control DOM、调用另一个 View 或绕过 Dependency Contract。

以同一 Section 的 A/B 两个 View 为例：A 绑定 `section.selected_store`，B 只读消费它。用户在 A 点击门店 X 后，共享 Control 提交 X，A Adapter 选中 X，B 更新一次，Control 面板同步显示 X；随后用户在面板 Clear，Control 提交 `explicit + []`，A 清除 selected projection，B 进入空状态。不存在“图表状态”和“面板状态”谁覆盖谁，只有按 revision 排序的一份 canonical state。

Server 与交互 HTML 共用同一 Control reducer 和 View Binding Contract。若该 Selection 触发 `server-python` Interactive Transform，Server 仍遵循 Transform trigger；独立 HTML 服从既有 export capability，不能伪装缺失的 Server 重算。自动分析状态展示同一个 Control 值，避免 Bound View 产生不可见的隐藏筛选。

对 Interactive Transform，Selection 不是一个需要业务代码自行解释的普通参数。Transform 通过 `selection_inputs` 声明依赖后，Runtime 必须在进入三种 Interactive Runtime 前，对每个具有相应字段契约的表输入应用 include 筛选；不含该字段的无关输入保持不变。因此统一顺序是：

```text
Base/Derived Output → Selection 选择样本 → Compute 逻辑 → Derived Output → Renderer
```

`context.table(name)` / `context.input(name)` / 浏览器的 `context.inputs` 看到的是已选样本；`context.selections` 仍保留局部 alias 与已提交值，供日志、标签或确定性分支使用。Transform 不应再手写同一层数据筛选；若某个值只选择算法/模型而不选择数据，它应声明为 `kind: compute`。

### Compute Control

随机种子、模拟次数、算法、风险系数、优化约束等不筛选数据，统一声明为 `kind: compute` Control。它们与 Selection Control 使用相同的作用域和容器：

```yaml
controls:
  - id: region
    kind: selection
    type: multiple_select
    field: region

  - id: seed
    kind: compute
    label: 随机种子
    type: single_input
    value_type: integer
    default: 42

  - id: simulations
    kind: compute
    label: 模拟次数
    type: single_input
    value_type: integer
    default: 1000000
```

- Compute Control 不进入 Source 或 Dataset Transform。
- Interactive Transform 必须通过 `compute_inputs` 把局部 alias 映射到 canonical Control key。
- Compute Control 可以真实声明在 Dashboard、Section 或 View；作用域决定哪些 View 能依赖它，Presentation 只调整同一作用域控件的呈现。
- 多个 View 共享同一个 Interactive Output 时，不复制参数或计算。

### 草稿、提交与触发

Interactive Transform 支持：

- `trigger: auto`：控件变化后 debounce 并自动提交；新状态会取消或 supersede 旧计算。
- `trigger: apply`：控件变化先形成草稿，分支标记 stale，用户点击 Apply/Run analysis 后提交。
- `trigger: manual`：只由明确按钮或 CLI/API 调用。

目标默认值按 Runtime 决定：`browser-js` 与 `browser-python` 默认 `auto`，`server-python` 默认 `apply`；作者仍可显式覆盖。浏览器并不等于计算便宜，因此不得删除 `apply/manual`，也不得由静态校验猜测计算成本。当前 Interactive Transform v2 仍统一默认 `apply`，在 Runtime-aware 默认值进入 Schema、Dependency Contract、CLI 文档和测试前，以显式 `trigger` 为准。

直接 Selection Control 筛选仍即时生效；只有依赖该 Control 的重型 Interactive Transform 可以进入 stale 状态等待 Apply。页面标题、说明和运行证据引用的是产生当前结果的 **已提交值**，不能把未应用的草稿伪装成结果上下文。

## 3. 两种 Transform

阶段和执行位置是两个不同维度：Dataset/Interactive 描述业务生命周期，Server/Browser 描述 Runtime 位置。

### Dataset Transform

- 字段：`dataset_transforms`。
- standalone schema：`dataviz/dataset-transform/v2`。
- 执行位置固定为 Server Python。
- 由 Query Parameter 和上游 Named Output 决定。
- 适合多 Source 合并、数据清洗、特征构造、基础指标和一次 Run 内固定的复杂计算。
- 执行完成后产生 Base Named Output；任何 scoped Control 都不得触发它。

### Interactive Transform

- 字段：`interactive_transforms`。
- standalone schema：`dataviz/interactive-transform/v2`。
- 只消费已经确定的 Base/Derived Named Output。
- 可以显式消费已提交 Query Parameter 快照，以及 selection/compute Control。
- 不访问 Adapter、不重新查询 Source。
- 适合 Monte Carlo、模型推断、运筹优化、情景分析和交互聚合。

DSL 形态：

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
    compute_inputs:
      seed: dashboard:sales-overview/seed
      simulations: dashboard:sales-overview/simulations
    selection_inputs:
      region: dashboard:sales-overview/region
    trigger: apply
    export: {mode: snapshot}
    outputs:
      summary: {kind: table}
      distribution: {kind: table}
```

DSL 中的值是 canonical Control key，Transform 代码只看到作者显式选择的局部 alias。运行上下文继续把两类 delta 分开，以便调度器准确做局部失效：

```text
context.query_inputs
context.compute_params
context.selections
context.inputs
```

其中可读取的表输入已经按所声明的 `selection_inputs` 裁剪，之后才执行 `compute_inputs` 驱动的业务计算。浏览器 Runtime 直接从 `context.inputs` 读已选数据；Server Python 分析代码通过 `table()` 或 `input()` 读取，`context.inputs` / `context.artifact(name)` 中的 descriptor 只用于 provenance 与调试。

Interactive Transform 的上下文不提供 Adapter。即使运行在 Server，也不能因为实现位置方便而偷偷重新取数。

## 4. Interactive Runtime

Interactive Transform 有三种 Runtime，但共享同一个输入、Output、状态、错误和生命周期契约。

| Runtime | 主要用途 | Python 包能力 | 独立 HTML 重新计算 |
| --- | --- | --- | --- |
| `server-python` | 原生模型、运筹优化、大规模或专有 Python 计算 | 使用 Workspace Server 环境 | 不支持；只能 snapshot 或 unavailable |
| `browser-python` | 希望保留 Python 逻辑并让导出页继续交互 | Pyodide 支持的纯 Python/WASM 包 | 支持，但需要可用的 Pyodide Runtime 与锁定依赖 |
| `browser-js` | 筛选、聚合、轻量模拟和常规交互计算 | JavaScript/Web API | 支持，默认首选 |

当三种 Runtime 都能清楚、可靠地实现同一逻辑，且输入规模适合浏览器时，默认选择顺序是：

```text
browser-js → browser-python → server-python
```

这个顺序优先考虑启动开销、分发体积、离线交互能力和部署复杂度，不是“JavaScript 在所有算法上一定更快”的性能排名。原生 Python 依赖、大模型、运筹求解器、无法进入 Pyodide 的包或明显超出浏览器内存的数据，应直接使用 `server-python`，不要为了导出能力强行移植。

### server-python

- Server 根据 `run_id + Named Output reference` 读取当前 tab 的 Base Artifact，浏览器不重新上传整份 Dataset。
- Query 计划会显式分类所有被可达 `server-python` 分支消费的 Base Output；分类结果进入 Run 诊断，不能靠 Interactive 运行时临时猜测或重新取数。
- Artifact 的物理位置是 Workspace `.dataviz/runs/<run-id>/artifacts/`，不在 Dashboard 文件夹；逻辑所有权是 `tab session + dashboard + run + canonical output reference`。刷新同一 tab 可恢复，跨 tab 请求必须拒绝。
- 每次计算在独立 Python 进程执行，支持 timeout、cancel、traceback、progress 和结构化运行证据。
- 缓存键至少包含上游 Output content hash、代码/依赖、已提交 Query Parameter 与声明消费的 Control delta。
- 新交互只取消当前 Dashboard 的目标分支，不干扰其他 Dashboard、tab 或用户。

### browser-python

- 当前引擎确定为 Pyodide，但公开语义使用 `runtime: browser-python`，避免把业务 DSL 与某个加载器 API 绑死。
- 必须运行在 module Web Worker，不允许阻塞主线程或直接操作 DOM。
- Python 只负责计算并返回 Named Output；Plotly.js、ECharts、Perspective 和其他 Renderer 仍由 JavaScript 管理。
- 依赖必须显式锁定。纯 Python wheel 和 Pyodide 已构建的 WASM wheel 可以使用；普通原生 CPython wheel 不能假设可用。
- JS/Python 数据交换优先使用 Arrow、TypedArray 或受控结构化数据，避免把大表重复转换为百万个行对象。
- PyProxy、Worker、buffer 和临时 Python namespace 必须在 dispose 时释放。

Pyodide 有两种资产策略：

- `cdn`：报告较小，打开时从 `runtime.pyodide_index_url` 加载；适合有稳定外网或内部镜像的环境。
- `bundle`：从 Workspace 的 `runtime.pyodide_bundle_path` 复制经过 `validate` 检查的本地 Pyodide 分发；适合公司内网和离线分发。

`bundle` 当前导出为一个文件包，而不是把 WASM、标准库和 wheel base64 塞进单个 HTML：CLI 产生 `report.html`、`report.assets/pyodide/` 与 manifest，Server 下载 ZIP。解压后应通过 HTTP 静态服务打开，因为 module Worker/WASM 在 `file://` 下没有可靠的跨浏览器行为。它只打包 Pyodide：Plotly 由 Dataviz 内嵌，ECharts/Arrow 需要显式配置 Workspace 本地文件，Perspective 当前仍是 CDN-only。manifest 的 `portable_without_network` 只覆盖声明的 Runtime/View 资产；任意 Canvas/Presentation 脚本自行发起的请求不在静态证明范围内。

配置目录必须是版本匹配的官方完整分发根目录，至少直接包含 `pyodide.mjs`、`pyodide.asm.mjs`、`pyodide.asm.wasm`、`python_stdlib.zip`、`package.json` 与 `pyodide-lock.json`。`validate` 会核对 `package.json` 版本，在 Pyodide/Emscripten 目标环境中解析 dependency marker，沿 lockfile 检查 `micropip`、声明的 Python 包及其传递依赖 wheel，并要求每个所需文件都有匹配的 SHA-256；因此旧版本、只有 loader 文件或不可验证 wheel 的伪 bundle 都不会通过预检。

Pyodide 是按需能力。只有导出后仍需执行的 `browser-python` 分支才携带 Python Worker、Pyodide URL 或 bundle 资产；没有 `browser-python`，或者该分支已经是 `snapshot/unavailable` 时，不加载也不打包 Pyodide。

参考官方约束：[Web Worker](https://pyodide.org/en/stable/usage/webworker.html)、[加载 Python 包](https://pyodide.org/en/stable/usage/loading-packages.html)、[内置包列表](https://pyodide.org/en/stable/usage/packages-in-pyodide.html)、[中断执行](https://pyodide.org/en/stable/usage/keyboard-interrupts.html)。

### browser-js

- 运行在独立 Web Worker，不能访问 DOM。
- 继续作为开箱即用和导出 HTML 的默认 Interactive Runtime。
- 支持 Promise、timeout、supersede cancellation 和可序列化错误。

## 5. Named Output 与 Export Contract

Source、Dataset Transform 和三种 Interactive Transform 共用同一个 Named Output 协议。Renderer 不关心 Output 来自哪个 Runtime。

每个 Interactive Transform 必须声明导出模式：

```text
interactive  → 导出后仍可根据控件重新计算
snapshot     → 只导出当前已提交状态和结果
unavailable  → 导出页明确展示该分支不可用
```

约束：

- `browser-js`、`browser-python` 可以使用 `interactive`、`snapshot` 或 `unavailable`。
- `server-python` 的声明仍需给出离线意图，但只要 Dashboard 的可达 Interactive DAG 中存在 `server-python`，HTML Export 就整体不可用；Runtime 必须引导用户创建分享链接，不能把重型计算伪装成静态分支。
- 分享链接固定创建时的 Query Parameter 与 Base Output，不允许再次 Run；Browser JS/Pyodide 继续在浏览器执行，`server-python` Interactive Transform 通过 Dataviz Server 执行。这是分享链接相对 HTML Export 唯一增加的计算能力。
- `snapshot` 必须把影响结果的 selection/compute Controls 以只读上下文展示，不能留下能修改但不会重算的假控件。
- `unavailable` 必须显示原因和需要 Server 的能力，不能静默留白。
- `browser-python` 的“支持 HTML”不等于自动得到单文件报告；Pyodide、WASM 和 wheel 必须由明确的 `cdn` 或 `bundle` asset policy 提供。

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

Server 的 SHARE 菜单只保留“分享链接”和“导出 HTML”两个动作。分享链接为 `/shared/<share-id>`，每次创建都原子写入 `workspace/shared_caches/<dashboard>_<UTC timestamp>_<run>/`；目录保存 Query Result、选择/计算状态、清单和经过哈希验证的 Artifact，不污染 `dashboards/`。打开链接时 Server 为每个浏览器会话恢复一份不可变 Query Run：Query Parameter 只读且不能 Run，Browser Runtime 继续端侧交互，Server Python Interactive Transform 复用现有 Interaction endpoint。Server 重启后仍可从该目录恢复；v1 不自动过期、不随 Dashboard 修改或删除而清理，用户可以直接删除整个子目录。分享页仍依赖当前 Workspace 中兼容的 Dashboard/Transform 定义和正在运行的 Dataviz Server，不是离线文件，也不承诺跨不兼容代码变更继续运行。

Adapter 只有两个权威位置：提交到 Git 的 `auth/adapters.yaml` 保存非敏感定义，本地忽略的 `auth/adapters.local.yaml` 按同名键覆盖凭证。Runtime 不扫描根目录旧文件或 `*.example.yaml`，避免多个隐式来源造成覆盖顺序不确定。

## 7. 逻辑与呈现解耦

`dashboard.yaml` 是必需的逻辑文件，负责：

- 稳定 ID 和业务内容；
- Adapter、Query Parameter 与 scoped Controls；
- Source、Dataset Transform、Interactive Transform 与 Named Output；
- Dashboard、Section、View 的 Selection/Compute Control；
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

Compiler 为每个 Dashboard 快照生成唯一的 `dataviz/layout-contract/v1`。契约包含 Canvas mode、Section 顺序、模板、列数、View 顺序、最终 span、确定性行分配，以及每个值来自显式声明还是模板默认。默认 Renderer、Server、HTML Export、AI context、Validator 与 `inspect-layout` 消费该契约，不再从 CSS、Presentation 和 DOM 各自猜测布局。

模板提供结构默认值，不静默吞掉显式属性：`grid` 中显式 span 覆盖模板默认；`single` 必须恰好包含一个全宽 View，声明多个 View 或额外 span 属于确定性冲突；`split`、`comparison`、`chart-and-table` 等模板声明默认比例，并明确哪些结构属性允许覆盖。任意 View 的最终 span 和行位置都必须能由 `inspect-layout` 解释。

完整自定义 Canvas 是显式逃生口，Layout Contract 只记录 `mode: custom`、声明的挂载点和稳定 View/Section ID，不尝试静态解释任意 HTML/CSS。其真实几何将由浏览器 `visual-check` 检查。Dashboard v8 与 Presentation v2 已删除 Presentation 的全局 layout、Section template/columns 和 View span；旧结构字段直接校验失败。

### 最终配置的 Semantic Validation

Schema 合法不等于配置有效。Semantic Validation 必须在 Dashboard、Presentation、Component/Renderer manifest 和 Layout/Dependency Contract 全部编译后运行，至少区分：

- `error`：确定无法执行或结构矛盾，例如 `single` 包含多个 View、行占用超过列数、Renderer 不接受声明属性；
- `warning`：能够运行但确定是 no-op，例如 span 被模板忽略、Selection 没有任何 View/Transform/内容 consumer；
- `advice`：依赖经验而非确定事实，例如大型 Table 放入 band、可疑的 `min_height`、Browser Transform 使用 `apply`。

`--strict` 只把 `warning/error` 作为门禁，不能因主观 `advice` 失败。所有诊断必须有稳定 code、文件/字段、最终有效值、冲突来源和最小修复建议；Validator 不得维护第二套 Layout 或 Dependency 推导。

产品外壳与分析画布属于两层视觉所有权，但默认不制造两张彼此竞争的“大卡片”。Server 与导出 HTML Header、Sidebar 及 Workbench 使用连续近白表面；Sidebar 只用轻微表面色差、发丝线和近乎不可见的环境阴影确认导航边界，不形成悬浮卡片。靛蓝用于当前项、主操作和默认分析序列，绿色只表示 Ready/成功等语义状态。这些稳定 Shell token 不跟随 Dashboard Theme 染色，因此切换 `business`、`editorial` 或 `terminal` 时操作入口仍保持一致且退居背景。Dashboard 默认 Theme 是 `business`：白色画布、白色分析卡片、靛蓝分析强调、轻边框、极低阴影和紧凑数据表。Plotly、ECharts、普通 Table、Perspective 与 Data Entry Component 共同消费 Dashboard Theme token。`plain` 是更克制的中性版本，`editorial` 与 `terminal` 分别用于叙事报告和深色技术监控；Dashboard 可通过 token、`css_class` 和局部 CSS 覆盖画布视觉，但不得越界重写 Shell。

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

Server Header 是横跨整个 viewport 的唯一全局栏。左侧依次是可点击的 Dataviz Logo/品牌名和 Query 节点信号灯，右侧依次放 SHARE、Dashboard Controls，最右侧固定为“查询 + ▼”分段按钮；Sidebar 与 Workbench 从 Header 下方开始。Logo 本身拥有 Sidebar disclosure，不再增加独立 Navigation/折叠按钮，Sidebar 也不重复显示 “Dashboards” 标题。查询主按钮执行 Query，右侧箭头整体显示或隐藏 Query Card；不再增加独立 Parameters 按钮，也不把执行入口放进可能被隐藏的 Card。Query Parameters 是 Workbench 正常文档流中的内联 Query Card，而不是浮层或 Header 的附属白条：Card 首行只显示“查询参数”，不保留查询按钮，也不显示参数数量、说明口号、Run ID 或 Dataset 状态。字段区统一采用“业务标题在上、输入在下”的响应式网格。Server 首次进入时默认展开，之后按浏览器 tab 与 Dashboard 记忆；导出 HTML 默认折叠，沿用同一分段按钮几何，其中查询主按钮只表达已固化的查询结果、不可重新取数，箭头用于查看固定参数快照。Card 展开后占据正常文档流并把 Canvas 向下推，滚动时自然离开视口。Server 的 Shell 与隔离 Canvas iframe 组成一个阅读面：向下滚动时先消费外层尚未离开的 Query Card，再滚动 Canvas；向上时先回到 Canvas 顶部，再恢复 Query Card，不能把两者暴露成顺序相反的嵌套滚动区。Query Card 不属于 Overlay Runtime，点击外部或按 `Esc` 不改变状态；没有 Query Parameter 时不显示箭头与 Query Card，但查询和 Dashboard Controls 仍保持可用。Dashboard Controls 的临时托盘才由外部点击或 `Esc` 关闭；Selection/Compute 与影响 View 数量继续存在于 Runtime 契约和诊断信息中，但默认界面只展示业务字段标签与组件，不重复呈现 DATA/LOGIC、Selections/Calculation、作用域或影响计数。Pipeline 也不占用操作区：Compiler 生成的每个节点在 Dataviz 品牌右侧拥有一个状态灯，颜色表达状态，悬停/聚焦只显示任务名，点击进入该节点的 SQL、日志和运行证据；`Ready` 与 `Dataset query completed` 等重复文字不常驻界面。Query Card 使用容器自适应网格：`columns` 是 1–6 的最大列数，`column_width` 是 160–600 px 的目标轨道宽度（默认 280）。Runtime 用 Card body 宽度决定能放下几列，但参数较少时不会用 `1fr` 把少数控件强行拉满整行；轨道保持目标宽度并在右侧留下自然空白，窄屏才收敛为单列满宽。控件默认 `span: 1`，只有 Presentation 显式声明 `span: 2` 才跨列。Dashboard/Section/View Controls 默认单列；局部 Controls 只有显式选择 `grid` 时才并排，当前不继承 Query 的自动密度策略。过高内容在面板内部滚动。Dashboard 可在 `presentation.yaml` 的 `control_panels.query`、`control_panels.dashboard` 中调整布局，Section/View 可在各自 Presentation 条目的 `controls` 中调整局部托盘。Presentation 不得重写值、kind、校验、tab 隔离或执行事件；Query 在导出 HTML 中只是固定快照，scoped Controls 保持交互。

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
- Compute Control 内容只在对应 Interactive Transform 提交后更新。
- Selection Control 在浏览器内即时更新；如果重型分支使用 `trigger: apply`，结果区域必须标记 stale，直到重新计算完成。
- 引用本身就是依赖声明；跨不可见作用域、未知 ID 和任意模板表达式由 `dataviz validate` 拒绝。

### 自动分析状态

Runtime 为每个 tab/Dashboard/Run 维护统一的 `dataviz/state-snapshot/v1`，区分 committed Query Parameter、applied Selection、committed Compute、draft Compute 和 stale 状态。该快照是导出、调试、动态文案和可选状态摘要的底层证据，但默认画布不机械复述所有 Query/Control 值。

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
dataset:features + dashboard:sales-overview/seed (kind: compute)
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

父页面和 Canvas 通过 `dashboard_id + run_id + frame_id` 握手。Query 最终完成时只同步 endpoint 状态，不重载 Canvas；已经挂载的 View、Control 和 Worker 状态因此不会被整页替换。Selection delta、Compute delta 与 Output 发布都必须显式：某类状态未变化要表达为空集合，不能被解释成“全部变化”。一个无关 Output 在 Interactive Transform 运行期间发布，也不能仅因派生 Output 尚未产生而取消或重启该分支。

浏览器状态以 tab 为边界：

- Server 中每个 Dashboard 拥有可复制的正式路由 `/dashboards/{dashboard_id}`；Query String 只承载该 Dashboard 的 Query Parameter 草稿。路径和参数共同构成可分享入口，不能在无法定位 Dashboard 的 Workspace 根路径上悬挂孤立参数。
- Dashboard 切换写入浏览器历史，Query Parameter 编辑只替换当前历史项；刷新、前进/后退和新标签页打开同一链接时，都先按 URL 恢复 Dashboard 与参数，再建立 tab-local Run 和交互状态。Selection/Compute、Run ID 与凭据不进入 URL。
- 同一 tab 可以记住当前 Dashboard 的 Query Parameter，以及 scoped Controls 的草稿/已提交值。
- 不同 tab、浏览器和用户不共享交互状态、Run 或运行证据。
- 一个 Dashboard 的查询或交互计算不会触发、中断另一个 Dashboard。
- `sessionStorage` 与 Browser Runtime 的 `none/session` cache 只允许 tab scope。
- Source、Dataset Transform 和 `server-python` Interactive Transform 默认也按 tab/session 隔离；Source/Dataset 缓存键同时包含 Dashboard 与节点 ID，只有显式的 `ttl/persistent + scope: workspace` 才能按内容哈希跨 tab 复用确定性结果。
- Workspace cache 只复用 Artifact，不共享草稿、Selection、Run、generation、取消信号或运行证据。

### 开发态 Workspace Hot Reload

`dataviz serve` 默认监听 Workspace，但“文件变化”不等于“重新查询”。Server 将一批连续编辑合并为单调 revision，加载并验证完整新快照，再通过 SSE 把影响范围通知每个浏览器 tab：

| 变化 | 影响状态 | 行为 |
| --- | --- | --- |
| title、description、Section/View、Presentation、CSS/Canvas 资源 | `canvas` | 重载 Canvas，保留当前 Run、Controls 和滚动位置 |
| browser-js、browser-python、server-python Interactive Transform 或其 Control Contract | `analysis` | 使用已有 Base Output 重建并重算受影响交互分支，不查询 Source |
| Query Parameter、Adapter、Source、Source 数据文件、Dataset Transform 或 Query 可达图 | `query` | 当前 Run 标记 `Outdated`；不自动执行查询，等待用户明确 Run query |
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

Dataset Transform 与 `server-python` Interactive Transform 都是可信单机 Python，使用独立子进程、timeout、traceback、依赖指纹、结构化日志、多输入和多 Named Output。当前产品不把 Workspace Python 当作不可信多租户沙箱，也不设计 CPU/内存配额。

## 11. View、Section 与 Component

### 默认模板

- View：Metric、Line、Bar、Stacked Bar、Pie、Scatter、Heatmap、Radar、普通 Table、Perspective、Markdown、Image、Custom。
- Section：Single、Stack、Grid、Split、Hero Metrics、Chart and Table、Comparison、Band、Small Multiples、Selection Gallery。
- Data Entry：Input、InputNumber、AutoComplete、Checkbox、Switch、Radio.Group、Select、Checkbox.Group、Cascader、TreeSelect、DatePicker、RangePicker、Slider。
- Query Parameter、Selection Control 与 Compute Control 共用这套组件，但保留各自 delta、作用域、提交和执行语义。

值语义、作用域与展示组件是三个正交维度。`dashboard.yaml` 拥有 type/default/required/clearable/options/suggestions/min/max/step/path_fields 等可验证逻辑；Control 的 Dashboard/Section/View 位置拥有作用域；`presentation.yaml.control_components` 只选择 UI 组件及 `span` 等视觉排版。Single Select 只渲染声明的真实选项，不合成 `All`、`Select all` 或 `Invert`，但 optional Single Select 可以显式 `clearable: true`，从一个值回到明确空状态。Checkbox Group 只用于 2–5 个少量并列多选：可清空时直接取消最后一项，必选时保留最后一项，不额外显示 All/Invert/Clear 工具栏。更大的平面多选使用 Select，层级多选使用 Cascader 或 TreeSelect。

DatePicker 与 RangePicker 不使用浏览器原生 `date` 外观作为产品界面，因为其日期格式、图标、日历语言和弹层样式会随浏览器漂移。两者统一显示并保存 `YYYY-MM-DD`：输入连续八位数字时按 `yyyy → mm → dd` 自动分段，例如 `20260809` 变为 `2026-08-09`；粘贴和直接编辑 ISO 文本走同一路径，真实日期、min/max 与范围顺序继续按值契约校验。日历按钮只负责打开同款 Dataviz 浮层，不取代文本输入；浮层标题以年、月下拉框支持直接跳转，左右箭头只用于相邻月微调。RangePicker 在一个连续边框内提供两个无独立边框的可编辑端点，宽屏显示相邻双月、窄屏收敛为单月；preset、键盘导航与范围边界属于同一个 Component Contract，没有 preset 时不保留空工具条，没有 Clear/Apply 动作时也不重复显示已在输入框中可见的日期范围。组件语义不决定网格宽度，因此 RangePicker 默认也只占一轨。

Table 默认只呈现列头和数据行，不为 `N rows` 单独占据一条元信息行；作者确实需要显式行数证据时才启用 `options.show_count: true`。空数据仍使用统一 Empty 状态，不能把“0 rows”元信息误当成空状态替代品。

`options.mode=static` 的 `choices` 是封闭候选集合，而不是动态数据域的标签缓存。维度成员来自 Source 时必须使用 `options.mode=infer`，由 `options.source` 或消费 View 的 Base Output 推导；否则 Source 新增但未写入静态枚举的值会被有意排除。候选域来源与初始选择意图分开，避免 Dashboard 同时维护数据和一份易漂移的默认值/白名单。

组件边界、值形状、状态和交互语义逐项对齐 Ant Design Data Entry，但 Runtime 不引入 React/Ant 依赖，以保持 Server、单 HTML 与离线报告同构。Checkbox 表达随所在流程提交的 boolean，Switch 表达立即反馈的 boolean；AutoComplete 接受自由 string，suggestions 不是封闭枚举；Radio.Group 不再借用 Segmented 语义。Form 是 `control_panels` 的组合职责，不制造新的 value type。TimePicker、Transfer、ColorPicker、Mentions、Rate、Upload 只有在形成明确分析语义后才进入 DSL。完整矩阵见 [Data Entry Component 语义契约](docs/data-entry-components.md)。

普通 Table 和 Perspective 是不同模板：前者便于自定义样式，后者提供排序、筛选、分组和透视。Small Multiples/Selection Gallery 从共享 Named Output 和一个 View 蓝图生成实例，不复制查询或计算。

每个 Component 都有明确 owner Package；Package 是 headless controller、Runtime Adapter、功能 CSS、Story 和测试声明的唯一实现来源。`canvas-runtime.js` 只保留 Runtime Manifest、Named Output Store、Interactive Scheduler、Selection Binding 等共享主机能力，不再实现声明式 View、Repeat Section、Presentation 或 Data Frame/Interactive Adapter。已删除独立的 `declarative-runtime.js`，Runtime 内也不保留同功能副本。

四个核心 owner 的边界是：

| Package | 唯一拥有的行为 |
| --- | --- |
| `data.pipeline` | Frame/Grouped Frame、Named Output 数据 API、Selection-before-Compute 输入边界、三种 Interactive Runtime Adapter |
| `view.declarative` | View descriptor、内置 Renderer、Perspective/Table/Chart 生命周期与 View 状态边界 |
| `section.declarative` | Section 编排、Repeat/Selection Gallery、懒挂载与 Section 聚合状态 |
| `presentation.shell` | Theme/Layout shell 与七状态语义、ARIA 映射 |
| `runtime.control` | canonical native value、共享事件、键盘与浮层桥接 |
| `control.*` | 每个 Data Entry Component 的唯一 controller、adapter、CSS、Story 与测试声明 |

Package 内的 `test.yaml` 是机器可读验收声明，不是测试执行器；`dataviz components --check` 验证 Package 元数据、资产和声明，真实行为由 pytest 与浏览器 E2E 执行。当前 Registry v5.3 有 21 个 package-owned Package，其中 14 个是独立 `control.*` Data Entry Package，不存在 bridge implementation。

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

`view.declarative` 宿主统一识别空数据、发布 Empty、释放旧实例并在数据恢复时重新 mount；Renderer/Chart Service 负责交互事件与 ResizeObserver；Export 必须加载同一 Runtime 和 Adapter，不能另写静态渲染分支。首屏 Python 生成的 Plotly/ECharts/Perspective bootstrap 也必须注册到同一 View ID 状态表，不能绕过后续 update/dispose。命令式引擎资源必须归属具体 Renderer 实例：Perspective 的 Worker、Table 与 Viewer 一同 mount/dispose，不能把 Worker 隐藏成 Canvas 全局单例。异步 mount/update/dispose 必须在平台时限内进入 Ready、Fallback 或 Error，不能永久停在 Loading。矩阵至少同时覆盖 Plotly、ECharts、Perspective 的 Server Canvas 和 portable HTML。

Custom Renderer 的目标默认路径不是直接调用全局 Plotly/ECharts，而是使用平台 Chart Service：

```javascript
context.charts.plotly.mount(element, {data, layout, config})
context.charts.echarts.mount(element, {options})
```

Service 与内置 View Adapter 共用 Theme、responsive、`scrollZoom`、resize、update、dispose、错误状态和 HTML Export 策略。直接访问底层库仍是显式逃生口，但不会自动继承平台默认值；Scaffold、Gallery 和 AI 文档优先生成 Service 调用。`view.declarative` Package manifest 声明 `service.charts` 能力，Semantic Validation 可据最终 Renderer 配置判断属性是否生效。

Server 页面与导出 HTML 必须使用同一组件实现。

## 12. Server、CLI、HTML 与 AI

- **Server** 面向人：提交 Query Parameter、操作 scoped Controls、运行 Interactive Transform、查看 Source/Transform 证据。
- **CLI** 面向 AI/自动化：validate、query、run、compute、output、report、docs、schemas、components、context、scaffold 和 benchmark。
- **HTML** 是一次 Query Run 的可移植快照：Query Parameter 固定；Browser Interactive Transform 可以继续执行；Server Interactive Transform 只能保留 snapshot 或 unavailable。

AI 默认 JSON 紧凑且稳定。`query/output/compute` 默认只输出状态、行列数、耗时、Schema 摘要和有限预览；完整 Node、Artifact、Resolved SQL、bindings、provenance 和 diagnostics 通过 `--detail debug|full` 请求。精简不能删除失败所需的稳定错误 code 和下一步建议，也不能让 summary/full 使用两套执行逻辑。

目标布局与视觉检查分为两层：

1. `dataviz inspect-layout WORKSPACE DASHBOARD --format json` 只读取编译后的 Layout Contract，输出 Section/View 行列、span、默认来源、冲突和 `mode: declarative|custom`，不启动浏览器；
2. `dataviz visual-check WORKSPACE DASHBOARD` 使用真实浏览器和固定 viewport 检查溢出、重叠、零尺寸、弹层裁切、稳定后永久 Loading、Perspective 容器高度、Console error 等客观事实，并可输出 Screenshot 与机器可读 geometry report。

`visual-check` 不声称判断配色、信息层级、业务图表选择或“是否好看”。自定义 Canvas 的任意 CSS 无法由静态 Contract 完整解释，必须走浏览器检查；视觉模型或人工审阅仍是主观质量的最终证据。

AI 的默认工作应该是选择模板、绑定 Output、填写状态依赖和业务表达式，而不是每次生成整页前端代码。安装包必须提供严格 Schema、静态 validate、机器可读 docs/components/context、Scaffold、Gallery、稳定错误码和 authoring 日志。

`validate` 不执行查询或计算；静态通过后，再按 Source、Base Output、Interactive Output、View 的顺序动态验证。框架是否节省 Token 必须通过相同任务与完整 HTML 对照，不能由模板数量自行推断。当前安装包提供五类固定任务、严格的 `authoring-event/v3` 日志和 identity/quality-gated 成对比较。Trial 会固定任务契约与输入 SHA-256；每条验收条件必须记录 human/automation/mixed assessor 和证据，只有两种方案均保持输入完整并通过全部验收时才进入聚合。在积累真实重复 trial 前，不发布节省比例。

## 13. 当前实现边界

当前执行契约：

| 契约 | 版本 |
| --- | --- |
| Dashboard schema | `dataviz/dashboard/v8` |
| Presentation schema | `dataviz/presentation/v2` |
| Source schema | `dataviz/source/v2` |
| Dashboard Dependency Contract | `dataviz/dependency-contract/v5` |
| Dashboard Layout Contract | `dataviz/layout-contract/v1` |
| Browser Runtime Manifest/Event | `dataviz/runtime/v5` |
| Dataset Transform schema | `dataviz/dataset-transform/v2` |
| Interactive Transform schema | `dataviz/interactive-transform/v2` |
| Component Registry | `5.4.0` |

已经实现：

1. Query Parameter 与 scoped Controls 是两个一级入口；Control 统一作用域结构，同时按 selection/compute delta 保持不同提交周期和失效路径。
2. Query DAG 与 Interactive DAG 分离；Base Output 对一次 Query Run 不可变，Derived Output 由 generation 隔离；快分支可在无关 Query 分支仍运行时进入 Server/Browser Interactive 计算。
3. Dataset Transform 使用 `server-python`；Interactive Transform 支持 `server-python`、`browser-python` 和 `browser-js`。
4. 三种 Interactive Runtime 只接收显式状态和 Named Output，不访问 View DOM；Interactive Runtime 不持有 Adapter。
5. Query 与 Interaction 都支持局部并发、分支失败隔离、timeout、cancel、progress、缓存证据和资源释放。
6. Python 节点支持 `context.log(message, level=..., **fields)`；实时事件和 `dataviz/execution-log/v1` Artifact 保留结构化日志及完整失败 traceback，并可通过 session 隔离 API 与 Sources 证据面板检查。
7. HTML Export 强制声明 `interactive`、`snapshot` 或 `unavailable`；Server Python 不伪造离线交互。
8. `validate`、`compute`、`docs`、`schemas`、`components`、`context` 和 Scaffold 使用同一当前契约。
9. 同一 tab 的状态可恢复，不同 tab、Dashboard、用户、Query Run 与 Interaction generation 相互隔离；父页面/Canvas 消息还校验当前 frame identity。
10. `authoring prepare/verify/assess/start/finish/compare` 可以用固定任务、经过完整性校验的 approach prompt、输入完整性、逐项验收证据、真实客户端 Token、首次成功率、修正轮次和耗时对比 Dataviz 与 standalone HTML；缺失 Token 不做估算。
11. `data.pipeline`、`view.declarative`、`section.declarative`、`presentation.shell` 已从 bridge 完整迁入物理 owner Package；Runtime v5 通过公开 ready event 装配且 dispose 幂等。
12. Gallery 已覆盖四类组件的七状态矩阵，以及真实 10/100/1,000 选项 Select Story；Story 元数据、页面目标与 Chromium 行为测试使用同一 Package。
13. `selection_inputs` 在 Server `ExecutionContext` 和 Browser `data.pipeline` 的公共输入边界先裁剪表数据，三种 Interactive Runtime 都保证 Selection 先于 Compute。
14. 动态 Selection option domain 从 Base Output 建立；首次运行先 hydration/reconciliation，再渲染与调度 Interactive 分支。`canvas-ready` 只在首次 canonical state 提交后发布，Browser Interactive 状态通过 frame identity 约束的事件同步到 Server `Pipeline` 面板。
15. Query、Interactive、Control、Output 与 View 的所有边由单一 Dependency Contract 编译；Planner、Server、Browser、Export、CLI 与 AI context 只消费其投影。Query/Interactive 节点只能读取声明的参数，Browser 注册与契约漂移会立即失败。
16. Selection 的唯一状态是 `{intent, values}`；Control、Repeat、View、三种 Interactive Runtime、tab 恢复与 HTML Export 共用 resolver。`explicit + []` 是明确空集，`all_available` 随候选域变化；optional Single Select 支持受契约约束的 Clear。
17. View 可通过一条 `control_binding` 双向绑定现有 Selection Control。Dependency Contract v4 编译唯一 writer 与普通 consumers；Plotly、ECharts、Table 和 Custom Renderer 只通过类型化 Adapter Action 写 canonical state，并拒绝越界、第二 writer、旧 generation 与反向作用域依赖。
18. Layout Contract v1 是声明式页面结构的唯一编译结果；Dashboard 拥有顺序、模板、columns 与 span，Presentation v2 只拥有视觉。默认 Renderer、Server、HTML、AI context 与 validate 共用该契约，自定义 Canvas 只暴露稳定 mount points。
19. Semantic Validation 在最终 Layout/Dependency/Renderer 配置上输出稳定 error/warning/advice；`inspect-layout` 公开编译后的行列与来源，不维护第二张布局图。
20. `state-snapshot/v1` 是当前分析状态的只读证据；默认画布不展示状态胶囊。作者显式启用后，Dashboard/Section/View 才展示 committed/applied 值，并把 Compute draft 明确标成待应用。
21. browser-js/browser-python 默认 `auto`，server-python 默认 `apply`；显式 trigger 仍优先。`query/output/compute` 默认返回紧凑 `dataviz/cli-result/v1`，调试证据通过 `--detail debug|full` 获取。
22. Custom Renderer 通过 `context.charts.plotly/echarts` 复用平台 Theme、滚轮、Resize、Update 与 Dispose；`visual-check` 对 Server/Report 执行真实浏览器几何和永久 Loading 检查并保存截图。

仍属于后续优化，而不是隐藏的兼容工作：

1. Arrow 已优化传输和浏览器 Interactive Transform 输入；通用 Selection 与部分 Renderer 首次消费大表时仍可能物化 JavaScript 行对象。
2. 固定 10K/100K/1M Query → Arrow → browser-js → Renderer 基准已经记录进程树 RSS、页面耗时和三轮 dispose 回落；流式 groupBy 由该证据触发，而不是凭行数猜测优化。
3. Server 尚未提供通用服务端分页或按需 Record Batch。现有 1M 聚合链路不足以证明需要扩张 DSL，也不能外推为 1M 原始 Table/Perspective 安全；二者都必须由各自基准触发。
4. authoring 评测工具已实现，但尚未积累足够的重复真实 trial，不能声称固定 Token 节省比例。
5. Chromium/Firefox/WebKit 已覆盖 390×520 弹层几何、内部滚动、键盘、ARIA、外部关闭，以及 Perspective 重复 dispose/reload/wheel 恢复；新增组件必须继续进入同一矩阵。
6. 当前协调模型是单进程：`dataviz serve` 启动一个进程，Run、Navigation、Cache 与报告发布锁不提供跨进程互斥；多个进程不得同时写同一 Workspace/输出路径。Runtime 并发上限在启动时捕获，修改配置后需重启。
7. Server 不提供账号体系或 HTTP 鉴权，默认只绑定回环地址；非回环 `--host` 必须显式使用 `--allow-remote`，访问控制由可信网络或外部代理承担。`session_id` 是 tab 状态命名空间，不是身份认证。
8. Semantic Validation 只判断确定性 no-op 与保守启发式；它不会根据未知真实数据规模判定图表是否适合，也不会替代人工审美判断。
9. 可选分析状态摘要覆盖默认 Canvas；完整自定义 Canvas 即使启用摘要，也需要显式放置稳定的 state-summary mount，平台不会猜测任意 HTML 的标题区域。
10. visual-check 判断溢出、裁切、重叠、零尺寸、永久 Loading、Perspective 高度和 Console error，不判断配色、业务图表选择或叙事质量。

Component Registry 独立版本化，只在公共组件契约变化时升级，不跟随 Dashboard schema 机械改号。

## 14. 已明确放弃的旧方向

以下内容不是待恢复功能：

- 不以中心 Server 数据库保存页面和多人编辑状态；Git/文件夹是协作边界。
- 不提供可编辑数据逻辑、依赖、布局和样式的通用网页开发器；Server 只保留默认值、静态候选项与同级顺序的受限人工调参面。
- 不使用 Filter/exclude；Selection 只表达 include。
- 不把 Selection 与 Compute 的 Runtime 语义抹平成无类型参数；统一入口必须保留显式 `kind`。
- 不支持任意 Filter Group 或一个 View 同时归属多个组。
- 不恢复 Mosaic、Widget 坐标或拖拽画布协议。
- 不让 browser-python/Pyodide 直接操作 DOM 或承担 View Renderer；它只产生 Named Output。
- 不把凭证写进 Dashboard，也不让 Dataset/Interactive Transform 获得隐式 Adapter。
- 不为已经移除的实验性字段、Schema 或 Runtime 保留 alias、自动迁移或双协议分支。
- 不要求普通 Dashboard 编写自定义 HTML/CSS/JS；完整 Canvas 只是最后逃生口。

## 15. 演进规则

1. 先固定状态与执行语义，再实现 Runtime，最后扩展 UI 模板。
2. 阶段和执行位置必须正交；不能再以 Server/Browser 命名业务阶段。
3. 新 Runtime 必须输出相同 Named Output，并遵守相同局部失效、错误和 dispose 契约。
4. 新组件由真实 Dashboard 需求触发，不能因为某个 UI 库存在就照单全收。
5. Schema、Runtime protocol、Component Registry 和 Package 独立版本化。
6. 0.x 阶段不为未投入生产的旧设计保留兼容分支。
7. 文档声明必须能由当前 Schema、CLI、Runtime 或测试证明；尚未实现的目标必须明确标记。

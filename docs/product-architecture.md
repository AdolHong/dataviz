# Dataviz 当前实现索引

更新时间：2026-09-01

本页帮助开发者和 AI 从产品契约定位到代码。设计语义以 [DESIGN](../DESIGN.md) 为准；字段以当前安装环境的 `dataviz schemas` 为准。

## 1. 版本边界

```text
Workspace              dataviz/workspace/v2
Dashboard              dataviz/dashboard/v17
Parameter Domain       dataviz/parameter-domain/v2
Parameter Domain Contract dataviz/parameter-domain-contract/v3
Parameter Lookup       dataviz/parameter-lookup/v1
Parameter Materialization dataviz/parameter-materialization/v1
Presentation           dataviz/presentation/v2
Source                 dataviz/source/v6
Dataset Transform      dataviz/dataset-transform/v3
Interactive Transform  dataviz/interactive-transform/v4
Dependency Contract    dataviz/dependency-contract/v12
State Snapshot         dataviz/state-snapshot/v5
Browser Runtime        dataviz/runtime/v13
Analysis Result        dataviz/analysis-result/v4
Analysis Evidence      dataviz/analysis-evidence/v4
Layout Contract        dataviz/layout-contract/v1
Workspace Change       dataviz/workspace-change/v1
Dashboard Bundle       dataviz/dashboard-bundle/v2
Report Manifest        dataviz/report-manifest/v3
Component Registry     5.9.0
```

这些契约独立版本化。Loader 只接受当前严格模型，不包含旧字段 alias、自动迁移或双协议执行分支。

关键入口：

- 领域模型：`src/dataviz/workspace/models.py`
- Workspace 公共加载 façade：`src/dataviz/workspace/loader.py`
- Workspace 物理 owners：`src/dataviz/workspace/loading/`（parse/load、loaded snapshot、cross-file contract、asset validation、catalog/navigation）
- Workspace 共享文件身份与安全解析：`src/dataviz/workspace/assets.py`
- 机器可读 Schema：`src/dataviz/schema_docs.py`
- CLI 内置手册：`src/dataviz/documentation.py`
- 渐进 Authoring 路由与 Workspace Scaffold profiles：`src/dataviz/documentation.py`、`src/dataviz/authoring.py`
- Dashboard 依赖契约编译：`src/dataviz/execution/dependencies.py`
- Dashboard 布局契约编译：`src/dataviz/layout.py`
- Canonical Input State：`src/dataviz/input_state.py`
- Control value/filter consumer：`src/dataviz/execution/control_filter.py`
- Analysis Catalog、Evidence、Promote 与执行：`src/dataviz/analysis/`
- Analysis 使用统计：`src/dataviz/analysis/usage.py`（`.dataviz/usage.sqlite`，best-effort，不进入 fingerprint）

## 2. 单一 Dependency Contract

Dashboard 快照的 `dependency_contract` 属性以并发安全的首次初始化惰性编译并缓存唯一的 `dataviz/dependency-contract/v12`；热更新创建新快照和新契约。同一快照的所有消费者读取同一个对象。它同时拥有：

```text
Query Parameter → Query Node inputs/dependencies/outputs → downstream Views
Base/Derived Output → Interactive inputs/dependencies/outputs
Control → direct dependencies/transitive closure/domain/View/Transform/content edges
View user event → ordered Control writer edges
Named Output → View consumers
```

`execution.plan`、`execution.interactive`、Loader 跨文件校验、Canvas、Server Pipeline、HTML manifest、Web Component Adapter、AI context 与 `dataviz inspect dependencies` 都只消费这份契约。不存在第二套按 Control 类型推断边的依赖图。

P1-B 只模块化这份 canonical derivation 的内部实现：`compile_dashboard_dependencies()` 编排 Query/Interactive 图与 binding、Output/View 输入、Control writer/domain/impact、跨 Runtime invariant、reverse index 和 Query Parameter impact 等私有函数，最终仍只生成同一个 v12 Contract。`LoadedDashboard` 继续分别惰性持有 Dependency、Layout 与 Parameter Domain Contract；没有 `CompiledDashboard`、phase class、总编译 pass、中间 cache 或新版本轴。语言无关 characterization fixture 同时冻结 v12、Layout v1、Runtime Manifest、请求级 ExecutionPlan、Catalog/inspect 与关键 diagnostics；编译失败不会缓存 partial Runtime fact。

编译结果还保存每个 Query Parameter 的最终影响闭包：需要重跑的 Query 节点、随后失效的 Interactive 分支、option Control、内容字段和 View。Control 则分别保存直接数据筛选、Interactive consumer、派生 View 与内容边，避免把“结构 scope”误说成“每次一定重绘”。

Browser Runtime 不做拓扑排序，也不从 DOM 层级重建 Control DAG。Transform/View 注册会核对编译后的 data inputs、`control_inputs` 和 Output names，但注册 payload 只作 drift assertion；Interactive 调度、View waiting 和 Renderer 取数继续消费 Contract。Control 候选关系使用 Compiler 生成的 `control_order`、`depends_on` 与 `dependency_ancestors`。因此 DSL、Server 和 Browser 对同一条边产生分歧时会立刻失败，而不是显示部分正确的页面。

`depends_on` 的 `dashboard.<id>`、`section.<id>`、`view.<id>` 都相对目标 Control 解析，只允许当前 Dashboard、所在 Section 和自身 View。每项只声明直接父节点；Compiler 计算传递祖先/后代并拒绝未知父节点、非法作用域和环。依赖型候选域必须来自不可变 Base table；Output 声明 Schema 时，Compiler 同时验证子字段及全部祖先字段。候选变化时，Runtime 优先保留当前有效交集；原非空选择完全失效才恢复 `initial`，用户主动空集不会被自动填充。

View 的 `control_binding` 编译为独立且按 View 声明顺序稳定排列的 writer/projection edge，不参与 Control DAG 环。同一个 Control 可以有零到多个经 Compiler 校验的 writer View；Plotly、Table 与 Custom Renderer 只通过携带 `action_id + source_view` 的类型化 `select / select_many / clear / reset` Action 写同一 canonical state。`select/select_many` 是明确 replace/set，不做隐式 union；`clear` 表示显式空值，`reset` 恢复 Control 的初始策略。Plotly 原生 `doubleclick` 只负责恢复 zoom scale，不能隐式映射为 Control `reset`；恢复 Control 由绑定图表工具栏中的明确 action 产生。再次点击当前激活的 Box/Lasso 工具只退出选择模式并保留已有选区。Bound writer 仅 selected projection 改变时使用 `Plotly.restyle(selectedpoints)`，不以完整 `Plotly.react()` 重建 marker 命中层。Bound View 应用目标 Control 的祖先但排除目标自身筛选，因此在空选择或单选时仍能展示完整候选上下文。Compiler 对每条 edge 校验 source View、scope、字段、声明类型、聚合映射与 Renderer 能力，并拒绝 View writer 反向决定 Section/Dashboard 候选域。

P5.4 的 `control_binding.writes` 允许同一 datum 额外投影上下文 Controls，典型用例是全国门店点击一次写 City + Store、城市地图继续只写 Store。主 binding 仍唯一决定 writer View 的 selected projection；每个附加目标在 Dependency Contract 中保留独立 context writer edge。ControlRuntime 在修改任何 state 前验证整批 projection，并以一个 action ID 一次提交所有合法目标、按现有 Control DAG 调和候选域和调度 consumer。single-value target 的多值投影、缺字段、越界、类型错误或 stale generation 会拒绝整次 action，不能产生中间帧或 partial state。Result/Evidence 继续使用已有 per-Control provenance，并以共享 action ID 关联同一手势。

环、未知 Output、浏览器 Runtime → `server-python` 的非法边和越过下游 View scope 的 Control consumer 都在编译期拒绝。Loader 只在契约无法形成时运行 recovery diagnostics，以便一次展示更多错误；它不向 Planner 或 Runtime 提供另一张图。

Control 的结构 scope 与数据适用性分开报告。`direct_view_bindings` 记录字段、operator、输入 Output 和 `declared | runtime | not_applicable`：Output schema 能保证字段时静态确认，否则在表格水合后按真实字段收窄；非表格 View 不进入直接数据重绘。`affected_views` 是保守上界，不伪装成每次交互的精确结果。

检查入口：

```bash
dataviz inspect dependencies WORKSPACE DASHBOARD
dataviz inspect dependencies WORKSPACE DASHBOARD --format json
```

新建作者任务不需要先加载上述完整依赖契约。`dataviz docs --task minimal|interactive|custom-renderer --format json` 返回 `dataviz/authoring-route/v1` 最小概念闭包；`dataviz docs --component <id>` 根据 Component Registry 自动选择路由。`dataviz scaffold --list --format json` 返回 Scaffold Catalog v2，区分完整 Workspace profile 与组合片段。

## 3. Query DAG

```text
Query Parameter → Source → Dataset Transform → Base Named Output
```

- 编排：`src/dataviz/execution/plan.py`
- 执行：`src/dataviz/execution/executor.py`
- Query Parameter 解析与节点本地投影：`src/dataviz/execution/parameters.py`
- Parameter Domain Contract：`src/dataviz/execution/parameter_domains.py`
- Workspace 共享物化、Lookup、刷新 lease 与 generation pin：`src/dataviz/execution/parameter_materializations.py`
- Workspace 时区相对日期：`src/dataviz/relative_dates.py`
- Source Runner：`src/dataviz/sources/`
- Python 子进程：`src/dataviz/execution/python_process.py`
- Artifact 与 Named Output：`src/dataviz/artifacts/`、`src/dataviz/execution/outputs.py`
- 缓存：`src/dataviz/execution/cache.py`

Query Run 固化每个 Query Parameter 的 canonical state 和 Base Output。scoped Controls 不进入这张 DAG。每个 Query 节点以 `query_inputs` 声明自己可读的本地 alias；结构化绑定可把 `range_input/date` 投影为 `start`/`end`，也可把候选多选投影为 `selection=all|include|exclude|none`、有限 `value` operands、`active` 或完整 `state`。普通 SQL 优先使用 `query_filters` 与受限 `{{ dataviz_filter:name }}` token：`all/include/exclude` 参数化生成 `TRUE/IN/NOT IN`，空 `multiple_input` 或候选 `multiple_select none` 由该 consumer 必填的 `empty: passthrough|match_none` 生成 `TRUE/FALSE`，不会产生 `IN ()`。相对日期默认值先按 Workspace IANA 时区解析为 ISO 日期，再进入 Run、缓存和执行上下文。节点按依赖闭包并发，Output 完成后立即发布；无关分支不互相等待。

网页动态候选位于 Query DAG 之前：`Parameter Domain SQL → Workspace shared immutable materialization → Server-local Lookup → Query Parameter draft → Query DAG`。SQL Domain 不按基数分叉，也不读取 Dashboard draft `query_inputs`；它由 definition/code hash、实际 Adapter identity 和 visibility scope 定位 generation，可跨 Dashboard、tab 和同可见范围用户复用。Browser 只持有当前页和有限已选 operands；搜索、generation-bound cursor 分页和 `depends_on` 父级 predicate 都读取同一 pinned Parquet generation，不重新执行远端 SQL。父 `single_select` 的 canonical 标量按单值 include 解释，父 `multiple_select` 使用 `all/include/exclude/none`。`refresh_after_seconds` 与 `expire_after_seconds` 分开控制 stale-while-revalidate 和 hard expiry；失败只禁用相关 Picker，不得阻断 Query、自由输入或 Workspace 导航。

AI 可按需使用 `dataviz parameters prewarm|status|lookup|refresh` 探索同一物化；`dataviz run` 只消费调用方 state 或可独立解析的 default，绝不为了候选校验而隐式构建物化。Result、Evidence、URL/tab checkpoint、portable HTML 与分享缓存只封存紧凑 state：`all/none` 没有 operands，`include/exclude` 只保存有限 operands；它们不包含 Domain SQL、Parquet、候选页、search 或 cursor。跨 Workspace 搬运单个 Dashboard 使用 `dataviz bundle` 在新目录或空目录创建独立快照，复制共享 Domain definition/SQL、实际引用的 Workspace Asset 与非敏感 binding manifest，默认不复制 `.dataviz`、无关文件或凭据；它不合并或覆盖已有 Workspace。Parameter Domain 与 Canvas Interactive Runtime 没有执行边，不进入 browser-js 或 Renderer。

File、SQL、Python 是 Source 的三种入口。Workspace v2 可注册共享静态文件；File Source v6 用 `asset:<id>` 读取时显式声明 format。Dashboard v17 的 Browser `assets` allowlist 与 Source 引用相互独立；Runtime v13 的 `context.assets` 在 Server URL 与 portable inline 之间保持同一 API。普通 SQL/文件默认属于 Dashboard；共享只用于稳定 Workspace Asset 与真正共用的 Parameter Domain。`dataviz bundle` 在 staging 中复制两类实际引用的联合闭包并校验 hash 后一次发布，输出不再跟踪源共享资源；`inspect context` 只投影 Asset 元数据。SQL 默认单次超时 120 秒，明确超时后立即额外重试一次；Source 可以覆盖 `timeout_seconds` 与 `timeout_retries`。SQL 面板保存参数化 statement、Resolved SQL、bound parameters、Adapter、耗时、重试和 hash 证据，但不公开凭证。

Python Source 与 Dataset Transform 使用 fresh spawn 子进程，支持硬 timeout、cancel、progress、完整 traceback、声明依赖指纹、多输入和多 Named Output。`context.log(...)` 产生实时 `node_log`，并保存 `dataviz/execution-log/v1` Artifact；Artifact 受 tab session 隔离，Query 节点可在 Sources 证据面板直接检查。

## 4. Interactive DAG

```text
Base/Derived Output + committed Query snapshot + scoped Control deltas
                                      ↓
                           Interactive Transform
                                      ↓
                            Derived Named Output
```

- 服务端计划与执行：`src/dataviz/execution/interactive.py`
- Server Control filter/value 投影：`src/dataviz/execution/control_filter.py`
- Browser 控制器：`src/dataviz/server/static/canvas-runtime.js`
- Browser Control 状态桥：`src/dataviz/components/packages/runtime.control/`
- browser-js Worker：`src/dataviz/server/static/interactive-js-worker.js`
- Server Run/generation 隔离：`src/dataviz/server/manager.py`

公共 Runtime Adapter 生命周期是：

```text
validate → prepare → execute → cancel → dispose
```

两种 Runtime 都只返回声明的 Named Output，不访问 Renderer DOM，也没有 Adapter：

- `server-python`：独立进程，适合本机原生依赖；HTML 只能 snapshot/unavailable。
- `browser-js`：Web Worker；默认的轻量浏览器计算路径。

浏览器内 snapshot 数据加工和便携交互使用 `browser-js`；完整 Python 生态、复杂模型、求解器或大规模计算直接使用 `server-python`。

每次交互以 `tab + dashboard + query run + transform + generation` 隔离。较新的 generation 只 supersede 相同分支的旧任务；迟到请求会收到 `interaction_generation_stale`，不能覆盖新结果。

Interaction endpoint 从 Query Run 建立时就属于该 Run，不以整次 Query 到达终态为前提。RunManager 持续发布不可变 Query snapshot；某个 Base Output 就绪后，依赖它的 `server-python` 分支可以读取当前 snapshot 并立即运行，无关慢 Source 不构成屏障。当前 Dashboard 若修改了 Query 语义，Query Contract fingerprint 会拒绝复用旧 Run；只修改兼容的 Interactive/Presentation 逻辑时可以继续复用同一批 Base Output，便于开发态迭代。

`execution.plan.server_interactive_base_references()` 在 Query 建立时分类可达 `server-python` 分支所需的 Base Output，并通过 Run API 暴露 `server_interactive_inputs`。数据只保存一份：所有 Query Artifact 位于 Workspace `.dataviz/runs/<run-id>/artifacts/`，不进入 Dashboard；RunManager 用 `tab session + dashboard + run` 控制访问，Interactive Executor 再按 canonical Output reference 读取。Source/Dataset 的 NodeCache key 包含 Dashboard 与节点 ID，默认 tab namespace 位于 `.dataviz/cache/tabs/<session-hash>/`。因此页面刷新可以恢复同一 Run，跨 tab 访问被拒绝，交互执行也没有 Source Runner 回退路径。

`trigger` 支持 `apply`、`auto` 和 `manual`。Interactive Transform 只用 `control_inputs`：`mode: value` 把一个 projection 传给代码，`mode: filter` 对明确列出的 table input 应用字段、operator 和空值策略。同一 Control 可以同时被自动预览和显式 Apply 的消费者读取；Runtime 分别记录 current state，以及每个 View/Transform 在 generation 启动时捕获的 applied revision/state。只有当前 generation 真正 Ready/成功才推进 evidence，内容绑定与 provenance 只描述真正产生当前结果的状态。

Control Select 用 `options.mode=static|infer` 明确候选域所有权。动态域不从派生 View Output 建立；Dependency Compiler 会把每个 `infer` Control 沿消费 View 的 Interactive 输入追溯到 Base Output，显式 `options.source` 也只能引用 `source:` / `dataset:` 表格 Output，并作为 Query reachability root。带显式 `depends_on` 的 static Select 同样绑定 Base option domain，但只允许声明的封闭 choices。Control Select 使用 `initial`：多选为 `all/empty/values`，单选为 `first/empty/value`；Query Parameter 则统一使用 `default` 和独立的 compact selection state。Canvas 首次启动按 `hello → checkpoint/null/timeout → hydrate Base → reconcile Controls in control_order → commit canonical snapshot → render/run consumers` 执行，避免必填空 `<select>` 抹掉 canonical state并阻断整页。`dataviz:canvas-ready` 在 canonical 初始化后发布，表示 Control action 已安全；它不等待 consumer 完成。

ControlRuntime 在 Server/Portable 唯一拥有完整 canonical state。Server Shell 的 Header 只发送带 `action_id + base_control_version + source_view:null` 的 typed `set` 或 Control keys-only Apply，View writer 则发送声明过的 `source_view`；两者都由同一 reducer 串行解释。View action 在同步入队时校验 source/binding/render generation，这一刻就是准入线性化点；合法 action 随后按接收顺序执行，不能因前一 action 让同一 writer 自重绘而被追溯性判为 stale，writer DOM 实例被替换/移除则仍稳定拒绝。Shell 显示 Canvas 返回的 operational projection，并持久化最后一次确认且 Contract hash 匹配的 checkpoint；它不 canonicalize、不增加 revision、不协调候选域，也不做 winner merge。private lockstep `postMessage` 的每条消息同时校验 origin、active iframe source 与 dashboard/run/frame identity；Server Python 只消费完整 canonical snapshot，任何 normalization drift 都以 `control_state_not_canonical` 拒绝。

## 5. Output、状态和证据

Canonical Output Reference：

```text
source:<id>/<name>
dataset:<id>/<name>
interactive:<id>/<name>
```

所有节点共用 `NodeResult.outputs` 和 `ArtifactDescriptor`。Output 类型包括 table、scalar、object、text、html、chart、image 和 file；声明名称与实际返回必须完全一致。

节点状态统一为：

```text
not_run → queued → loading → ready | empty | error | cancelled | unavailable
                         ↘ stale（交互结果等待重新提交）
```

运行证据包括输入 content hash、代码与依赖指纹、参数快照、缓存来源、耗时、progress、结构化日志和错误 traceback。缓存命中复用 Output，但不会冒充一次新的 Python 执行日志。

## 6. Browser Runtime 与局部更新

Server 与 HTML 共享 `dataviz/runtime/v13` Manifest、Named Output Store 和 Runtime Event。共享主机源码按 Manifest、Value Contract、Output Store、Interactive Scheduler、Control Binding、Renderer Lifecycle 与 bootstrap 分布在 `src/dataviz/server/runtime_src/`；`python tools/build_canvas_runtime.py` 确定性生成 Server 与 HTML 唯一加载的 `server/static/canvas-runtime.js`，`--check` 用于 CI/发布门禁。`runtime.control`、`data.pipeline`、`view.declarative`、`section.declarative`、`presentation.shell` 分别物理拥有输入协调、数据 Adapter、Renderer lifecycle、Section/Repeat 和 Presentation state，借 `dataviz:runtime-ready` 装配到主机，不在 Runtime 源码模块中保留第二份实现。命令式 Renderer 实例拥有其全部引擎资源；Perspective 的 Worker/Table/Viewer 不作为 Canvas 全局单例共享，实例释放时三者共同释放。异步引擎阶段具有有界终态，失败时进入结构化 Fallback/Error，而不是无限 Loading。

Server Header 中的 `Pipeline` 面板同时展示 Query 节点与 Interactive Transform。Query 状态来自 Run SSE；Browser Interactive 状态通过当前 iframe 的 `dataviz:interactive-status` 消息回传，并同时校验 dashboard/run/frame identity，避免跨 Dashboard 或旧 frame 污染状态。

Runtime 根据显式依赖建立反向索引：

- Query Output 就绪时只启动刚满足依赖的 Interactive Transform 和 View。
- `mode: filter` binding 只筛选字段适用且位于其作用域内的 View。
- View Control 不重绘兄弟 View。
- `mode: value` binding 只失效声明消费它的 Interactive Transform 下游。
- 新 Run 可以显示 stale 旧结果，但不会把两个 Run 的 Output 静默混合。

父页面与 Canvas 的消息同时校验 origin、source、`dashboard_id`、`run_id` 和 `frame_id`。Canvas ready 后主动握手；Query 到达终态时父页面只更新 Interaction endpoint，不重新加载 iframe。

Runtime 将 Control state delta 与 Output delta 分开；具体效果来自每个消费者自己的 `control_inputs` binding，而不是 Control 的全局 kind。调用方必须显式传递“全部变化”“部分变化”或“没有变化”，不能用省略参数混淆语义。缺失 Derived Output 只负责首次启动分支；若分支已经 active，无关 Output 发布不会取消或重复启动它。Output signature 未变化时也不会继续传播或重绘。

大 Table 的传输可使用 Arrow IPC/columnar envelope；浏览器按需解码。部分通用 Data Entry Component 和 Renderer 首次消费时仍会物化 JavaScript 行对象，当前不承诺完整的浏览器列式查询引擎。

声明式 View、browser-js Worker 和 Custom Canvas 的内置数值聚合使用线性 reducer，不通过 `Math.min(...rows)` / `Math.max(...rows)` 展开大数组。Worker/Data API 的 groupBy 还采用单遍流式聚合，每组只保留 key 与 count/sum/min/max。固定 10K/100K/1M 证据与测量边界见 [Runtime 性能基线](runtime-performance.md)；聚合链路通过不等于 1M 原始明细 View 已获支持预算。

规模回归入口：

```bash
dataviz benchmark runtime <workspace> <dashboard> --format json
```

浏览器基准等待 Arrow hydration、Interactive Transform、Repeat reconciliation 和已挂载 View 进入稳定状态，并分开记录 Query、报告构建、页面就绪、Arrow 行数/字节/耗时、Renderer mount/update/failure/耗时与 View 终态。

Renderer 作者接口：

```text
validate → mount → update → dispose
```

平台验收的是更完整的行为矩阵：

```text
mount → update → empty → restore → interaction → resize → dispose → export
```

Plotly、普通 Table、Perspective、文本、图片和自定义 Renderer 都通过四个作者 hook 工作；Empty/Restore 由 View 宿主统一管理，Interaction/Resize 由 Adapter 或 Chart Service 管理，Export 复用同一 Runtime。Python 首屏 bootstrap 也注册到 View ID 状态表，不能成为不受 update/dispose 管理的旁路。

Plotly 是 Dataviz 唯一的作者图表接口。声明式模板负责常见字段映射，并允许通过 `options.trace`、`options.layout` 与 `config` 覆盖；可信 Custom Renderer 既可以通过 `context.charts.plotly` 继承平台生命周期，也可以使用页面内嵌的完整 Plotly.js API 实现自定义 trace、函数、事件与命令式交互。Dataviz 不维护封闭的图表能力白名单。官方文档与 Gallery 是视觉和 API 参考，项目 Recipe 只是少量完成 Dataviz 生命周期适配的样例。作者不选择图表引擎，Scaffold、focused docs 和 Gallery 也不暴露引擎分支。

页面滚动优先于图表手势：Plotly 模板默认关闭 `scrollZoom`。直接调用底层 API 时必须自行承担 Theme、Resize、Update、Purge、事件解绑和滚轮所有权。Perspective 自己拥有内部滚动和 WASM/Table 生命周期；只有内部确实能继续滚动时才拦截滚轮。

失败、取消与 unavailable 节点的结构化错误会进入 portable Output 状态。终态 Run 可以重新打开检查：已经完成的兄弟 View 保持 ready，受影响的 View 显示 error/cancelled/unavailable，而不是返回 500 或无限 loading。

## 7. HTML Export

Interactive Transform 必须声明：

- `interactive`：导出后继续计算，只适用于浏览器 Runtime。
- `snapshot`：固化当前 Derived Output 与状态，相关控件只读。
- `unavailable`：明确展示离线缺失能力和原因。

Server 页面导出时会向 Canvas 请求 canonical snapshot；请求按当前 Dashboard contract 清除 sessionStorage 中可能遗留的未知 key。可达 Interactive DAG 中只要存在 `server-python`，HTML Export 就返回 `html_export_server_runtime_unavailable`，并引导创建分享链接；独立 HTML 不会把 Server Runtime 伪造成 snapshot。

CLI 无浏览器上下文时不会替用户伪造 browser snapshot。需要当前页面交互状态的报告由 Server 页面导出；确定性的默认状态报告可以使用 `dataviz report`。

## 8. Workspace、Adapter 和隔离

- Dashboard 文件夹末级名称是导航显示名。
- `dashboard.id` 是 API、DAG、缓存和状态的稳定身份。
- `##` 编码逻辑目录，`__TRASH__##` 编码回收站。
- `workspace.yaml` 只补充空目录、顺序和 Runtime 等磁盘命名无法表达的状态。
- Dashboard 只引用自己声明的逻辑 Adapter reference，再由 Workspace 绑定到具体 Adapter；凭证留在 `auth/adapters.local.yaml` 或环境变量。

Server 状态以浏览器 tab 的 `session_id` 为边界。不同 tab、Dashboard、用户、Query Run 和 Interaction generation 不共享草稿、取消信号或运行证据。内容寻址缓存可以复用相同输入的结果，但不会共享交互状态。

分享结果属于 Workspace Runtime 数据而不是 Dashboard 源码。每个 `/shared/<share-id>` 对应 `shared_caches/<dashboard>_<timestamp>_<run>/`，其中只保存 manifest、Query Result 和经过哈希校验的 Artifact。分享页锁定 Query Parameter，不提供 Run；Browser JS 在端侧执行，Server Python Interactive Transform 通过既有 Interaction API 执行。Server 重启时把持久化结果恢复为当前浏览器会话独享的合成 Run，不能把 generation、取消信号或草稿跨浏览器共享。v1 不做过期和自动清理。

开发态 Hot Reload 位于 `src/dataviz/server/hot_reload.py`：dependency-free watcher 只做 stat 扫描并忽略 `.dataviz`/虚拟环境/构建目录，debounce 后根据已解析声明和实际引用资产计算 Workspace semantic snapshot，把变化分成 navigation、canvas、analysis、query、server 或 invalid；无关临时文件不会重载 Canvas。`server/app.py` 原子发布完整快照并提供 Workspace SSE；Query 请求会先 flush 尚未发布的文件批次，并返回所捕获的 revision。`server/static/app.js` 保留 tab 状态、处理增量刷新并在真正晚于 Run 的 Query Contract 变化时进入 Outdated。活动 Run 始终继续使用启动快照，页面恢复时 `/api/session/runs` 会再次核验当前 Contract。

`.dataviz/runs` 与 `.dataviz/cache` 是唯一运行数据根目录，Dashboard 文件夹和 Dashboard ZIP 不包含缓存。所有已发布 Query Output 在有界 Run 保留期内存在；其中 Server Interactive 输入会被显式标记和保护，而不是重复存储。活动 Interaction 消费的 Run 不能被清理。

## 9. Component 与 Presentation

页面结构由 `LoadedDashboard.layout_contract` 以并发安全方式惰性编译为唯一 `dataviz/layout-contract/v1`。当前 Dashboard v17 拥有 Section/View 顺序、模板、columns、span 和全局 gap；Presentation v2 只拥有 Theme、容器外观、Data Entry Component、visual renderer options 与资产。默认 Renderer、Server API、HTML manifest、AI context 和 validate 都消费这份 Contract。Custom Canvas 只公开稳定 Section/View mount points，不伪造任意 CSS 的静态网格。

默认 Presentation 使用文档流；删除 `presentation.yaml` 后 Dashboard 仍必须可读、可交互。样式扩展顺序是：

```text
默认组件 → 模板参数 → Theme token/css_class → 自定义 Renderer → 完整 Canvas
```

Component Registry v5.9.0 从 `src/dataviz/components/packages/` 扫描 Package。每个 Package 声明 owner、Schema、controller、adapter、功能 CSS、Story 和测试声明。`components check` 只校验这些元数据、资产与声明，pytest/浏览器 E2E 才执行行为。21 个 Package 均为 package-owned；14 个 `control.*` Package 独立承载 Data Entry Component，声明式 View/Section、Data Pipeline 与 Presentation 已迁入各自 owner，`declarative-runtime.js` 与 Runtime 中的重复实现已经删除。

`view.declarative` 的原生 Map 继续由唯一 Plotly Chart Service 托管：point 映射经纬度，region 通过 Dashboard allowlist 的 Workspace GeoJSON Asset 连接区域指标；Server 与 portable HTML 共用同一资产水合和 Renderer lifecycle。Overview → Detail 使用通用 compound Control writer，不增加地图事件协议。大型实体 Query Parameter 不新增组件或 Runtime owner，`query-parameter.entity-select` Scaffold 只组合已有 Parameter Domain、服务端 Lookup、紧凑 `multiple_select` 与 Source `query_filters`。

`presentation.shell` 还拥有 `control-panel.adaptive`：Server 与导出报告共享 Query Card、自适应列和内部滚动规则。Server Header 横跨 Sidebar 与 Workbench，Dataviz 品牌按钮拥有 Sidebar disclosure，Query 节点信号灯紧随品牌；Sidebar 和 Workbench 从 Header 下方开始。Header 右侧以 Dashboard Controls 和最右侧“查询 + ▼”分段按钮结束：主按钮执行 Query，箭头开合 Query Card，不另设 Parameters 按钮。Query Parameters 位于 Workbench 顶部的正常文档流，Card 内只保留紧凑标题和 label-over-input 网格，不重复查询动作。Card 与 Canvas 共享同一个响应式水平 gutter，不设置独立最大宽度。Server 首次默认展开并记忆 tab 状态，导出报告默认折叠以优先展示分析内容。展开时推开 Canvas，页面滚动时自然离开视口，不成为遮挡分析内容的 sticky/fixed Overlay。Server 的同源 Canvas iframe 通过 Shell Scroll Bridge 与外层形成一个顺序明确的纵向阅读面。Dashboard/Section/View Controls 才属于可由外部点击或 `Esc` 关闭的 Overlay。Query 的 `columns` 是最大列数，`column_width` 是目标轨道宽度；Runtime 读取 Card body 实际宽度计算有效列数，稀疏表单保持有界轨道并在右侧留白。单个控件只有显式 `span: 2` 才跨列。Scoped Controls 默认单列，只有显式配置才进入网格。Shell/Runtime 继续统一拥有值、校验、级联和执行状态。Shell 默认文案保持操作化和紧凑；解释框架概念的长文进入 Docs/Help/Diagnostics，不永久占据 Dashboard。

Shell 还拥有独立于 Dashboard Theme 的稳定视觉 token。Server 与导出 HTML 的 Header、Sidebar 与 Workbench 默认使用连续白色表面，只用极浅分割线确认导航边界；Dashboard Theme 只进入 Canvas、Section、View 与 Renderer。这个边界避免自定义画布或深色 Theme 改变全局导航和操作入口，也让默认 `business` Canvas 与 Shell 视觉连续、其他 Dashboard CSS 仍可独立表达。

## 10. 静态校验与 AI 开发入口

`dataviz validate` 不查询数据，覆盖：

- 严格 Schema、重复 ID、路径与 Adapter。
- SQL 参数与 Python 依赖。
- Query/Interactive DAG、Output 引用与环。
- Query Parameter 与 scoped Control 的 namespace、writer 和 consumer 作用域。
- trigger/export/Runtime 组合。
- Presentation、Component 和内容绑定。

主要 AI 入口：

```bash
dataviz docs quickstart
dataviz docs design-language --format json
dataviz schemas dashboard --full --format json
dataviz components check --format json
dataviz inspect context WORKSPACE DASHBOARD --focus interactive:<id> --format json
dataviz validate WORKSPACE --dashboard DASHBOARD --format json
```

错误应包含稳定 code、文件、字段、节点/依赖细节和修复建议。AI 不需要读取整个 Browser Runtime 才能新增普通看板。

## 11. 当前明确限制

- 这是可信单机执行环境，不是不可信代码沙箱，也不提供多租户 CPU/内存额度。
- 通用服务端分页、按需 Record Batch 和完整浏览器列式执行尚未实现。
- 21 个 Component Package 都已物理拥有 controller、adapter 和功能 CSS；共享 Runtime 主机也已按职责拆为构建源模块，但当前仍生成一个无模块加载开销的浏览器资产。
- Gallery 已覆盖 Control、View、Section 七状态和真实 10/100/1,000 选项；Chromium/Firefox/WebKit 还覆盖窄视口、弹层、滚动、键盘、ARIA、Perspective 恢复和三轮 dispose 组合。
- Token 节省是待真实任务评测的产品假设，不承诺固定数字。
- 成对评测工具已经实现；真实重复 trial 与结果发布尚待积累。
- 当前运行协调只支持一个 Dataviz Server 进程写一个 Workspace/报告目标；Runtime 并发上限变更需要重启。
- Plotly.js 4.0.0 与 TanStack Table Core 9.2.4 都由 Dataviz 固定并直接内置，Server 与 portable HTML 共用这些浏览器资产，不安装 Python `plotly`；Arrow 只有显式配置 Workspace 本地文件时离线，Perspective 当前仍依赖 CDN。manifest 的可移植性结论不覆盖自定义脚本自行发起的网络请求。
- Dataviz 会隔离 Adapter 并脱敏错误/日志，但可信 Python Source 仍有能力主动把秘密作为 Output 返回；这是看板作者必须遵守的边界。

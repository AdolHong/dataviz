# Changelog

## Unreleased

## 0.17.0 — 2026-09-01

- P3 将 Query Parameter 候选多选一次迁移为紧凑 `all/include/exclude/none` state；`all/none` 不展开全集，`include/exclude` 只保存有限 operands。Dashboard v14 统一使用 `default`，URL、Tab、Revert、Run、Result/Evidence、分享与 HTML 均封存同一 canonical state，候选全集不会进入结果资产。
- SQL Parameter Domain v2 一律先形成 Workspace 共享 immutable materialization；Parquet generation、SQLite registry、原子发布、reader pin、refresh lease、Server restart recovery、stale-while-revalidate、hard expiry、visibility scope 隔离与 preview-first prune 共同支持跨用户、Tab 和 Dashboard 复用，物化数据不污染 `dashboards/`。
- Parameter Lookup v1 只向 Browser 返回有界页面，支持规范化搜索、稳定排序、opaque cursor、exact total、有限已选项补标签和父级 `all/include/exclude/none` 本地谓词；级联、搜索与翻页不重新执行远端 Domain SQL，也不把完整关系下发浏览器。
- Source v4 提供规范 `value/selection/active/state/start/end` projection 与受限 `{{ dataviz_filter:name }}` 参数化 SQL predicate；`dataviz run` 可直接消费已知 canonical state，不隐式构建候选物化。Dashboard Bundle v1 复制共享 Domain 定义和 SQL，不复制凭据或 `.dataviz` 缓存。
- Query Panel Reload 只刷新共享候选 generation，不 Reset、不执行业务 Query；失败或 hard-expired Domain 只禁用相关 Picker，不再锁死全局导航。候选摘要按紧凑 state 显示“全部”或有限排除数，不再渲染数千个 Tag。
- Plotly Box Select 与 Lasso Select 可通过再次点击当前激活工具退出到普通查看模式；退出保留已有选区，不触发 clear/reset，Server 与 portable HTML 共享同一行为。State Summary 同步适配 Query Parameter v14，避免把 `{value, selection}` 显示成 `[object Object]`。
- 固定 10K/100K/250K Parameter Materialization/Lookup benchmark、604 项 Chromium-inclusive pytest、Runtime 生成资产一致性、Ruff、wheel/sdist/pip ZIP 内容与独立安装冒烟共同作为 0.17.0 发布门禁。

## 0.16.0 — 2026-08-31

- 0.16.0 发布门禁完整执行 594 项 Chromium-inclusive pytest，并由 Firefox、WebKit 各重复 53 项 Runtime E2E；三引擎共同覆盖 Host/Canvas 协议、Control writer/consumer、portable HTML、Renderer 生命周期及 Plotly 柱形/散点真实鼠标手势。Catalog characterization 现在排除本地 `.dataviz` 使用状态，async-host 边界测试也不再受先前 Playwright 主线程生命周期污染。
- 保留 Plotly 原生快速双击恢复 zoom scale，但 `plotly_doubleclick` 不再被 Dataviz 解释为 Control `reset`；Control 恢复只由工具栏中明确的 “Restore default selection” action 触发。Bound writer 在数据、layout 与 config 未变而仅 `selectedpoints` 改变时改用 `Plotly.restyle()`，不再以完整 `Plotly.react()` 重建 marker 命中层，避免散点重绘窗口吞掉下一次正常慢速点击。
- 修复 `chart-gallery` 连续点击省份收入柱形或订单/收入散点时偶发无响应：View writer action 的 render generation 现在只在同步入队时做准入校验，已经合法入队的 action 不再被前一个 action 引起的同 writer 自重绘误判为 `stale_view_generation`；writer DOM 实例真正被替换/移除和初始即过期的 action 仍会拒绝。真实 Chromium 覆盖重叠 Plotly action、柱形/散点连续鼠标切换与既有 portable provenance。
- TanStack Table 搜索框现在在 Renderer state 生命周期内保持唯一稳定 `id`，避免 `records` View 每次重绘时 Chrome 重复报告 “A form field element should have an id or name attribute”；该浏览器告警与 Control action 竞态本来没有执行因果关系。
- P1-B 将 `dependencies.py` 的 canonical derivation 按 Query/Interactive 图与 binding、Output/View 输入、Control writer/domain/impact、跨 Runtime invariant、reverse index 和 Query Parameter impact 提取为私有函数；`compile_dashboard_dependencies()` 仍只组装既有 Dependency Contract v10。`LoadedDashboard` 继续分别惰性持有 Dependency、Layout 与 Parameter Domain Contract，没有新增 `CompiledDashboard`、phase/service class、中间 cache、公开 DTO 或版本轴。
- 新增语言无关 Dependency v10 characterization fixture，冻结四个真实 Dashboard 的 v10 Contract、Layout v1、Runtime Manifest、Query/Interactive ExecutionPlan、Catalog/inspect projection 与关键 diagnostics；补充独立 lazy ownership、并发首次编译和失败不缓存 partial fact 的门禁。P1-B 不改变作者 DSL、公开/persisted/private wire shape，因此不升级协议。
- P1-D 将多 View linked brushing 作为一次明确契约迁移落地：Dashboard v13 允许多个 View 写同一 Control，Dependency Contract v10 输出按声明顺序稳定的 writer edges，Runtime v9 的 action/rejection 携带并校验 source View；所有 writer 仍只向唯一 ControlRuntime 发送 replace/set 语义的 typed action，不引入隐式 union、反馈事件总线或第二 reducer。
- State Snapshot v4 与 Analysis Result/Evidence v3 封存 current/applied writer provenance；consumer 只在对应 generation 真正成功时推进启动时捕获的 action/source View 证据。`chart-gallery` 的排名与散点共同驱动省份 Control，并由 Server、portable HTML 与不可变 Result 的真实 Chromium 回归验证选择、清空、重置、伪造 source 和 stale generation 边界。
- P1-A 将 Server/portable Control 状态收敛到同一 Canvas-hosted ControlRuntime：Shell 只发送 typed `set/apply`、镜像 operational snapshot 与可丢弃 checkpoint，不再推进 revision、协调 Control domain 或执行 per-key winner merge。private lockstep `postMessage` 逐消息校验 origin/source/dashboard/run/frame identity，并对重复 action、stale version、迟到 restore、错误 payload 与断连给出确定结果。
- Consumer 在 generation 启动时捕获完整 Control state，只有当前 View Renderer Ready 或 Transform 成功才推进 applied evidence；superseded、迟到 Ready、error/cancel/timeout 保留旧 evidence。Dependency Contract v9、Runtime v8、State Snapshot v3 与 Analysis Result/Evidence v2 一次迁移，Result/Export 可用 per-consumer `applied_control_state` 自包含证明实际结果值；Server Python 以 `control_state_not_canonical` 拒绝非完整 canonical snapshot。
- 建立 canonical protocol inventory/change record，并新增语言无关 `input-binding / control-filter / value-signature / consumer-revision / output-capability` conformance corpus；Python、Canvas Runtime 与 Web Component Adapter 共同消费同一组 expected/error code。
- 补齐 Query Input `value/present/intent/range part` 全链路，Browser binding signature 保留 projection，server-python Interactive 读取所属 immutable Query Run 的 parameter intents；`present(0)` 与 `present(false)` 均为 true。
- typed comparison 一次迁移到 Dashboard v12、Interactive Transform v4、Dependency Contract v8 与 Runtime v7：number/integer 数值比较、date 规范日期比较、text 拒绝词法排序、boolean 仅允许 equals/in，并统一零端点、空值和转换错误。
- canonical value signature 与 consumer revision 在三端共享安全整数、非有限数、序列化、stale/ahead 等边界；生成后的单一 Runtime bundle 额外执行 JavaScript 语法门禁。
- Browser `image/file` 在 portable snapshot 与 CLI Result 进入执行前返回结构化 `output_destination_unsupported`；live/portable interactive display 不被错误禁止。Browser Result 的 `text/html` 改为原生 bytes、MIME、扩展名与持久化 content hash，不再封装成 JSON 字符串。

## 0.15.0 — 2026-08-31

- 删除受限且职责重叠的浏览器 Python Runtime；Interactive Transform 只保留用于便携端侧数据加工的 `browser-js` 与用于完整 Python 生态和复杂计算的 `server-python`，同时移除相关 Worker、依赖校验、资产分发、导出分支、脚手架和测试夹具。
- Dashboard v11、Dependency Contract v7、State Snapshot v2 与 Browser Runtime v6 统一 Input State / Consumer Binding：Control 不再用 `selection/compute` 类型猜测行为，View 与 Interactive Transform 通过 `control_inputs.mode: filter | value` 显式消费同一 canonical `{value, revision, intent?}` 状态。
- Plotly、Table、Custom Renderer 与 Control Component 统一为类型化 writer action；Compiler 明确校验单 writer、consumer 输入、字段、空值策略与影响闭包，Runtime 只重绘真实受影响 View，并拒绝旧 generation 和注册契约漂移。
- State Snapshot 将 Runtime 原始 `applied_revisions` 按当前 Dependency Contract 规范化为 per-consumer `effective_revision / applied_revision / stale` 证据；Browser/Server 执行、HTML/Share、不可变 Result、`result inspect` 与 Evidence 贯通同一结构，未知或超前 revision 不会进入封存事实。
- Query Parameter Revert 现在以最后一次成功 Query 的 committed `{values, intents}` 为唯一目标，通过 Parameter Domain 拓扑一次性恢复级联候选和值，不执行正式 Query，也不回退声明 `initial`。
- 最新 Domain 缺少已提交值时，Resolver 保留该值并投影为只读 unavailable choice；Query Card 只有在 draft 真正偏离 committed values 或 intents 时才显示克制的恢复动作，完成后回到 Applied。
- `dataviz init` 与 Feature Showcase 全部改为显式 View `control_inputs.mode: filter`，新建 Workspace 可直接通过 `validate --strict`，不再依赖已删除的继承 Control 隐式筛选。
- 修复级联/树形 Control 初始化、Section/Repeat 路径投影、Header/Canvas revision 竞争、Progressive SSE 初始化、Server/Browser Interactive 注册与显式 View filter 等真实浏览器边界；429 项非浏览器测试、52 项 Chromium E2E，以及可切换引擎的 43 项 Firefox/WebKit Runtime E2E 均完整通过。
- `dataviz docs` 与 `dataviz-skill.md` 清除旧 Selection/Compute/PyProxy 叙述，统一说明 Control 只持有状态、consumer binding 决定 filter/value 语义。
- 四个示例 Workspace 通过 strict validate，21 个 Component Package（63 个组件、38 个 Story、75 个测试声明）通过检查；wheel、sdist、ZIP 分别在全新 Python 3.12 环境完成安装、Schema/Component 检查、`init → strict validate → report` 与无 Python `plotly` 依赖验证。

## 0.14.1 — 2026-08-30

- 统一 Parameter Domain 的作者边界：一张低/中基数有界关系表可投影多个候选池，每个 `value_field` 按 canonical value 自动去重；独立候选不声明 `depends_on`。
- focused docs、DESIGN、实现索引与 AI skill 不再使用高基数 `item_nbr` 候选池演示选择意图；Parameter Domain 必须适合完整加载，候选过多时重构业务参数或让已知 ID 使用 `multiple_input`。
- AI skill 的 Workspace Quickstart 对齐真实 CLI：`dataviz init` 直接生成可运行的 `hello` Dashboard；Scaffold 用于指定 Dashboard ID 或选择渐进式 recipe。
- README 明确 `result export` 只复制不可变 Result 中的原生 Artifact，不重新执行查询，也不转换格式。
- 生成资产、JavaScript 语法、四个示例 Workspace strict validate 与 Component Package 检查通过；Ruff、435 项非浏览器测试和 43 项 Chromium E2E 全部通过。
- wheel、sdist、pip ZIP 通过内容审计，并分别在独立 Python 3.12 环境完成 `install → version → schemas → components → init → validate → report`；三个环境均未安装 Python `plotly`。

## 0.14.0 — 2026-08-30

- Query Parameter `multiple_select` 的 committed state 现在同时封存 canonical values 与 `all_available | explicit` 意图；`explicit + []` 是唯一明确空集，不增加 `none`、`exclude`、loading 或 reset 等伪业务状态。
- Source、Dataset Transform 与 Interactive Transform 的结构化 `query_inputs` 新增 `{parameter: <id>, projection: intent}`，让 SQL/Python 能区分“当前范围全部成员”和“显式有限子集”；默认值投影继续保持原有短格式，Intent 只允许用于 `multiple_select` 且不能与日期 `part` 混用。
- Server、CLI Analysis Result、Interaction Result、持久化分享结果与 portable HTML 元数据共同保留 Query Parameter intents；Parameter Domain 仍只负责 Query 前候选发现，不进入 Result、Canvas Interactive DAG 或候选成员校验。
- 修复 Parameter Domain 422 后旧 Dashboard 表单校验阻断全局导航的问题：切换看板先取消旧请求，并以 best-effort 保存旧草稿；刷新仍可重试当前看板，但损坏 Domain 不再锁住整个 tab。
- 运行时静态资产禁缓存改为纯 ASGI Middleware，消除浏览器取消请求时 Starlette `EndOfStream → No response returned` 的错误链。
- DESIGN、产品架构、focused CLI docs 与分析 skill 明确两态 Intent、固定字段 Domain 投影、同表多候选自动去重和有界完整候选池原则。
- Ruff、434 项非浏览器测试与 54 项 Chromium E2E 通过；新增真实浏览器回归覆盖 Domain 失败、刷新后跨 Dashboard 导航，以及 `all_available/explicit` 从 Query Panel 到封存 Run 的传递。
- wheel、sdist、pip ZIP 完成内容审计，并分别在独立 Python 3.12 环境通过安装全流程；三个环境均未安装 Python `plotly`。

## 0.13.0 — 2026-08-30

- Dashboard Contract 升级为 v10，新增严格 `dataviz/parameter-domain/v1`：一个 Query 前置 SQL Domain Table 可为多个 Query Parameter 投影类型化候选，并通过直接父参数映射完成共享省市等层级级联。
- Server Parameter Resolver 提供行数上限、类型化 Choice、session/TTL cache key 和稳定诊断；AI 可按需使用 `dataviz parameters options` 将原始多列候选表封存为 `options_id`，终端默认只预览 10 行，再由 `parameters filter` 基于快照筛选、选列和分页而不重跑 SQL。`dataviz run` 不隐式执行 Domain、不做候选成员校验，只校验参数值契约。Dependency Contract 升级为 v6，只在 Query 区域公开独立 Parameter Domain Contract，不把它写入 Canvas Runtime Manifest。
- Query Panel Shell 支持请求 generation、tab 草稿恢复、有效交集/initial/主动空集协调、级联 loading 与 RUN 门禁；动态参数看板在“查询参数”右侧显示克制的 reload，强制刷新候选但不执行 Query、不清空有效选择。
- 动态候选加载结束会同步恢复自定义 Select 的交互状态；浏览器回归直接点击可见的省份、城市候选，避免隐藏原生 `<select>` 的强制操作掩盖“候选可见但无法点击”。
- portable HTML 与分享链接继续只消费封存 Result 中的 committed Query Parameter；不嵌入 Domain SQL、候选表、Adapter、cache receipt 或刷新 endpoint，也不把 Parameter Domain 接入 browser-js Interactive Runtime。
- Feature Showcase 新增共享省市参数域看板；机器 Schema、focused docs、分析 skill、产品架构与参数编辑器同步当前边界。
- 432 项非浏览器测试与 53 项 Chromium E2E 通过；四个示例 Workspace strict validate、21 个 Component Package（65 个组件、39 个 Story、77 个测试声明）和真实 `run → Result → report` 冒烟通过。
- wheel、sdist、pip ZIP 通过内容审计，并分别在独立 Python 3.12 环境完成安装全流程；归档包含 Parameter Domain/Options 实现与浏览器交互修复，不包含 Workspace 缓存、凭据、维护者评测工具或 Python `plotly`。

## 0.12.3 — 2026-08-30

- 重新审计并收敛机器可读 `dataviz docs`：Quickstart 对齐 `init` 生成可运行 `hello` Dashboard 的真实行为，Shell 文案统一为 `RUN` split control，Table/Perspective 职责、Selection 初始化与动态候选恢复策略同步当前实现。
- 图表文档明确 Server/Transform、Browser Adapter 与 Plotly.js 的所有权边界；strict-schema 和 release topic 补齐 Layout Contract、State Snapshot、Plotly.js 4.0.0、TanStack Table Core 9.2.4 及快速迭代浏览器门禁。
- 新增文档残余回归，拒绝 ECharts/Vega、旧 CLI、旧 Schema/Runtime、旧 Query 按钮文案和过期组件职责重新进入正式 docs。
- Ruff、423 项非浏览器测试与 52 项 Chromium E2E 通过；四个示例 Workspace strict validate、21 个 Component Package（65 个组件、39 个 Story、77 个测试声明）和实际 `run`/`report` 冒烟通过。wheel、sdist、pip ZIP 完成内容审计，并分别在独立 Python 3.12 环境通过安装全流程；三个环境均未安装 Python `plotly`。

## 0.12.2 — 2026-08-30

- Plotly Selection Binding 只在真实用户操作完成后提交；绑定图表默认仅显示矩形选择、套索选择和恢复默认选择，未绑定图表不显示空工具栏。空 `plotly_selected` 不再覆盖刚完成的点选，click、area select 与 double-click 会取消尚未提交的旧动作；`clear` 与 `reset` 分离，恢复默认选择不再制造显式空集。
- 删除产品源码、Schema、示例、文档和发行资产中的 ECharts/Vega 分支；Plotly 保持唯一作者图表接口，普通 Table 继续使用 TanStack Table Core。
- 浏览器图表 Runtime 直接固定并内置 Plotly.js 4.0.0；Server 与 portable HTML 共用同一资产，删除仅用于转运 JS bundle 的 Python `plotly` 依赖，并显式关闭 v4 默认云端分享入口。
- TanStack Table 搜索框支持中文输入法 composition 生命周期：拼音组合期间不重绘，候选文字提交后再过滤；`source-lab` 右侧图表移除独立灰蓝背景，与同页 Plotly 卡片统一表面颜色。
- README 收敛为产品理念、安装和两条 Quickstart；DESIGN 清除旧版本/旧 CLI/旧 Runtime 残留，plan 只保留当前基线与真实待办。
- 快速迭代发布默认执行 Chromium 完整 E2E；稳定发布、跨浏览器敏感变更或明确要求时再重复 Firefox/WebKit，避免把尚未执行的跨浏览器验证写成发布事实。
- 421 项非浏览器测试与 52 项 Chromium E2E 通过；四个示例 Workspace strict validate、21 个 Component Package（65 个组件、39 个 Story、77 个测试声明）和实际 `run`/`report` 冒烟通过。wheel、sdist、pip ZIP 完成内容审计与独立 Python 3.12 安装全流程冒烟。

## 0.12.1 — 2026-08-30

- Plotly Control Binding 的框选改为仅在 `brushEnd` 提交一次；拖动过程中的高频 `brushselected` 只保存预览，不再因首个命中点触发 View 重绘并中断手势。

- Replaced the hand-written default Table behavior with locally bundled `@tanstack/table-core` 9.2.4, added polished Dataviz defaults for sorting/search/pagination/pinning, and exposed managed plus unrestricted `context.tables.tanstack` APIs to Custom Renderers.

- 文档与机器可读 `dataviz docs` 将 Plotly 固定为唯一作者图表接口；作者只关心数据口径、视觉编码与交互目标，从声明式模板逐步进入 trace/layout/config 覆盖和拥有完整 Plotly.js API 的 Custom Renderer。官方文档与 Gallery 用于视觉和 API 参考，项目 Recipe 只保留少量完成 Dataviz 生命周期适配的样例。

- 新增 `dataviz-skill.md`，把快速构建、渐进式文档、分析问题设计、Catalog 复用、Result-centric 执行和长期维护整理为一份可直接交给 AI 的工作流。

- 大型 Canvas Runtime 与 Workspace Loader 按 owner 边界拆分为可维护源码模块，由确定性构建和兼容 façade 保持单一浏览器资产、稳定错误 code 与既有 CLI 行为。

## 0.12.0 — 2026-08-29

- 公开 CLI 收敛为 `catalog → run → result → evidence`：删除 `analyze`、`query`、`output`、`compute` 和产品内 `authoring` 分组；工程导航改为 `tree`，结构检查归入 `inspect`，清理改为安全预览优先的 `prune`。
- 新增 `dataviz/target-reference/v1`。Catalog、Describe、Run、Result、Evidence 和 next action 统一使用 `dashboard::source|dataset|interactive|view:...` 物理引用，不再生成或解析 hash 短别名。
- `dataviz run WORKSPACE TARGET` 同时支持 Dashboard、Source、Base/Derived Output 和 View；显式执行进入终态后封存不可变 `ready|partial|failed|cancelled` Result，preflight 错误不创建 Result。
- Result Store 统一写入 `.dataviz/results/`，新增 `result list`；show/inspect/export、Report 与 Evidence 只读既有 Result，不重新执行。Dashboard report 保留便利入口，但会先执行并封存 Result。
- Share 操作同步封存可追溯 Result；`prune` 统一管理 Result、Execution Artifact 与缓存，默认只预览，`--apply` 才删除，分享缓存暂不自动清理。
- `components list/show/check/gallery`、`renderer test`、`benchmark runtime` 与 `inspect context/dependencies/layout` 形成稳定命令域；`validate` 与需要浏览器的 `visual-check` 继续保持独立成本边界。
- AI Authoring 成对评测、真实 Token/会话日志与 context benchmark 已移到仓库专用 `tools/authoring-evaluation/` 项目，使用独立 `dataviz-authoring-eval` 入口，不进入正式 Wheel、sdist、pip ZIP 或产品帮助。
- README、DESIGN、Plan、机器 Schema、focused docs 和回归测试同步到 0.12.0 对象模型。
- 402 项非浏览器测试通过；52 项 E2E 在 Chromium、Firefox、WebKit 三引擎分别执行并通过。四个示例 Workspace 通过 strict validate，21 个 Component Package（64 个组件、39 个 Story、76 个测试声明）通过检查；wheel、sdist、pip ZIP 完成内容审计与独立 Python 3.12 全流程安装冒烟。

## 0.11.0 — 2026-08-29

- Analysis discovery 改为语义优先：`analyze all/search` 默认显示业务意义、粒度、可信度、参数契约、消费 View 与命中原因；旧式单行索引保留为显式 `--compact`。Source/View 命中会投影到可复用 Base/Derived Output，不再与主要口径平铺竞争。
- 运行前探索由 `analyze describe WORKSPACE REFERENCE...` 统一承载，可在同一 Catalog generation 中批量描述多个引用、保持输入顺序、去重并返回逐项失败；它不会执行 Source 或创建 Result。
- Analysis 短别名改为裸 `src_.../base_.../drv_.../view_...`；旧 `@alias` 返回稳定 `analysis_alias_prefix_removed` 诊断和可直接复制的 replacement。
- `analyze run` 默认输出高密度文本和 10 行预览，同时完整执行并原子封存不可变 `.dataviz/analysis-results/<result-id>/`。新增 `result show/inspect/export`，分别负责无重跑分页、渐进 provenance 和单个原生 Artifact 复制；run 不再承担 Arrow/Parquet 转换或任意目标路径导出。
- Result index 可由不可变 manifest 重建；CLI 每日最多一次 best-effort 清理超过 30 天未访问的托管 Result。直接 File Source 只保存实际读取文件的 path/size/hash/reader 收据，文件变化或缺失时拒绝静默读取新内容。
- 新增 `dataviz/analysis-describe/v1` JSON Schema，并覆盖语义摘要、批量 describe、Result 原子发布/分页/导出/索引重建、File Source hash 收据以及 Browser Result 原样导出回归。
- 449 项当前测试契约通过；52 项 E2E 在 Chromium、Firefox、WebKit 三引擎分别通过。四个示例 Workspace 通过 strict validate，21 个 Component Package（64 个组件、39 个 Story、76 个测试声明）通过检查；wheel、sdist、pip ZIP 完成内容审计与独立 Python 3.12 安装冒烟。

## 0.10.0 — 2026-08-29

- 新增 AI Analysis Plane：`dataviz analyze all/search/describe/run` 可通过稳定裸别名搜索、批量描述并执行 Source、Base Output、Derived Output 与 View 输入；各类 Output 共用现有 Runtime 和机器可读 provenance。
- P1 Analysis Plane A–E 完成：新增 Output `semantics`/`assurance`、版本化机器 JSON Schema、public/internal 与可信发现边界、稳定 Analysis 错误 envelope、Evidence 和 Promote dry-run。
- Workspace Catalog 补齐并发 refresh 去重、构建失败回退旧 generation、Server watcher 异步刷新和 stale diagnostics。
- 新增 `.dataviz/usage.sqlite` 成功行为统计；Server Query 与 AI `analyze run` 使用 WAL、原子 UPSERT、首次初始化的有界锁重试和 best-effort 故障隔离，统计文件不影响 fingerprint、Hot Reload 或成功结果。
- `analyze all/search` 对实现资产、Runtime、Adapter 引用、Query bindings 与 Output Contract 完全一致的口径做精确折叠，支持 occurrence 展开、关闭折叠和折叠后的 Top N；不推断 SQL 语义等价。
- public 或 reviewed/certified SQL Output 的 `SELECT *`/`table.*` 产生稳定 warning，`count(*)` 不误报；Scaffold 与示例改用显式字段投影。
- `analyze run` 使用原生 Parquet/Arrow Artifact、输入 Artifact provenance、summary/debug/full 分层、View presentation mapping，以及 `--also` 单浏览器会话批量 Derived 提取；格式转换不再暴露为 run 职责。
- Browser Analysis 默认使用隔离 Context 并阻止非本地网络，记录 launch/page-ready/runtime-ready/transform/extraction 分段耗时；可复用 Arrow Output 优先通过 Arrow IPC 提取。
- 新增 `dataviz/analysis-overlay/v1`：`analyze run --overlay FILE|-` 可一次性替换 SQL、File Source、Python/JS Transform 及 code dependencies；`--dry-run` 先检查影响范围，正式执行不写回 Dashboard/Catalog，并使用独立缓存 salt 与 Analysis Run manifest。
- `analyze describe --detail full --include-code` 可批量查看目标闭包的定义、路径、hash 与已脱敏的小型代码资产；大型数据文件不内联，也不会执行 Source。
- Dashboard Contract 升级为 v9：Query Parameter、Selection 与 Compute 的所有 Select 统一使用 `initial`。多选支持 `all | empty | values`，单选支持 `first | empty | value`；非 Select 输入继续使用 `default`。
- 动态 Selection 候选域采用混合协调策略：优先保留仍有效的用户选择；原非空选择完全失效时恢复 `initial`；用户主动清空始终保留；`all` 意图继续跟随完整候选域。
- `visual-check` 提供独立可选依赖 `pip install "ai-dataviz[visual-check]"`；缺少 Playwright 包或浏览器时，CLI 直接返回可复制的安装命令。
- `dataviz docs --task` 新增 `cascading-selection`、`view-filter` 与 `browser-compute` 聚焦入口，分别返回最小示例、允许字段、常见错误和验证命令。

## 0.9.2 — 2026-08-28

- CLI 文档新增按任务/Component 的机器可读作者路由；默认 minimal 只披露 `Adapter → Source → View → Layout`，interactive 与 custom-renderer 按需加入各自的传递契约。
- Scaffold Catalog 升级为 v2，并新增可直接运行的 minimal、interactive、custom-renderer Workspace profiles；三条路径分别回归 `validate → report → visual-check`。
- `visual-check` 不再要求已设计为隐藏的 Query 状态文案可见，只等待其 Runtime 状态进入 Ready。

## 0.9.1 — 2026-08-28

- 默认 Table 不再为行数单独占用一条元信息行；确实需要时可显式启用 `options.show_count: true`。
- DatePicker/RangePicker 改用统一的可编辑 ISO 日期输入和 Dataviz 日历；连续八位数字自动分段，年/月可直接跳转，Range 不再重复显示已选范围。
- Query Parameters 使用有界目标轨道；参数较少时不再被 `1fr` 强行拉满整行，窄屏仍自适应为单列。
- 日期默认值统一为独立 Date Atom：单日期编辑器只显示“固定/相对”模式与一个当前值；Range 的开始、结束各自选择模式，因此支持固定开始日与相对结束日混用。旧 `start_offset/end_offset` 范围对象不再接受。
- Server 与导出 HTML 通过 `presentation.shell` 共用 Header 高度、基础字体、Query/Control Panel 表面、字段标签和输入尺寸；两个 Host 保留能力差异，但不再呈现两套默认视觉。
- Server Shell 的 Header 现在横跨整个屏幕，统一承载可点击的 Dataviz Logo、品牌名、Query 节点信号灯和操作区；点击 Logo 即可展开/收起其下方 Sidebar。删除独立 Navigation 按钮和 Sidebar 内重复的 “Dashboards” 标题。
- Sidebar 删除重复的 `+` 新建目录按钮及其空工具栏；在 Sidebar 空白处右键仍可新建目录。
- Query Parameters 改为按 Panel 自身宽度计算列数：`columns` 只定义 1–6 的最大列数，新增 `column_width` 定义 160–600 px 的最小轨道宽度（默认 280）；Dashboard/Section/View Controls 默认保持单列，只有显式配置才并排。
- 导出 HTML 的便携式 Header 现在保留紧凑的 Dataviz Logo 与品牌名；它属于 `presentation.shell/report.brand`，不会把 Server 的 Sidebar、导航、Reload 或诊断操作复制进报告。
- Dependency Contract 升级为 v5，并为每个 View 编译唯一拓扑序 `pipeline_nodes`。Header 信号灯只表示 Source/Dataset Query 层；View 在 Renderer 类型标签左侧按需显示自身上游节点与 Renderer 状态，Ready/Not run 自动隐藏，Running/Stale/Error 等状态可直接定位分支故障；导出 HTML 不重复展示已固化的 Source Ready 灯。
- Dashboard/Section/View Controls 托盘移除重复的 Controls 标题、DATA/LOGIC 标签、Selections/Calculation 分组标题、彩色竖线和影响 View 计数；Runtime 仍保留完整类型与影响契约，默认界面只展示业务字段和组件。
- Server 与导出 HTML 收敛为安静白色 Shell：Header、Sidebar、Workbench 与默认 Canvas 形成连续表面，移除 Canvas 外层卡片、灰色沟槽与强阴影；默认 `business` Theme 改为白色画布、轻边框和靛蓝分析强调，绿色只保留给 Ready/成功状态。
- Feature Showcase 保留自定义布局能力，但统一为中性白色底、轻边框和靛蓝分析强调，不再以紫色画布、黑粗边与多色大块作为项目第一印象。
- 导出 HTML 的 Parameters 默认折叠，打开报告时直接展示分析内容；Server 仍首次默认展开并记忆当前 tab/Dashboard 状态。
- Query Parameters 托盘移除重复的参数数量、Run ID 状态和内部分割线，只保留字段；宽屏默认上限从四列调整为六列，并响应式降为 5/4/3/2/1 列。`control_panels.*.columns` 同步扩展为 1–6。
- Server 与导出 HTML 的 Parameters 从固定/浮动弹层改为 Header 文档流托盘：展开时推开 Canvas，滚动时自然离开视口，不再持续遮挡看板上半部分。
- Server Canvas 增加 Shell Scroll Bridge：滚轮先滚走外层 Parameters，再进入 iframe 看板；反向滚动按相反顺序恢复，消除两个纵向滚动区的顺序错乱。
- 保留紧凑 sticky 操作栏；Query 参数仍由 split control 显式开合，外部点击与 `Esc` 不会误收起。
- 精简原生 Shell 的重复编号、口号和教学文案，保留必要操作、状态以及 Dashboard 自己声明的业务内容。

## 0.9.0 — 2026-08-27

- Query Parameters 在宽屏使用占满可用宽度的四等分轨道，不再以 1396px 封顶表单并留下大片空白；窄屏逐级降为 3/2/1 列。
- Checkbox Group 收紧为 2–5 个并列选项的直接多选，移除默认 All/Invert/Clear 工具栏；6 个及以上的平面候选域自动使用 Select，显式将超限静态候选域绑定到 Checkbox Group 会产生 Semantic Validation warning。

Dataviz 的 package、DSL、Component Registry 与浏览器 Runtime 分别版本化。这里记录使用者可观察到的变化；字段细节以 `dataviz schemas` 和 `dataviz components` 为准。

## 0.8.0 — 2026-08-26

### Unified Renderer lifecycle

- Plotly 与 Perspective 统一遵守平台行为矩阵：`mount → update → empty → restore → interaction → resize → dispose → export`；Custom Renderer 作者接口仍保持精简的 `validate → mount → update → dispose`。
- 首屏 Server/HTML bootstrap 不再绕过 View Package，而是按真实 View ID 注册到同一实例状态表；后续更新、空集、恢复、Resize 与销毁因此只有一个生命周期 owner。
- 空数据成为同步终态：View 立即发布 Empty 并释放旧实例；数据恢复时创建唯一的新实例，不保留旧坐标轴、图例、透视状态或事件监听器。
- Perspective Worker、Table 与 Viewer 改由单个 Renderer 实例共同拥有和释放，不再跨 View 生命周期共享 Canvas 全局 Worker；加载、建表、恢复、更新与销毁均有有界终态，外部资产或引擎停滞时回退普通 Table，不会永久 Loading。
- Plotly 交互监听和 ResizeObserver 由平台 Chart Service 管理，重复 update 不会叠加回调；Perspective 的 resize/dispose 也进入同一指标与错误边界。
- Runtime 暴露 mount、update、empty、restore、interaction、resize、dispose、failed 与耗时指标，便于 Gallery、Visual Check 和浏览器回归定位生命周期缺口。

### Component contract and verification

- Component Registry 升级为 `4.2.0`，新增 `view.renderer-lifecycle` 契约；`view.declarative` 与 `renderer.custom` manifest 明确区分作者 hooks 和平台矩阵。
- Chromium、Firefox、WebKit 在 Server Canvas 与 portable HTML 中共同覆盖 Plotly、Perspective 的八阶段矩阵，并保留 Plotly 交互与 Perspective 空集恢复专项回归。
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

- Dashboard 升级为 `dataviz/dashboard/v8`、Presentation 升级为 v2、Dependency Contract 升级为 v4、Browser Runtime 升级为 v5，并新增 Layout Contract v1；不提供兼容分支。
- Selection 统一保存 `{intent, values}`；`explicit + []` 是明确空集，`all_available` 随候选域扩张。optional Single Select 支持 Clear，required Single 禁止 clearable。
- View 可用一条 `control_binding` 双向绑定现有 Selection Control；一个 Control 最多一个 writer View，Plotly/Table/Custom 共用类型化 Action 和 canonical commit。
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

- browser-js 未显式声明时默认 `trigger: auto`，server-python 默认 `apply`；Scaffold 与文档使用同一规则。
- `query`、`output`、`compute` 默认输出紧凑 `dataviz/cli-result/v1`，`--detail debug|full` 才展开执行证据。
- Component Registry 升级为 4.1.0；Custom Renderer 可通过 `context.charts.plotly` 复用平台 Theme、滚轮、Resize、Update 与 Dispose。
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
- Server、导出 HTML、Data Entry Control、Plotly、普通 Table 与 Perspective 统一消费 Theme token；Renderer 的显式 options/config 继续拥有更高优先级。
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
- Server Python 的 `context.table()` / `context.input()` 与 browser-js 的 `context.inputs` 看到相同的已选样本；`context.selections` 仍可用于日志、标签和确定性分支。
- `data.pipeline` 拥有 Browser Selection-before-Compute 边界，Server 使用同契约的 `ExecutionContext` 筛选；无关表输入保持不变。

### Verification

- 新增 Server 与 Browser 回归，证明 Selection 先裁剪样本、Compute 只在已选数据上运行，且无关 View 不重绘。
- 全量 Python 测试、Browser Runtime E2E、Component Package 检查与仓库示例静态预检纳入发布验收。

## 0.2.0 — 2026-08-24

### Breaking architecture

- Dashboard 与 Browser Runtime 升级为严格的 `dataviz/dashboard/v2`、`dataviz/runtime/v2`；查询阶段使用 Dataset Transform，取数后计算使用 Interactive Transform。
- 新增独立 Compute Parameter，以及服务端 Python 与浏览器 JavaScript Interactive Runtime；两者统一产出 Named Output。
- Query DAG 与 Interactive DAG 分离；Query Run 固化 Base Output，交互结果按 tab、Dashboard、Run、Transform 和 generation 隔离。
- HTML Export 强制声明 `interactive`、`snapshot` 或 `unavailable`，不再把 Server Python 伪装成离线交互。
- 删除旧实验性 Transform 字段、自动迁移命令和 Runtime 兼容分支；仓库示例与测试直接使用当前严格契约。

### Added

- 新增 `dataviz compute`、Compute Control、Interactive Compute API 和 browser-js Worker。
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
- 源码 CLI 文档固定使用 non-editable `uv sync --reinstall-package ai-dataviz`，规避部分 macOS/Python 组合忽略 hidden editable `.pth` 导致的 `ModuleNotFoundError`；发布 smoke 仍使用独立干净环境。
- 声明式 View、browser-js Worker 与 Custom Canvas 的数值聚合改为线性 reducer，大表 min/max 不再因展开数组超过 JavaScript 参数上限而崩溃。
- Arrow Table 作为 Metric 输入时不再被误判成 scalar 并显示 `[object Object]`；没有 descriptor 的 View 进入明确的 `empty` 终态。
- Live Canvas 处理 node/run cancelled；失败或取消的终态 Run 可重新打开并显示分支错误，不再因为缺失 Output 返回 500 或永久停在 rendering。
- 后台保留策略不再清理仍被活动 Interaction 消费的 Query Run 与缓存，避免长时间模型/运筹计算被误取消。
- Source/Dataset 缓存键补入 Dashboard 与节点身份，并继续由 tab session namespace 隔离；Server Interactive 只读取所属 Query Run 的不可变 Artifact，不会因 Selection/Compute 变化重新查询 Source。

### Documentation

- 仓库首页改为面向首次访问者的简明 README；稳定产品设计收敛到 `DESIGN.md`，未完成工作收敛到 `plan.md`，三者都会进入后续源码 ZIP 与 sdist。
- 删除设计文档中的安装手册、旧版本测试快照和已完成里程碑；明确当前未完成边界、放弃的旧方向与按真实需求触发的候选能力。
- 明确浏览器与服务端 Runtime 的适用条件，以及 server-python 无法在独立 HTML 重算的边界。

## 0.1.4 — 2026-08-23

### Fixed

- 默认 View Shell 现在实际渲染 `description`，并统一覆盖 Table、Perspective、Plotly、Custom Renderer 与 Repeat View；动态 Selection 文案原地更新，Server 与导出 HTML 保持一致。

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

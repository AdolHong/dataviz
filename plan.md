# Dataviz 实施计划

更新时间：2026-08-31

稳定设计见 [DESIGN](DESIGN.md)，代码入口见 [当前实现索引](docs/product-architecture.md)，使用者入口见 [README](README.md)，已完成的版本工作见 [CHANGELOG](CHANGELOG.md)。本文件只记录当前基线、尚未完成的工作与按真实需求触发的候选项，不再重复保存历史迁移清单。

## 当前基线

| 领域 | 状态 | 当前结论 |
| --- | --- | --- |
| 数据执行架构 | 核心语义与 P0 跨 Runtime 一致性已完成 | Query DAG、Interactive DAG、Control/View 影响关系、Named Output、状态隔离和导出边界已经进入版本化 Dependency Contract；共享 conformance corpus 证明 Python、Canvas 与 Web Component 对 P0 契约的相同解释。 |
| Control 与 Linked Views | P1-A/P1-D 已完成 | `{value, revision, intent?}` 是 canonical Control state，View gesture 与 Header 都只是 typed action producer；Server/Portable 共用托管于 Canvas 的唯一 ControlRuntime。一个 Control 可由多个经 Compiler 校验的 View writer edge 写入，action/rejection/applied evidence 保留 source View。 |
| Input State / Consumer Binding | v13/v10/v9 迁移与 conformance 已完成 | Query Parameter 与 Control 保留两个生命周期入口并共用 typed value contract；`value/present/intent/range part`、零边界、typed comparison、canonical signature、generation-start applied evidence、writer provenance 与 consumer revision 已由共享 fixtures/浏览器回归固定。 |
| Layout 与最终配置 | 已完成 | Dashboard v13 拥有结构；Layout Contract v1、Semantic Validation、`inspect layout`、Server、HTML 与 AI context 使用同一编译结果。 |
| Renderer 与组件 | 当前范围已完成 | Plotly 是唯一作者图表接口；普通 Table 使用 TanStack Table Core；Perspective 只用于终端用户现场多维探索；21 个 Component Package 均为 package-owned。 |
| AI Analysis Plane | 当前范围已完成 | `catalog → run → result → evidence`、物理 Target Reference、不可变 Result、Overlay、Evidence 与 Promote dry-run 已落地。 |
| AI 开发效率评测 | 工具完成，真实试验暂缓 | 维护者评测工具已与正式产品隔离；没有真实成对试验前不发布 Token 或效率结论。 |
| 规模与浏览器可靠性 | 当前范围已完成 | 固定 10K/100K/1M 基准和三浏览器契约矩阵已有可复现证据；快速迭代发布默认执行 Chromium 全套，稳定发布、跨浏览器敏感变更或明确要求时再执行 Firefox/WebKit。 |
| Query Parameter 与 Domain | P1-E 已完成 | Query 前置 Domain 以 Contract/Resolution v2 明确分开 `options.depends_on` projection edge 与 Domain `query_inputs` query edge；同 snapshot 级联在浏览器本地事务式完成，query edge 才获取新 snapshot，叶子和独立 `multiple_input` 不触发 Domain 工作。完整 relation projection 受 50,000 rows / 8 MiB 双预算约束，超限稳定失败且不截断、不回退。 |
| Compiler 与应用边界 | P1-B/P1-C 已完成 | `LoadedDashboard` 继续分别持有和缓存三份 canonical lazy Contract；Contract 间已有 derivation dependency 保持显式、单向。`dependencies.py` 已按语义提取私有 derivation 函数，没有增加 owner/wrapper/phase class；`RunRequest → run_analysis() → canonical AnalysisResult` 复用现有 Catalog resolver 与 `AnalysisResultStore`，没有增加 Runner class。 |
| 当前发行基线 | 0.15.0 之后的 P0、P1 与当前 P2 范围实现完成 | Input State / Consumer Binding 断代、browser-python 删除、Domain locality、显式 Target 应用函数、单一 Control authority、多 View linked-brushing、Compiler 内部模块化、当前协议版本门禁与严格 Analysis producer 已落地。 |

当前开发基线：Package `0.15.0` 之后的工作树、Python 3.11–3.14、`dataviz/dashboard/v13`、`dataviz/parameter-domain/v1`、`dataviz/parameter-domain-contract/v2`、`dataviz/parameter-domain-resolution/v2`、`dataviz/presentation/v2`、`dataviz/source/v3`、`dataviz/dataset-transform/v3`、`dataviz/interactive-transform/v4`、`dataviz/dependency-contract/v10`、`dataviz/layout-contract/v1`、`dataviz/state-snapshot/v4`、`dataviz/runtime/v9`、`dataviz/analysis-result/v3`、`dataviz/analysis-evidence/v3`、Component Registry `5.6.0`。当前 0.x Runtime 是 exact-current、同 package lockstep，没有 capability negotiation。P1-D 已按 P0.0 决策一次迁移 authoring、private wire 与 persisted evidence；以后缩小合法 Output 声明、改变持久化 shape 或 public wire 仍必须分别判断版本，不能被“bugfix 不升版”笼统覆盖。

## 当前优先级

### 跨阶段门禁：抽象必须证明价值

本计划不以减少或增加类、协议、消息、文件数量为目标。真实目标是增强可组合的表达能力与可验证的通信可靠性，同时减少同一语义的 owner/解释器数量。所有 P1 candidate 在实现前记录以下证据：

- 当前真实问题：语义漂移、双 authority、不可恢复通信、非法状态，或被 Adapter 隐藏的应用用例；“文件太长/架构图不整齐”单独不构成立项理由。
- 最轻可行形态：说明为什么局部函数、typed data 或现有 owner 不够；没有独立 state/lifecycle/substitution 时不新建 class，没有独立 producer/consumer/persistence 时不新建 protocol。
- 唯一语义边界：owner、invariant、允许/禁止的依赖、失败方式和 public/private/persisted 分类；新抽象不得与现有对象竞争同一事实。
- Characterization 与反例：先固定 current behavior，再用至少一个会在缺少该边界时失败的 parity、retry、stale、diagnostic 或 Result case 证明收益。
- 退出条件：若 spike 只增加 forwarding、DTO 转换、cache/version 轴或同步步骤，却没有消除重复解释、建立可靠性边界或支持新的安全组合，就撤销 candidate，不为了完成计划保留空层。

逻辑步骤不机械等于 class，应用责任不机械等于 service，跨 frame message 不机械等于公共协议。反过来，只要 typed action、revision 或 typed data 对表达力/正确性确有必要，也不因为“抽象变多”而拒绝。

### P0：恢复并证明跨 Runtime 协议一致性（已完成）

目标：先把已经承诺的 `value / present / intent`、Control filter、revision 和 Output destination 语义钉成一组可执行事实，再修复 Python、Canvas Runtime 与 Web Component 的实现漂移。本阶段不重新设计领域模型、不新增通用状态框架；每项变化先区分实现修复与新语义。

#### P0.0 建立最小协议边界与升版门禁

- [x] 对本轮触及的 Dashboard/Transform、Dependency projection、Runtime Manifest/Event/Web Component、State Snapshot、Analysis Result 与 Output destination error 做最小 inventory，登记 `boundary / producer / consumer / persisted / current revision / strictness`。这是实施门禁，不等待 P2 扩展登记范围。
- [x] 每个 change record 明确标成 `implementation parity fix / additive-but-current-reader-incompatible / semantic breaking / private lockstep refactor`，并写出 bump/no-bump 理由；当前不存在 capability negotiation，不得把它当作兼容方案。
- [x] 冻结判断：补回 payload 已有的 Query projection、修复 `0` truthiness 不机械升版；typed comparison coercion、在通用 validate/compiler 缩小既有 Output 声明、持久化 `applied_control_state`、公开 Host channel 与公共客户端重命名必须分别判断 revision/兼容策略。
- [x] 后续版本投影继续消费同一 canonical metadata source；P0 不另建长期手写协议清单。

#### P0.1 冻结语言无关的 conformance corpus

- [x] 建立五组小型 JSON fixture：`input-binding`、`control-filter`、`value-signature`、`consumer-revision`、`output-capability`。Fixture 是规范实例，不是新的产品协议或万能执行 DSL。
- [x] 每条 case 只保存一份 `id / operation / input / expected`；失败 case 保存稳定 `expected_error_code`，不得让 Python 与 JavaScript 各维护一份答案。
- [x] 为 Python projector/filter/output validator、Canvas Runtime source module 和 Web Component Adapter 各提供薄 runner；不在 Python 中重写 JavaScript，也不从生成后的 bundle 反推源语义。
- [x] 覆盖 `value / present / intent / range part`，`null / "" / [] / 0 / false`，`equals / in / between / contains / gte / lte / gt / lt`，多字段 path、candidate intent、canonical signature、Control action/revision，以及 Output kind × destination capability。
- [x] 明确 `present(0)` 与 `present(false)` 为 true。`range_input` 的 schema 合法性与显式 `operator: between` 的兼容性分开测试；在尚无 operator/type 规则时，不臆造通用的 `between(false)` 拒绝语义。
- [x] 先为当前已知漂移添加失败用例，再修实现；以后修改既有 expected 必须经过协议版本判断，为已承诺行为补遗漏 case 不要求升版。

#### P0.2 修复 Query Input projection 全链路

- [x] Browser canonical binding、drift signature、projection 和 cache identity 必须保留 `projection`，不能只保留 `parameter / part`。
- [x] browser-js 对 `present` 使用 canonical empty-value 语义，对 `intent` 读取已提交 Query Parameter intent；Server Canvas 与 portable HTML 执行相同 fixture。
- [x] `server-python` Interactive 调用 Query projector 时必须传入所属 immutable Query Run 的 `query_parameter_intents`。
- [x] Source、Dataset Transform、server-python Interactive、browser-js Interactive 对相同 binding 产生完全相同的局部 `query_inputs`；注册 drift assertion 能发现 projection 差异。

#### P0.3 修复 Control Filter 与 revision parity

- [x] 先用不混入多位数字排序的 fixture（例如 bounds `[0, 8]`、rows `[-1, 0, 5, 9]`）修复零端点 truthiness；Python、Canvas 与 Web Component 都只保留 `0/5`。
- [x] 单独用多位数字、ISO 日期、普通文本与显式 operator 暴露当前 `between` 比较方式；在冻结 number/date/text coercion table 与版本判断前，不把“typed numeric between”混入 zero-bound bugfix。
- [x] `empty: passthrough | match_none`、`explicit + []`、路径字段和所有比较 operator 在三端共享 expected rows 或稳定错误码。
- [x] canonical value/signature 对 object key order、安全整数、非有限数值和不可序列化值有明确且一致的结果；大 Output 不通过反复 `JSON.stringify` 冒充稳定 content hash。
- [x] `consumer_revisions` 继续是由 Dependency Contract、effective revision 与 Scheduler `applied_revisions` 派生的只读审计投影；未知 consumer/control 确定性忽略，负数/boolean/非整数和 `applied > effective` 以稳定错误码拒绝，缺失 applied revision 投影为 `null` 并派生 stale。

#### P0.4 建立 Output transport capability 的 fail-fast 边界

- [x] 审计完整 kind 集合 `table/scalar/object/text/chart/image/html/file` 在 `server-python Artifact`、`browser-js live Canvas`、portable interactive HTML、portable snapshot、CLI immutable Result 与 Share page 的真实路径；现场重算、snapshot/Result 封存和 Share 不得合并成一格。
- [x] 记录物理 transport 与 policy：Server Canvas 的 `browser_table_transport=json|arrow|auto`（Arrow 使用 HTTP endpoint）、Share Base 的 embedded gzip Arrow chunks、Share 后续 server-python Derived 的 HTTP Arrow/JSON endpoint、Portable 的 embedded Arrow、页面内 structured clone、server-python 的 Run Artifact reference；Browser snapshot 回传始终为 JSON，Arrow table 会先变 rows。
- [x] 在没有 Browser asset materializer 前，`browser-js + portable snapshot/CLI Result + image/file` 在 export/CLI preflight 以精确 `output_destination_unsupported` 拒绝，并返回 `producer_runtime / output_kind / destination / required_capability`；不能把字符串交给服务器 `Path()`。portable interactive HTML 中由 browser-js 现场生成的 display-only 值不经过该 materializer，不得因 snapshot 限制被笼统禁止，但仍须由明确 Renderer/Browser capability 支持。
- [x] 若要把拒绝前移到通用 `validate` 或 Compiler，先执行 P0.0 的 Transform/Output revision 判断，因为这会缩小当前可接受的作者声明。Live Canvas 的 Renderer-specific display 不自动获得持久化、HTML、Result 或 Share 能力；当前也不虚构通用 Adapter capability manifest。
- [x] 审计 Browser CLI Result 的 `text/html`：原生文本/HTML bytes、MIME、扩展名与持久化 content hash 已对齐；HTML Export 中任何可达 `server-python` 分支仍整体不可用。
- [x] 区分 `artifact_content_hash`（格式相关的持久化字节）、未来可选的 `logical_value_hash` 和可选 `transport_byte_hash`；不再要求 JSON/Arrow/Parquet hash 相同。真实 Browser asset 持久化需求出现时采用 `LogicalOutput → materializer →` 现有 `ArtifactDescriptor`，不预先新增收据类型。

#### P0.5 发布门禁与确定残余

- [x] 修正文档中的旧 Runtime revision 等纯文案残余。`DatavizRuntimeV3Client` 是既有 public symbol，本轮保持不变；未来重命名必须作为独立兼容变更，不能当作文案清理。
- [x] Conformance corpus 进入快速测试；真实 Chromium 覆盖 iframe、portable HTML 与 Web Worker 边界，Firefox/WebKit 按现有稳定发布策略执行。
- [x] 生成 Runtime source/bundle 一致性检查、现有 unit/contract/server tests、代表性 Workspace `validate → run/report` 和 Browser E2E 全部通过。
- [x] README、DESIGN、plan、实现索引和 CHANGELOG 不再把缺少 fixture 证明的跨 Runtime 语义写成已完成。

P0 非目标：不合并 Query Parameter/Control、Dataset/Interactive Transform 或 Execution Run/Result；不新增作者可见 `states:`、exclude、任意 predicate、Filter Group 或第二张 Dependency Graph；不为纯实现 parity fix 增加兼容层或机械 revision，但也不把新语义伪装成 bugfix。

### P0.6：冻结 typed comparison 的下一版本契约（已完成）

这不是 P0 零端点 bugfix 的一部分，但直接影响分析结果，必须在结构重构前完成版本决策，不能长期停留在“以后决定”。

- [x] 用 P0 corpus 固定多位数字、负数、ISO 日期、普通文本、boolean、空 bound、显式/auto operator 和不可转换字段的可观察行为，并将新 typed 语义一次迁移到当前版本。
- [x] 冻结 operator × `value_type` 表：`integer/number` 的有序 operator 使用数值比较；`date` 使用 canonical 日期比较；`text` 只支持 `equals/in/contains` 并拒绝 lexical ordering；`boolean` 只允许 `equals/in`。
- [x] comparator 类型只来自声明的 Control `value_type`；Output Schema dtype 存在时做静态兼容检查，缺失时也不允许逐行猜类型或让 Python/JavaScript 自行 coercion。
- [x] 冻结空值顺序：Control empty policy 在 comparator 前处理；`between` 的 `null` endpoint 只按明确契约表示开放边界，`0/false` 不得视为缺失；缺失或 `null` 行字段统一 non-match。
- [x] 对 bound/字段不可转换、operator/type 不兼容和混合值定义稳定 error code；所有 Runtime 返回相同错误，不静默转字符串、`NaN` 或空匹配。
- [x] 分别记录 author schema、Dependency projection、Runtime/Web Component 的 bump/兼容决定；Dashboard v12、Interactive Transform v4、Dependency Contract v8 与 Runtime v7 已一次迁移，不保留两个隐式 comparison mode。
- [x] 发布门禁覆盖 `2/10` 数值顺序、日期边界、text ordering rejection 和 boolean rejection；同时证明三端实现一致与语义正确。

### P1：ControlRuntime、Domain locality、应用函数与 Compiler 内部收敛

P1 在 P0 与 typed comparison 决策之后调整内部边界，目标是让强表达能力可靠组合，而不是追求更多架构名词。P1-A、P1-B、P1-C、P1-E 是可独立验收的工作流；多 View writer 是 P1-A 完成后才进入版本设计的表达能力项。它们共享 P0.0 与抽象准入门禁，不得人为串成 big-bang migration。现有作者 DSL、Named Output 与 Result 语义默认保持不变；任何 public wire/persisted shape 变化先升版或给出兼容策略。

#### P1-A 托管于 Canvas 的 ControlRuntime 成为唯一 authority（已完成）

- [x] Characterization 覆盖旧 Shell shadow、Canvas 状态转换、checkpoint、动态 options，以及 View/Transform applied revision 的成功、失败、超时与 supersede 时点；Server/portable 继续执行同一生成 Runtime bundle。
- [x] Owner 已固定：Shell 拥有 Query Parameter draft/committed 与 Host UI；Server 拥有 Parameter Domain SQL/Adapter/cache；ControlRuntime 在 Server/Portable 唯一拥有 canonical Control state；RunManager 和 `AnalysisResultStore` 继续分别拥有临时运行与不可变结果。没有新增同名 class。
- [x] Server Python 交互入口只接受完整 canonical Control snapshot；`resolve_control_states()` 的 canonical signature 若改变输入就以 `control_state_not_canonical` 拒绝，不静默成为第二个 reducer。
- [x] Host channel 判定为同一发行物内的 private lockstep wire；实现采用普通 `postMessage`，每条消息校验 origin、active iframe `event.source` 与 dashboard/run/frame identity，不再增加 `MessageChannel` 分支。
- [x] 已实现最小消息：`dataviz:control-hello / restore-checkpoint / canvas-ready / control-action / control-apply / control-snapshot / action-rejected`。Action 只含 `action_id + base_control_version + typed payload`；snapshot/reject 只含确认和 Header 显示所需事实。
- [x] 未引入 transport sequence、独立 correlation ID、第二个全局 state version、逐消息 Contract hash或全量实时 audit graph；有界 action result cache提供重复 action 幂等响应。
- [x] Header Dashboard Control 已退化为 typed `set` action producer 和 operational projection；Shell 不 canonicalize、不增加 revision、不协调 Control domain、不解释 trigger、不做 per-key winner merge。
- [x] `dataviz:control-apply` 只发送 Dashboard Control keys；ControlRuntime 根据 binding graph 推导 manual consumers，Shell 不发送任意 targets。View writer 继续使用既有 typed action。
- [x] Compiler 从排除 Presentation 的 canonical Control definition/order、option domain、writer/consumer binding 与 trigger 生成 `control_contract_hash`；hash 只用于 hello/checkpoint，Shell/Runtime 不各自重建。
- [x] Checkpoint 是可丢弃恢复提示：hash/key/shape 不匹配整体忽略或拒绝；首份 restore/none/750ms timeout 永久关闭 restore window，迟到恢复返回 `restore_window_closed`，不提供 migration 或逐 key 升级。
- [x] 初始化顺序已固定为 listener/hello → restore/timeout → Base hydration → initial domains → checkpoint coordination → canonical snapshot → Ready；Ready 表示可接受 action，不等待 consumer 完成。
- [x] Host operational snapshot 只携带 current controls 与 Header state/options/availability/validation/disabled/loading/impact，不复制 `consumer_revisions`；Result/Export 另行原子收集持久化 evidence。
- [x] View/Transform 在启动时捕获 generation 与完整 Control state；只有同一 current generation 真正 Ready/成功才推进 applied evidence，superseded、迟到 Ready、loading/error/cancelled/timeout 均不推进。
- [x] State Snapshot v3、Analysis Result/Evidence v2 为每个有 applied revision 的 consumer 强制封存 `applied_control_state`（canonical key → `value/intent?/revision`），证据可脱离 revision history 自包含验证。
- [x] 失联时 Shell 进入 disconnected 并禁用 Control/Apply/Export；旧 frame、重复 action、stale base version、非法 payload、Contract mismatch 与迟到恢复均有确定结果。

#### P1-E 将同一 Parameter Domain snapshot 的级联投影下沉到浏览器

目标不是少调用一个接口，而是让定义本身精确回答“父值变化后是查询新 Domain，还是只查看同一 Domain snapshot 的另一部分”。两条路径不得根据网络、缓存、异常或临时结果大小在运行时互相回退。

- [x] 已记录旧路径并冻结行为矩阵：`geo_level → geo_values → store_nbrs`、`division → category_nbr → category_subcategory_nbr` 是 projection edge，独立 `item_nbrs: multiple_input` 无 Domain edge；真实浏览器记录 HTTP、cache hit/miss、SQL 执行、values/intents 与 generation。
- [x] Contract v2 分别暴露 `projection_dependencies`、`projection_descendants`、`query_domains` 与保留 projection/part 的 `domain_input_bindings`；组合 `dependencies` 只保留作完整拓扑/诊断，不再驱动 Shell 调度。
- [x] Compiler 以 `parameter_domain_dependency_mode_conflict` 拒绝同一个 `(parent parameter, Domain)` 同时声明 projection/query edge；一个 parent 对不同 Domain 的两项工作仍可合法共存。
- [x] 无下游叶子与无 Domain 的 `multiple_input` 只更新 draft；真实浏览器断言两者均为 0 Domain request。
- [x] boundary/bump decision 已登记：作者 `parameter-domain/v1` 不变；private lockstep Contract/Resolution 一次升级到 v2，不保留 v1 执行分支或 capability negotiation。
- [x] Server 从已验证 frame 生成完整 browser-safe relation projection，只下发 consumer 使用的 canonical candidate/signature、元数据、直接父 signature 和确定顺序；不下发未使用列值、SQL、Adapter 或凭据。
- [x] 复用原 request/cache/generation/resolution/endpoint；只增加一个 Shell 生产纯函数模块供运行和 conformance 共用，没有新增 Snapshot Store、Resolver service、Plan class、持久化 Artifact 或第二 endpoint。
- [x] 容量合同固定为每份 client relation projection 最多 50,000 records、canonical UTF-8 payload 最多 8 MiB；实际/上限在 response `capacity` 与机器错误中可见，必须完整且不得截断。
- [x] 超限返回 `parameter_domain_client_projection_limit` 及实际/允许 rows/bytes、Domain/consumer、`query_inputs`/拆 Domain/`multiple_input` 建议；payload 缺失、hash drift、本地异常也直接失败，均无 Server fallback。
- [x] 首次或缺少 generation 时只获取一次当前 snapshot；projection 父值随后按 Contract order 在 Shell 同步过滤、去重并以一个事务协调所有后代，不经过 debounce/loading/network。
- [x] `query_inputs` 的有效 canonical projection 变化才请求新 snapshot；input signature 进入 generation，cache 仅影响物理 SQL，旧 response 继续由 dashboard/request generation 取消或丢弃。
- [x] 手动 Reload 只走 query path 并绕过 cache；正式 Query 的浏览器断言确认不调用 Domain endpoint，只运行 Source/Dataset DAG。
- [x] Revert 先比较当前/committed Domain input signatures：同 snapshot 本地事务恢复；不同 signature 明确请求 committed snapshot。两者都不运行正式 Query、不持久化候选表。
- [x] `parameter-domain-projection` 共享 corpus 由 Python projector 与 Shell 生产模块执行，覆盖 `0/false`、多父集合、canonical signature、stable sort/dedupe、metadata conflict、`all_available | explicit`、主动空集及部分/完全失效；Revert/unavailable 由 Python 与真实浏览器事务测试补齐。
- [x] 现有 `domains.*.cached`、generation 与 HTTP/SQL 测试证据区分 local projection、cache-served snapshot 和 SQL execution；没有为此冻结新的公共 observability envelope。
- [x] 真实浏览器断言 projection 父值、叶子、独立输入均为 0 request，query-input 恰好请求所需 snapshot，Reload 绕 cache，Query 不请求 Domain，快速编辑回到 active signature 时不发布中间 snapshot。

#### P1-C 抽出最小 `run_analysis()` 应用函数

- [x] 定义内部 `RunRequest → run_analysis(request, dependencies) → canonical AnalysisResult`，覆盖 Dashboard、Base/Derived Output、View、batch/also 和 Overlay；直接基于当前 Dependency Contract，不等待 P1-A/P1-B。
- [x] 复用现有 Catalog/canonical Target resolver，不复制平行解析器；复用 `AnalysisResultStore.publish()` 的 staging/hash/immutable publish/index ownership，不新增竞争的封存对象。
- [x] `run_analysis()` 执行 canonical Target/capability preflight，通过后才启动 Target closure、请求级 plan 与 Runtime dispatch，并负责终态映射和 Artifact/provenance 汇总；Query Executor 与 Interaction Runtime 保留不同领域生命周期。
- [x] CLI `run` 只保留参数解析、text/JSON formatting 和 exit code。只有未来显式 Target/Result-sealing HTTP API 才作为同一函数的 Adapter；普通 Server Query/Control/SSE 仍由 RunManager 负责。
- [x] RunManager 继续拥有人类 session、渐进事件、取消、generation、临时 Execution Run 和 Artifact lease；普通 Control 更新不自动产生 Result。Report 的 Result publish 已复用同一封存函数；Share/Save/Export 只有 Result 语义相同时才继续复用该边界。
- [x] 第一版保持普通函数；可选 dependencies 仅为已加载的不可变 Workspace snapshot。没有新增通用 Job journal、Universal Event/Error/Output envelope、万能 Runner、service class 或 DI 框架。
- [x] P1-C characterization 已覆盖 direct/CLI canonical parity、View、Dashboard、Server Derived、batch/multi-output、Overlay explain/execute、preflight 不封存，以及 ready/partial/failed/cancelled 终态；最终验收由 `run_analysis()` 直接启动真实 Chromium 执行 Browser Derived Output，并断言 canonical Result、Output 与 per-consumer `applied_control_state`。该路径使用独立 Portable Canvas；P1-A Host/Canvas wire 由其真实浏览器门禁联合回归，两者共享 ControlRuntime/evidence 语义但不强行合并应用生命周期。

#### P1-D 多 View writer 表达能力

- [x] 真实 linked-brushing 用例固定为 `chart-gallery` 的省份收入排行与订单/收入散点共同写 `dashboard.province`，趋势、构成和明细共同消费；复制 Controls 会制造两个当前焦点，隐藏回调会绕过 scope/revision/evidence，因此用例满足抽象准入门禁。
- [x] Dependency Contract v10 使用有序 writer edges；所有 View 只发送带 source View/action identity 的 typed action，由同一 ControlRuntime 串行处理。
- [x] 默认 `select/select_many` 是明确 replace/set，不做隐式 union；`clear` 产生显式空集，`reset` 恢复声明的 initial。需要交集或组合条件时使用不同 Control 与显式 consumer logic。
- [x] Compiler 校验 source View、scope、Control `value_type`、field/mapping，并继续拒绝反向作用域、非法值与程序化重绘回发 action。
- [x] 多 writer 的交替 action、clear/reset、stale generation、re-render projection 和 Result evidence 已进入真实 Chromium 跨 Runtime fixture；action/rejection/evidence 均保留 source View。View generation 以 action 入队时的同步校验为准，已准入动作不会被前一个动作造成的同 writer 自重绘误杀；柱形与散点重叠 action、真实鼠标连续切换均无丢失。Plotly 原生快速双击只恢复 zoom scale，不提交 Control `reset`；明确 Restore action 才恢复 Control。Bound writer 仅 selected projection 改变时使用增量 restyle，正常慢速 marker 点击不会落入完整 react 的命中层空窗。
- [x] `chart-gallery` 已实现 ranking/scatter 交替 action、clear/reset、replace 与 source View/revision corpus；Compiler 接受两个合法 writer，并继续拒绝未知、越界、聚合歧义和类型不兼容的 edge。
- [x] 已按 P0.0 决策一次迁移 Dashboard `v13`、Dependency Contract `v10`、Runtime `v9`、State Snapshot `v4`、Analysis Result/Evidence `v3`；其余 Contract 未升版，也未新增 Control kind。

#### P1-B 模块化 `dependencies.py` 的 canonical derivation（已完成）

- [x] 已为 Dependency Contract v10、Layout Contract v1、Runtime Manifest、请求级 Query/Interactive ExecutionPlan、Catalog/inspect projection 与关键无效输入 diagnostics 建立语言无关 characterization fixture；四个真实 Dashboard 同时冻结结构 hash 和可读计划投影。
- [x] `LoadedDashboard` 仍是现有不可变快照 owner；`dependency_contract`、`layout_contract`、`parameter_domain_contract` 继续由各自 property 并发安全地 lazy derive/cache。测试证明三者独立惰性，Dependency 消费 Parameter Domain projection 的既有依赖保持显式、单向，没有包裹层或总编译 pass。
- [x] `compile_dashboard_dependencies()` 已成为清晰的编排入口；Query/Interactive 图与 binding、Output/View 输入、Control writer/domain/impact、跨 Runtime invariant、reverse index 和 Query Parameter impact 分别由私有 derivation 函数生成。
- [x] 没有新增 compile context、phase class、公开/持久化中间步骤、独立 lazy cache 或版本轴；当前中间值仍只是一次函数调用内的普通映射和既有 Contract value。
- [x] 继续保持 `dependency_contract + RunRequest.targets/current state → target-specific ExecutionPlan`；加载快照不缓存请求 Target 的最小闭包，Planner、Catalog、Canvas 与 `run_analysis()` 未迁移到新 DTO。
- [x] 保留当前 Dashboard-wide execution gate 和 exception 路径；没有在收益未被证明时引入 Diagnostic accumulator 或 `CompileOutcome`。
- [x] recovery-only reference/cycle scan 仍只补 diagnostics，不产生 topology/closure/Manifest 或 Runtime value；测试证明失败 derivation 不缓存 partial Contract，重复访问返回相同稳定诊断。
- [x] 每次提取均验证 v10/v1/Manifest/ExecutionPlan/Catalog/inspect/diagnostics parity；P1-B 没有改变作者 DSL、公开 projection、持久化 shape 或 private wire，因此没有协议升级。

#### P1 分项验收

- [x] P1-A：Server/Portable 使用同一 ControlRuntime bundle；只有它增加 Control revision；Shell 不再 winner merge，Header 不运行第二套 Control domain/revision 解释器。
- [x] P1-A：最小 channel 在无 checkpoint、重复 action、stale version、迟到恢复、旧 frame、错误 payload 和断连下都有确定结果；没有增加未被用例证明的额外时钟或 envelope 字段。
- [x] P1-A：consumer applied revision 只在当前 generation 真实成功后推进；Result/Export 原子 evidence 中的 `applied_control_state` 可独立证明实际值，Host snapshot 不承担持久化审计职责。
- [x] P1-E：Contract/`inspect` 对 projection/query edge 的投影无歧义，同一 parent/Domain 的双路径声明被 Compiler 拒绝；示例级联的父值编辑只做一次本地原子投影，叶子与独立 `multiple_input` 不做 Domain 工作，query-input 编辑才获取新 snapshot。
- [x] P1-E：完整 browser-safe projection 在 50,000 records / 8 MiB budget 内通过 Python/Shell 共用 fixtures；超限、缺失或 drift 以稳定错误失败并给出改用 `query_inputs`/拆分 Domain/`multiple_input` 的建议，任何测试都观察不到 Server/local 自动回退。
- [x] P1-E：Reload、Revert、快速连续编辑、cache hit/miss 与正式 Query 的 network/SQL 计数符合已冻结矩阵；snapshot generation 原子替换，旧响应和中间 choices 不可见。
- [x] P1-C：CLI 与直接调用 `run_analysis()` 得到相同 canonical Result/provenance；Base、两种 Derived、View、Dashboard、多 Output 与 Overlay 保持现状，preflight failure 不封存，启动后的 partial/failed/cancelled 均封存；真实 Chromium Browser Derived Output 与 P1-A ControlRuntime/applied-evidence 语义联合验收通过。
- [x] P1-D：两个以上合法 writer 不产生反馈循环、隐式集合合并或第二 authority；source View 在 action、rejection、State Snapshot、Result 与 Evidence 中可追踪，Server/Portable/Result 联合验收通过。
- [x] P1-B：每份现有 Contract result 在一个 `LoadedDashboard` 中仍只由自己的 canonical lazy derivation 产生，Contract 间输入依赖显式且无环；公开 projection 与 Dashboard-wide gate 不变，任何 partial/recovery fact 永不进入执行。
- [x] 所有分项：既有公开 Contract 的任何 shape/语义变化都有 P0.0 change record、revision/兼容决定和对应 conformance suite；P1-B 的纯内部重构由 exact characterization 证明无需升级，未把语义差异混作内部修改。

### P2：当前协议版本与 Analysis producer 门禁（已完成）

- [x] `protocols.py` 是当前 Schema URI 的唯一映射；Protocol Registry、Schema Catalog、CLI `version` 和内置文档都消费该映射，不再分别手写当前版本号。
- [x] 回归测试校验机器接口和 `docs/product-architecture.md` 的当前版本表；版本升级若只修改某一处会直接失败。
- [x] Analysis 持久化 reader 保留 tolerant-read 行为；Dataviz 内部 Entry/Catalog/Describe/Result/Evidence/Promotion producer 在每个 typed model 边界递归拒绝未知字段，核心字段拼错返回稳定 `analysis_producer_unknown_field`。
- [x] 当前不建设完整 Registry 平台，不统一升级无关协议，也不增加迁移层或双协议 Runtime。`DatavizRuntimeV3Client` 作为既有公开 symbol 保持不变；未来若确需重命名，再作为独立兼容变更处理。

默认价值顺序如下；顺序不等于人为串联的技术依赖：

| 顺序 | 工作 | 真正前置条件 |
| --- | --- | --- |
| 1 | P0.0–P0.5：最小 boundary gate、共享 fixtures、三项 parity 修复与发布门禁 | 无；这是其他可观察变化的基线 |
| 2 | P0.6：typed comparison 契约与版本决策 | P0 corpus 已记录当前行为 |
| 3 | P1-A：唯一 ControlRuntime authority 与最小 Host channel（已完成） | private lockstep `postMessage`、Dependency v9/Runtime v8/State v3/Analysis v2 与 generation evidence 已落地 |
| 4 | P1-E：Parameter Domain 同 snapshot 本地投影（已完成） | Contract/Resolution v2、明确容量 budget、共享 conformance 与真实浏览器请求矩阵均已落地；不依赖 P1-A/P1-B |
| 5 | P1-C：`run_analysis()` 应用函数（已完成） | P0 的 Target/Output capability expected 已冻结；不依赖 P1-A/P1-B |
| 6 | P1-D：多 View writer（已完成） | Dashboard v13、Dependency v10、Runtime v9、State v4、Analysis v3 与真实 linked-brushing 跨 Runtime 门禁已落地 |
| 7 | P1-B：`dependencies.py` 内部模块化（已完成） | v10/v1/Manifest/ExecutionPlan/Catalog/inspect/diagnostics exact characterization 已落地；无协议升级或 consumer 迁移 |
| 8 | P2：当前协议版本与 Analysis producer 门禁（已完成） | `protocols.py` 单一映射、静态文档回归和严格 producer 已落地 |

P1-A、P1-B、P1-C、P1-D、P1-E 已作为边界清楚的工作流分别完成；P1-B 只在 characterization expected 冻结后提取私有 derivation，没有迁移 consumer 或改变协议。当前 P2 范围只增加 current-version 投影门禁与严格 producer，不改变 tolerant reader。任何删除协议、改变 Analysis reader 兼容性或重命名 public symbol 的决定都必须先通过 P0.0 gate，不能因 P1 完成而跳过版本判断。

## 并行工作流

### 验证 AI 开发效率

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
- Browser asset bytes 上传、远程 URL 抓取、Blob/data URL 持久化或通用 Binary Artifact materializer；P0 只要求能力矩阵和稳定 fail-fast，完整支持由真实 image/file Result/Share 需求触发，成功物化继续返回现有 `ArtifactDescriptor`。
- `number-range`、month/quarter/year 日期控件、Transfer、Entity Picker 或 Drawer。
- 多套命名 Presentation、HTML Analysis Capsule、HTML Output 提取或远程分享链接分析。
- 多进程共同写一个 Workspace、内建账号体系、多租户资源配额或不可信代码沙箱。
- 自动 Apply Promote、自动 certified，或绕开人工审阅的知识写回。

## 明确非目标

- 旧实验契约兼容层、自动迁移或双协议 Runtime。
- 可编辑数据逻辑、依赖、布局或样式的通用网页开发器；Mosaic、坐标布局和旧 Widget 协议。
- 让 Python 直接操作 DOM 或成为第二套 View Renderer。
- Interactive Transform 隐式访问 Adapter 或重新查询 Source。
- 为 Analysis Plane 复制 Dependency Contract、Query Executor、InteractionExecutor 或 Browser Runtime。
- 让 AI 通过图像像素反推本可直接读取的 Base/Derived Output。
- 在没有真实需求和证据前增加空接口、Runtime、图表引擎或重复组件。

## Definition of Done

公开能力必须同时具备：严格 Schema 与稳定错误码、`validate` 提前发现、机器可读 CLI 文档、默认样式和扩展 hook、契约与真实浏览器测试、Server/HTML 一致行为、局部更新与状态隔离，以及准确的 README、DESIGN、plan 和 CHANGELOG。

同一语义存在 Python/JavaScript/Web Component 等多个实现时，还必须证明：规范 expected 只存在于共享 conformance corpus；所有适用实现得到相同 canonical value、rows、signature 或 error code；Browser source 与生成 bundle 同步；未支持的 Output kind/transport 在最早可判断边界稳定失败。没有这些证据，不得仅凭某一端 unit test 把跨 Runtime 能力勾为完成。

Typed comparison 完成还必须证明：operator × `value_type` 的允许表、coercion、空值和稳定错误在 Python、Canvas 与 Web Component 完全一致；数值 `2/10`、日期边界、文本排序决策、boolean operator 与不可转换输入均有 fixture；类型只来自声明和可选静态 Schema 校验，不通过逐行数据猜测。任何可观察语义变化必须有单独版本决定。

Parameter Domain locality 完成还必须证明：`options.depends_on` 与 Domain `query_inputs` 在 Contract 和 Runtime scheduling 中保持两类显式边；同 snapshot 父值级联只消费完整 browser-safe projection，叶子/独立输入不触发 Domain request，query edge 才获取新的 input-specific snapshot；row/byte 超限、payload 缺失和 contract drift 都稳定失败，不自动切换为 Server Resolver。Python/Shell 共用候选投影 expected，真实浏览器同时断言 HTTP 和 SQL 次数；Reload、Revert、cache 与正式 Query 均符合行为矩阵。没有这些证据，不能仅以“SQL 命中 cache”声称无多余 resolve。

Control authority 收敛完成还必须证明：Server/Portable 使用同一个 ControlRuntime 实现；hello/restore/ready 不死锁且无 checkpoint 也能启动；Shell 只发送 typed action、保存最后确认 checkpoint 和显示所需 Header projection；只有 ControlRuntime 增加 Control revision，Server Python 不成为第二个 normalization reducer；普通连接采用“逐消息校验 identity”或“握手后绑定 MessageChannel port”中的一种；`consumer_revisions` 可由 Contract、Control state 与 applied revisions 重建且不能驱动执行；consumer 只在其启动时捕获的 generation 真正成功后推进；Result/Export 原子封存自包含的 `applied_control_state`。旧 frame、Contract mismatch、重复 action、stale version、迟到恢复与断连均有确定结果；没有 characterization 反例时，不以额外 transport sequence 或全量实时 audit graph 作为完成条件。

内部架构收敛还必须证明：现有公开 Schema、Dependency/Layout/Runtime projection 未发生无意变化；`LoadedDashboard` 继续分别持有和缓存三份 canonical lazy Contract，每个事实只有一套 derivation，Contract 间依赖显式、单向且无环，不新增包裹 owner、总编译 pass 或长期中间 plan；请求级 ExecutionPlan 只由当前 Contract 与 RunRequest 派生；recovery diagnostics 不能产生可执行 partial fact。CLI `run`/显式 Target API 只作 Adapter，`run_analysis()` 与直接 CLI 路径产生相同 immutable Result/provenance，普通 Server RunManager 生命周期未被合并。若实施多 View writer，还必须证明多个 writer 不产生反馈循环、隐式 union 或第二 authority，并且 source View 可审计。公共或持久化变化必须先通过最小 boundary/bump gate，最终登记进同一 canonical metadata source 并关联 conformance suite。

Analysis Plane 还必须证明 Output 语义和可信度可审查、Catalog 可重建且并发安全、CLI 复用 Server/Browser Runtime 的同一执行语义、Result/Evidence 携带可验证 provenance，且 Promote 只产生可 validate 和 Git 审查的普通 Workspace 变更。计划项只有在实现、测试和文档都完成后才能勾选。

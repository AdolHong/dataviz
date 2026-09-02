# Dataviz 实施计划

更新时间：2026-09-02

稳定设计见 [DESIGN](DESIGN.md)，代码入口见 [当前实现索引](docs/product-architecture.md)，使用者入口见 [README](README.md)，已完成的版本工作见 [CHANGELOG](CHANGELOG.md)。本文件只记录当前基线、尚未完成的工作与按真实需求触发的候选项，不再重复保存历史迁移清单。

## 当前基线

| 领域 | 状态 | 当前结论 |
| --- | --- | --- |
| 数据执行架构 | 核心语义与 P0 跨 Runtime 一致性已完成 | Query DAG、Interactive DAG、Control/View 影响关系、Named Output、状态隔离和导出边界已经进入版本化 Dependency Contract；共享 conformance corpus 证明 Python、Canvas 与 Web Component 对 P0 契约的相同解释。 |
| Control 与 Linked Views | P1-A/P1-D 已完成 | `{value, revision, intent?}` 是 canonical Control state，View gesture 与 Header 都只是 typed action producer；Server/Portable 共用托管于 Canvas 的唯一 ControlRuntime。一个 Control 可由多个经 Compiler 校验的 View writer edge 写入，action/rejection/applied evidence 保留 source View。 |
| Input State / Consumer Binding | v19/v13/v14 当前契约与 conformance 已完成 | Query Parameter 使用 compact `all/include/exclude/none` state；Control 保留 `{value, revision, intent?}`。两者共用 typed value contract，但保持独立生命周期；projection、零边界、typed comparison、canonical signature、generation-start evidence、writer provenance 与 consumer revision 已由共享 fixtures/浏览器回归固定。 |
| Layout 与最终配置 | 已完成 | Dashboard v19 拥有结构；Layout Contract v1、Semantic Validation、`inspect layout`、Server、HTML 与 AI context 使用同一编译结果。 |
| Renderer 与组件 | P5 当前范围已完成 | Plotly 是唯一作者图表接口，原生 Map 覆盖点位与 GeoJSON 区域；普通 Table 使用 TanStack Table Core；Perspective 只用于终端用户现场多维探索；21 个 Component Package 均为 package-owned。 |
| AI Analysis Plane | 当前范围已完成 | `catalog → run → result → evidence`、物理 Target Reference、不可变 Result、Overlay、Evidence 与 Promote dry-run 已落地。 |
| AI 开发效率评测 | 工具完成，真实试验暂缓 | 维护者评测工具已与正式产品隔离；没有真实成对试验前不发布 Token 或效率结论。 |
| 规模与浏览器可靠性 | 当前范围已完成 | 固定 10K/100K/1M 基准和三浏览器契约矩阵已有可复现证据；快速迭代发布默认执行 Chromium 全套，稳定发布、跨浏览器敏感变更或明确要求时再执行 Firefox/WebKit。 |
| Query Parameter 与 Domain | P3 已完成；0.21.0 收口所有权 | SQL Domain 由所属 Dashboard 持有并形成 immutable materialization，同一 Dashboard 的用户/tab 可复用，跨 Dashboard 隔离；Browser 只走 Lookup 搜索/分页。 |
| Workspace 共享文件 | P4 已完成，进入 0.19.0 | Workspace Asset 注册共享静态文件；Dashboard Browser allowlist 与 File Source `asset:<id>` 独立；Server/portable HTML 共用 `context.assets`，Bundle 复制实际依赖闭包，AI context 只含元数据。 |
| Bundle 独立快照 | P4.1 已完成，进入 0.19.1 | Bundle 只写入新目录或空目录；staging 完整校验后一次发布，不复用、合并、同步或覆盖已有 Workspace。 |
| 业务看板最短路径 | P5 已完成 | 原生 Map View 消除常见地图需求对 Custom Renderer/JS/CSS 的依赖；Entity Select Scaffold 组合现有 Parameter Domain、Query Parameter 与 `query_filters`，没有新增 Runtime 状态模型。 |
| Compiler 与应用边界 | P1-B/P1-C 已完成 | `LoadedDashboard` 继续分别持有和缓存三份 canonical lazy Contract；Contract 间已有 derivation dependency 保持显式、单向。`dependencies.py` 已按语义提取私有 derivation 函数，没有增加 owner/wrapper/phase class；`RunRequest → run_analysis() → canonical AnalysisResult` 复用现有 Catalog resolver 与 `AnalysisResultStore`，没有增加 Runner class。 |
| 作者可观察性与开发反馈 | P6 已完成 | 已交付只读 Query explanation、Dataset Transform 的 Result 输入复用、原生 Map 多 Layer、参数作者模式和 Table 静态列强调；全部复用现有执行、状态与 Plotly/TanStack owner。 |
| Runtime 增量反馈与既有能力闭环 | P7 已完成 | Interactive Transform 更新保留旧画面，作者检查器解释本次刷新原因；Custom Renderer 多命名输入完成文档/Scaffold 闭环；Workspace Asset File Source 在执行与 Result 封存中使用同一解析规则。 |
| 当前发行基线 | 0.21.1 已封版 | Lookup 竞态、参数分段诊断、有界 Interactive cache 与多输入 alias 证据已进入公共实现；完整非浏览器、Chromium/Firefox/WebKit 完整 E2E 与 wheel/sdist/ZIP 独立安装冒烟均通过。 |

当前开发基线：Package `0.21.1`、Python 3.11–3.14、`dataviz/workspace/v2`、`dataviz/dashboard/v19`、`dataviz/parameter-domain/v2`、`dataviz/parameter-domain-contract/v3`、`dataviz/parameter-lookup/v1`、`dataviz/parameter-materialization/v1`、`dataviz/dashboard-bundle/v2`、`dataviz/report-manifest/v3`、`dataviz/presentation/v2`、`dataviz/source/v6`、`dataviz/dataset-transform/v3`、`dataviz/interactive-transform/v4`、`dataviz/dependency-contract/v13`、`dataviz/layout-contract/v1`、`dataviz/state-snapshot/v6`、`dataviz/runtime/v14`、`dataviz/analysis-result/v5`、`dataviz/analysis-evidence/v5`、Component Registry `6.0.0`。当前 0.x Runtime 是 exact-current、同 package lockstep，没有 capability negotiation。P3/P4 已按 P0.0 决策迁移各自 authoring、private wire 与 portable/persisted 边界；以后缩小合法 Output 声明、改变持久化 shape 或 public wire 仍必须分别判断版本，不能被“bugfix 不升版”笼统覆盖。

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
- [x] `server-python` Interactive 调用 Query projector 时必须读取所属 immutable Query Run 的 canonical `query_parameter_state`，不能从当前 Shell 草稿重建输入。
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

### P1：ControlRuntime、应用函数与 Compiler 内部收敛

P1 在 P0 与 typed comparison 决策之后调整内部边界，目标是让强表达能力可靠组合，而不是追求更多架构名词。P1-A、P1-B、P1-C 是可独立验收的工作流；多 View writer 是 P1-A 完成后才进入版本设计的表达能力项。它们共享 P0.0 与抽象准入门禁，不得人为串成 big-bang migration。现有作者 DSL、Named Output 与 Result 语义默认保持不变；任何 public wire/persisted shape 变化先升版或给出兼容策略。

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
- [x] P1-C：CLI 与直接调用 `run_analysis()` 得到相同 canonical Result/provenance；Base、两种 Derived、View、Dashboard、多 Output 与 Overlay 保持现状，preflight failure 不封存，启动后的 partial/failed/cancelled 均封存；真实 Chromium Browser Derived Output 与 P1-A ControlRuntime/applied-evidence 语义联合验收通过。
- [x] P1-D：两个以上合法 writer 不产生反馈循环、隐式集合合并或第二 authority；source View 在 action、rejection、State Snapshot、Result 与 Evidence 中可追踪，Server/Portable/Result 联合验收通过。
- [x] P1-B：每份现有 Contract result 在一个 `LoadedDashboard` 中仍只由自己的 canonical lazy derivation 产生，Contract 间输入依赖显式且无环；公开 projection 与 Dashboard-wide gate 不变，任何 partial/recovery fact 永不进入执行。
- [x] 所有分项：既有公开 Contract 的任何 shape/语义变化都有 P0.0 change record、revision/兼容决定和对应 conformance suite；P1-B 的纯内部重构由 exact characterization 证明无需升级，未把语义差异混作内部修改。

### P2：当前协议版本与 Analysis producer 门禁（已完成）

- [x] `protocols.py` 是当前 Schema URI 的唯一映射；Protocol Registry、Schema Catalog、CLI `version` 和内置文档都消费该映射，不再分别手写当前版本号。
- [x] 回归测试校验机器接口和 `docs/product-architecture.md` 的当前版本表；版本升级若只修改某一处会直接失败。
- [x] Analysis 持久化 reader 保留 tolerant-read 行为；Dataviz 内部 Entry/Catalog/Describe/Result/Evidence/Promotion producer 在每个 typed model 边界递归拒绝未知字段，核心字段拼错返回稳定 `analysis_producer_unknown_field`。
- [x] 当前不建设完整 Registry 平台，不统一升级无关协议，也不增加迁移层或双协议 Runtime。`DatavizRuntimeV3Client` 作为既有公开 symbol 保持不变；未来若确需重命名，再作为独立兼容变更处理。

### P3：Query Parameter 紧凑集合与 Dashboard-owned 物化候选（已完成）

目标：删除 SQL 候选的“小 Domain 完整下发 / 大 Domain 远程查询”作者分叉。每个 SQL Parameter Domain 由所属 Dashboard 持有并形成 Server 端 immutable materialization，Browser 只通过同一 Lookup 做 distinct、父级过滤、搜索和 cursor 分页；static choices 保持内联。Query Parameter 多选改为紧凑集合表达式，10 万候选的全选、排除一项、Result 与 HTML 都不得展开全集。

#### P3.0 冻结状态语义与版本边界

- [x] 迁移 characterization 已分别冻结 pre-v14 与当前 Query state、Domain、Source projection、URL/tab/Revert、Result/HTML 和 CLI expected；旧路径仅存在于迁移证据，不进入当前 Runtime。
- [x] 定稿 canonical Query Parameter state：普通输入 `{value}`；候选多选 `{selection: all|include|exclude|none, value: finite operands}`。`all/none` 强制空 operands，include/exclude 去重且受 `max_explicit_values` 限制。
- [x] 统一默认声明为 `default`：single select 只允许 first/value/none，candidate multiple 只允许 all/include/exclude/none，自由输入继续使用自身 typed value；Reset/Revert/refresh 的边界分别冻结。
- [x] P0.0 inventory 与一次迁移决策已覆盖 Dashboard、Parameter Domain definition/Contract/Lookup、Source SQL filter token、Runtime Query transaction、State/Result/Evidence 和 CLI invocation；同一 Dashboard 没有双 state 解释器。

#### P3.1 Dashboard Domain 与物化 Store

- [x] Parameter Domain definition/SQL 必须位于 Dashboard；`workspace:/...` 只用于稳定 Workspace Asset，不允许引用取数逻辑。相似看板复制 SQL 后独立演进，不因修改一个共享文件影响其他看板。
- [x] SQL Domain 禁止以 Dashboard draft `query_inputs` 碎片化物化；父级关系只进入物化后的本地 Lookup predicate，Runtime 不按基数选择第二条路径。
- [x] 实现 `.dataviz/parameter-materializations/` registry、immutable generation、Parquet/manifest、atomic publish、reader pin、refresh lease、Server restart recovery 和 preview-first prune；物化不写入 `dashboards/`。
- [x] Materialization key 覆盖 Dashboard-local definition path/code hash、实际 Adapter identity 和非敏感 visibility scope；凭据不落盘。同一 Dashboard 可跨用户/tab 共享，不同 Dashboard 与不同 RLS/principal 必须隔离。
- [x] Server row/byte/disk guard 与错误证据已独立于 Browser response；页面始终只接收有界 Lookup page。

#### P3.2 Freshness、并发与运维

- [x] 实现 `refresh_after_seconds` 与 `expire_after_seconds`：fresh 直接读，stale 立即读旧 generation 并由单一 lease 后台刷新，refresh failure 在 hard expiry 前继续读旧值，expired/missing 只禁用相关 Picker。
- [x] Query Card Reload 触发当前 Dashboard refresh、合并同看板重复请求并保留旧 generation/draft；不 Reset、不 Query。新 generation 原子发布后只更新标签、计数与页，不展开 all/exclude。
- [x] 提供可脚本化的 prewarm/status/refresh CLI；输出 generation、rows、freshness、last error 与 next refresh，不打印候选全集。
- [x] 覆盖并发 tab/用户、Server 中断、过期 lease、构建失败、Adapter visibility 变化、旧 generation reader 与 prune 竞争；当前仍不承诺多个独立 Server 或网络文件系统共同写一个 Workspace。

#### P3.3 Lookup、搜索、分页与级联

- [x] 所有 SQL Domain consumer 使用同一 Server-local Lookup；第一页若已覆盖全部候选也只是同一响应的自然结果，不增加 eager/remote/access 等作者 mode。
- [x] 请求只含 Domain/consumer、父 canonical states、search、limit、opaque cursor 和有限 selected operands；response 在一个 pinned generation 中返回 items、selected_items、exact total、next_cursor 与 freshness。
- [x] 父 `depends_on` 将 `single_select` canonical 标量编译为单值 include，将 `multiple_select` 的 all/include/exclude/none 编译为本地物化 predicate，再做 consumer value/label/metadata distinct；父编辑、搜索和翻页都不执行远端 Domain SQL。
- [x] 搜索固定 NFKC/casefold、空白 token AND 与 exact/prefix/keywords/substring 排序；拼音和别名只来自 `keywords_field`，不提供 regex、任意 SQL 或模型搜索。
- [x] cursor 绑定 generation 和稳定 sort tuple；generation/search/parent 改变会取消旧请求并从第一页开始，迟到页不得覆盖新状态。Browser 每页 500，CLI 默认 50，统一上限 500；不提供含糊的“当前页全选”。
- [x] 已选 operands 与当前页分离；补标签和 unavailable 只处理有限 operands。父级变化协调 include/exclude 有效交集，Revert 原样恢复 committed operands；翻页、搜索和 refresh 不丢失选择。数量摘要由 total 与 compact state 推导，不展开 Tag。
- [x] Lookup 成功后只替换并同步当前 Select，不再重写 Query Parameter state 或执行全表单 `controls.sync()`；搜索结果优先进入下一次 Browser paint，并保留焦点、搜索词、展开状态与 request generation 门禁。
- [x] 页面刷新和首次 Dashboard hydration 把 URL/tab/committed compact state 作为恢复目标；Lookup 按依赖拓扑补全有限 operands 的标签与 availability，不将恢复误判为父级编辑，也不静默丢失已选 Item。

#### P3.4 Source binding、Result 与可搬运性

- [x] Query consumer projection 已收敛为 `value / selection / active / state / start / end`；candidate multiple 的 SQL value consumer 必须同时消费 selection，Python 可直接消费完整 state。候选页、cursor 和物化 metadata 不进入业务代码。
- [x] Source v5 的受限 `{{ dataviz_filter:name }}` SQL token 与 `query_filters` 为 all/include/exclude 生成参数化 TRUE/IN/NOT IN，并要求每个 consumer 用 `empty: passthrough|match_none` 明确把空 `multiple_input` 或 `multiple_select none` 映射为 TRUE/FALSE；不是通用 Jinja。高级作者仍可显式消费 selection/value。
- [x] `dataviz run` 支持直接传 canonical state 且不隐式物化候选；Catalog/describe 一次展示 default、selection contract、Domain、父依赖和所需 Source projection。
- [x] Result/Evidence/URL/checkpoint/分享/HTML 只保存 compact state；all/none 无 operands，include/exclude 只保存有限 operands。分享/HTML 继续锁定参数，不嵌入 SQL、Parquet、候选页、搜索词或 cursor。
- [x] portable Dashboard bundle 复制完整 Dashboard 目录，Domain definition/SQL 随目录自然进入快照；额外闭包只包含实际引用的 Workspace Asset 与非敏感 binding manifest，默认不复制 `.dataviz` materialization 或凭据。

#### P3.5 验收与文档迁移

- [x] conformance corpus 覆盖 Browser/Python/SQL filter/CLI 的 all/include/exclude/none、默认、typed values、空列表、operand limit、parent predicate、unavailable 与 canonical signature。
- [x] 真实浏览器覆盖首次 missing、预热 fresh、stale refresh、hard expiry、搜索、cursor、三级级联、Reload/Revert、同 Dashboard 多 tab 共用 generation、不同 Dashboard generation 隔离，以及 Domain 失败不锁死导航。
- [x] 固定 10K/100K/250K materialization/Lookup benchmark；DuckDB/Parquet 优化未产生第二套 DSL，页面始终只持有当前页和有限 operands。

#### 本次发版前的 Plotly 交互修复（已完成）

- [x] Lasso Select 与 Box Select 进入选择模式后，各自都允许再次点击当前已激活的工具退出并恢复普通查看模式；退出只取消工具激活态，保留已有选区，不隐式触发 `clear` / `reset`。Server 与 portable HTML 已覆盖真实工具栏点击回归。
- [x] `documentation.py`、`dataviz-skill.md`、product architecture、Scaffold、schemas、examples 和错误建议已统一到当前 P3 契约，旧候选双路径只保留在明确的迁移 change record 中。

### P4：Workspace Asset 与单 Dashboard 可搬运闭包（已完成）

- [x] Workspace v2 注册稳定 Asset ID、相对路径与 MIME；Loader/validate 拒绝缺失文件、绝对路径和 Workspace 逃逸。注册本身不构成 Browser 公开。
- [x] Dashboard v16 以 `assets` 作为 Browser allowlist；Source v6 的 File Source 可独立读取 `asset:<id>` 且必须显式声明 format。两条引用只共享文件身份，不互相隐式授权。
- [x] Runtime v12 提供 `context.assets.list/describe/bytes/text/json/blob/url`；Server 使用 Dashboard-scoped URL、ETag 与 MIME，portable HTML 使用 UTF-8/base64 inline，同一 Renderer 不判断 transport。
- [x] Dashboard Bundle v2 计算 Browser Assets 与 File Source Assets 的联合闭包；Parameter Domain 已位于完整复制的 Dashboard 目录，不再产生 Workspace SQL 闭包。未引用文件、凭据或 `.dataviz` 不进入快照。
- [x] Report Manifest v3 记录 Asset path-independent hash/size/MIME；`inspect context` 只投影当前依赖 Asset 元数据，不读取内容进入 AI context。
- [x] 契约、Server route、File Source、report/bundle、hot reload 与 Server/portable Browser parity 均有回归；0.19.0 完整发布门禁见本次发行记录。

### P4.1：Bundle 独立快照收口（0.19.1）

- [x] `dataviz bundle` 只接受不存在或为空的目标目录；普通文件、非空目录和源 Workspace 自身均稳定失败，不读取目标内容做复用或合并。
- [x] 在目标同级临时目录构建完整 Workspace、Dashboard、Workspace Asset 与 Manifest；全部复制、hash 和来源稳定性校验通过后才一次发布。
- [x] Bundle 是单向、自包含快照，不是 import、merge、sync 或 package manager；输出不修改源 Workspace，也不能覆盖已有 SQL、Asset、Dashboard 或其他用户文件。
- [x] Source SQL、Parameter Domain SQL 与普通文件均为 Dashboard-local；Workspace 共享能力只保留稳定 Asset，不扩展为 Shared Source/Transform/View/SQL。
- [x] 回归覆盖空目录成功、非空目录拒绝、旧 Bundle 无法覆盖新 SQL、复制期间来源变化失败且不发布 partial destination、闭包独立运行和凭据/缓存排除。
- [x] `DESIGN.md`、内置 docs、`dataviz-skill.md`、架构文档、CLI help 与 Changelog 使用一致术语；0.19.1 只运行非浏览器和静态门禁后构建 wheel/sdist/ZIP。

### P5：原生地图表达与实体选择最短路径

目标：让“按经纬度展示点位”“按 GeoJSON 行政区着色”和“搜索并选择十万级 Item”不再要求普通 Dashboard 作者编写 Custom Renderer 或重复拼接一组低层契约。P5 复用当前 Plotly、Workspace Asset、Parameter Domain、compact selection、Control writer 与 Renderer lifecycle，不建立第二套地图引擎、候选状态或共享数据执行模型。

#### P5.0 契约与版本门禁

- [x] 用真实 `map-lab` 同时固定门店点位与行政区指标、离线 GeoJSON、跨 View 选择写回和 Server/portable parity；原生 View 不需要 Dashboard 自带 JS/CSS/Renderer。
- [x] 按 P0.0 将作者契约升为 Dashboard v16、Runtime v12、Component Registry 5.8.0；Dependency/Result/Evidence/Transform shape 未变，因此不机械升版。
- [x] 地图文档只在地理位置本身参与分析问题时推荐 Map；普通分类比较仍优先 Bar/Table。

#### P5.1 原生 Map View

- [x] 第一版只支持 `mark: point | region`：point 映射 longitude/latitude，可选 label/color/size；region 通过 Dashboard 已声明的 Workspace GeoJSON Asset，把 `data_key` 与 `feature_key` 连接并映射 label/color。
- [x] 复用唯一 Plotly Chart Service 和现有 View `options.trace / options.layout / config` 逃生口；没有引入第二套图表包、地图 DSL、远程瓦片依赖或 Python Plotly。
- [x] point 不强制 GeoJSON；region 的 GeoJSON 来自 Workspace Asset 并进入 Browser allowlist、Bundle、Report Manifest 与 portable HTML 依赖闭包。第一版不支持远程 URL、在线 token、多图层编辑、轨迹、聚合或 GIS 运算。
- [x] 复用 View lifecycle、Theme、Resize、Empty/Error、tooltip、HTML Export 与 dispose；地图点击/框选只通过现有 `control_binding` writer edge 提交 typed action，没有 map-specific selection state。
- [x] 静态 `validate` 拒绝缺少字段声明和未暴露 Asset；查询完成后 Renderer 在绘图前拒绝非有限坐标、重复数据/feature key 和无法连接的 key。Server 与 portable HTML 使用同一 Renderer 和本地资产。

#### P5.2 Entity Select Scaffold，不新增 Entity Runtime

- [x] 新增 `dataviz scaffold query-parameter.entity-select`，生成现有 Parameter Domain、Domain-backed `multiple_select`、value/label/keywords/metadata 投影和 Source `query_filters` 示例。
- [x] 默认示例面向十万级 Item：Server Lookup 搜索/opaque cursor 分页，`default: {mode: none}`、`clearable: true`、`empty: passthrough`；空选择表示不筛选，有限 include 表示只筛选所选 Item，Browser/Result/HTML 不展开候选全集。
- [x] Recipe 只生成当前严格 Schema 的普通文件，没有新增 `entity_select` value type、状态协议、第二候选 Store 或自动业务合法性白名单。

#### P5.3 渐进文档与诊断降噪

- [x] 增加 `map-view` / `entity-select` focused task、`maps` / `entity-selection` docs 与 Skill 最短路径；完整 Plotly、Workspace Asset 和 Parameter Domain 契约按需展开。
- [x] 删除对所有旧式/私有 Output 一概提示 semantics 的 advice；public/reviewed/certified SQL 的确定性风险仍保留。
- [x] strict validate、严格 Scaffold、Plotly/Asset 生成资产、真实 Chromium Server/portable 地图 parity 与相关 Chart/Table/Parameter Domain 非回归通过；本次没有跨浏览器 CSS/交互风险，Firefox/WebKit 不作为 P5 开发门禁。

#### P5.4 Overview → Detail 原子联动（0.20.0）

- [x] `control_binding` 增加有序 `writes`：主 binding 继续决定当前 View 的选中高亮，附加 write 从同一行投影其他 scoped Control；不增加地图专属事件、隐藏回调或第二 reducer。
- [x] 一次 View 手势只生成一个 `action_id`，ControlRuntime 在提交前完成全部字段、类型、scope、cardinality 与 generation 校验；任何目标失败则全部拒绝，成功则一次写入全部 Control、按既有 Control DAG 调和候选域并只触发一次 consumer/render 调度。
- [x] `select` 对每个目标投影一个值；`select_many` 先稳定去重，single-value Control 收到多个不同值时以稳定错误拒绝整次 action；`clear/reset` 同样原子作用于主目标和全部附加目标。
- [x] Dependency Contract 的每个目标保留独立 writer edge，Result/Evidence 沿用现有 per-Control writer provenance；同一次 compound action 通过相同 `action_id/source_view/action` 关联，不新增持久化状态 shape。
- [x] `map-lab` 固定真实全国 → 城市下钻：全国门店图一次点击写 City + Store，城市图只消费 City 并继续写 Store，全国图不被详情状态反向过滤；Server/portable、三浏览器、Result evidence 与发行冒烟共同验收。
- [x] Map viewport 由实际坐标/区域 key 集合生成稳定 revision：跨 City 必须重新 fitbounds，同城 Store 高亮不重置视野；Plotly update 期间合并 ResizeObserver 事件，压力回归连续跨四城 12 次验证 trace 与实际 SVG 点位均可见。
- [x] 按 P0.0 升为 Dashboard v17、Dependency Contract v12、Runtime v13、Component Registry 5.9.0；State Snapshot、Result/Evidence 与 Transform shape 不变。完成后更新内置 docs、Skill、架构文档和 Changelog，并发布 Package 0.20.0。

P5 明确非目标：Workspace 级共享 Source、Transform、View、Parameter Domain 或业务 SQL。跨 Dashboard 复用稳定语义使用 Catalog Output，复用静态文件使用 Workspace Asset；取数逻辑允许少量复制换取清晰所有权和安全 Bundle。P5.4 也不提供任意事件编排：一个 View gesture 只能从同一批选中 datum 投影声明过的 Control write，不能执行 Query Parameter、SQL、任意 JavaScript callback 或跨 Dashboard action。

### P6：作者可观察性与开发反馈（已完成）

目标：不继续堆叠业务 DSL，先让作者和 AI 能解释“当前 state 如何变成执行计划、SQL、行数与 Result”。P6 只允许复用 canonical Query Parameter state、Dependency/Execution Plan、现有 Executor、Artifact 与 immutable Result；诊断输出是这些事实的只读投影，不建立第二套参数解释器、SQL 编译器、运行日志或状态 Store。

#### P6.0 统一 Query/Source/空结果证据

- [x] 冻结执行前 explanation、执行中 telemetry、执行后 immutable evidence 三类边界。`inspect query` 明确返回 `executed: false`；实际 statement、bindings、缓存、行数、耗时与错误仍由 Result/Execution evidence 拥有。
- [x] 提供 `dataviz inspect query <workspace> <dashboard> --source <source>`，接受与 `run` 相同的 Query Parameter 输入或显式 canonical state；输出 `all/include/exclude/none`、有限 operands/active、Query Filter predicate、脱敏 bindings、参数化 statement 和 Parameter Domain dependency，不执行 Source。
- [x] 已有可读 Parameter Domain generation 时附带候选、有效已选和 unavailable 数；没有 materialization 时返回 `missing` 与 `null` counts，且 inspect 不创建 SQLite/index 或触发候选 SQL。
- [x] `result inspect` 继续拥有实际 Resolved SQL、Driver statement、bindings、Adapter、cache、输入/输出行数、耗时和 provenance；Source canonical Target 可独立执行，未增加 `run-source`。
- [x] Empty/NO DATA 只封存运行记录能够证明的 `source_zero_rows / transform_zero_rows / control_filter_zero_rows / upstream_failed` 与有限 filter 摘要；View renderer/mapping 错误继续使用既有 View/Renderer error evidence，不在 Server 执行结果中猜测。
- [x] SQL、binding、traceback 与 diagnostics 继续经过同一凭据脱敏边界；Query explanation 复用 SQL Runner diagnostics，不维护第二套 SQL 编译器。

#### P6.1 Python Transform 从 Result 复用输入

- [x] 未增加 `run-transform`；canonical Dataset Transform Target 支持 `dataviz run ... --from-result <result-id>`，以既有 Named Output 为输入且不重新查询 Source。
- [x] 只从一个 ready/partial immutable Result 解析当前 Transform 已声明的直接输入；reference、kind、声明 Schema、行数与持久化 Artifact hash 不兼容时稳定失败，不猜字段、不回退查询数据库。
- [x] 每次复用仍创建新的 Execution 与 Result；provenance 记录输入 Result、reference、kind、rows 与 Artifact hash，既有 Result 不修改。行数、Schema、耗时、日志和脱敏 traceback 继续使用现有 Executor/Result 证据；未为不稳定的跨平台峰值内存口径另建字段。
- [x] 已以 Dataset Transform 的真实用例证明 Source 不会执行；`server-python` Interactive Transform 仍不接受 `--from-result`，等待 Control/applied-state 可完整重建的真实需求。

#### P6.2 原生 Map 多 Layer

- [x] “GeoJSON 区域 + 门店点位”已进入真实 `map-lab`；每层显式拥有稳定 id、input、mark、字段映射、可选 Control binding 与顺序，不要求共用输入表。
- [x] 单 mark 与 `layers` 互斥并由 Schema/Compiler 严格校验；合法输入扩展已升级 Dashboard v18、Dependency Contract v13、Runtime v14、State Snapshot v6、Analysis Result/Evidence v5、Component Registry 6.0.0 和 `view.declarative` 3.0.0。
- [x] 所有 Layer 编译为同一个 Plotly Map View/Renderer 生命周期；viewport 使用可见 Layer 的稳定集合签名，数据集合变化时 refit，单纯高亮变化保留视野。
- [x] 点击、框选和套索携带 source View/Layer provenance，继续写既有 ControlRuntime typed action；State Snapshot、Result 与 Evidence 封存 `source_layer`，未增加 Layer 私有状态或 callback 总线。
- [x] 仍不承诺在线 token/远程瓦片、GIS 运算、轨迹、热力聚合和可视化 Layer 编辑器；复杂 Plotly trace 继续走 options/Custom Renderer。

#### P6.3 参数作者模式与确定性迁移说明

- [x] 普通用户继续看到业务文案；Query Card 的显式作者开关只读投影 canonical selection、operand count、available/unavailable count、父级 dependency 和最近一次协调结果。
- [x] 父参数变化后的保留、有效交集、恢复 default 或转为 all，由现有 Query Parameter reconciliation 同步留下 transition evidence；作者投影不保存第二份参数状态或历史。
- [x] unavailable operand 继续与 available 候选分离；作者模式只改变诊断文字可见性，不改变 Query、候选刷新、Revert、Result 或 portable HTML 语义。

#### P6.4 Table 呈现小补强

- [x] 文档继续复用 `labels/formats/align/widths/wrap`，没有增加同义配置。
- [x] 默认 TanStack Table 支持最小静态 `options.emphasis.columns`，仅为列头与单元格增加稳定 markup/token 强调，不执行条件表达式或业务计算。
- [x] 复杂条件格式、自定义 cell/header/footer 仍通过 TanStack/Custom Renderer；Server 与 portable HTML 继续使用同一 `view.declarative` Table owner。

P6 明确暂缓 Workspace 级 Python 工具库。它会同时引入 import namespace、依赖 hash、子进程加载、缓存失效、Bundle 闭包和 traceback 映射，当前少量 helper 允许 Dashboard-local 复制；只有多个真实项目持续证明该重复是主要成本时再设计。Transpose DSL、指标表达式 DSL、SQL 组合 DSL、自动推断 Category/Item 关系、第二套图表/地图引擎和隐式跨 Dashboard Source 依赖同样不进入 P6。

### P7：Runtime 增量反馈与既有能力闭环（已完成）

目标：修复真实链路断点，并让交互重算更像局部更新；不为已有能力再增加协议、DSL 或持久化状态。

- [x] File Source 的 `asset:<id>` 在 Source Reader 与 Analysis Result source receipt 中统一经 Workspace Asset resolver 解析；真实 `Workspace Asset → File Source → Analysis Result` 集成回归防止执行成功、封存失败。
- [x] 已挂载 View 在 Interactive Transform 重算时保留旧内容，只显示轻量 `updating` 状态；首次加载仍使用完整 Loading，新 generation 就绪后原位更新。
- [x] Custom View 继续使用既有 `inputs` 映射；descriptor 以 `inputs.<alias>` 暴露多个 Named Output，`rows` 只保留主输入兼容捷径。内置 docs、Skill 与 Scaffold 展示该能力，没有新增 View/Runtime revision。
- [x] 作者模式的 Interactive 节点检查器显示本次刷新由哪些 Control、上游 Output、缺失 Output 或 manual action 触发，以及实际变化的 Output 和受影响 View；该 trace 只存在于当前 Server Runtime，不进入 State Snapshot、Result 或 Evidence。
- [x] 同一作者模式把刷新证据投影到每个 View renderer signal：从 View 反查触发 Control/Transform、变化 Output、是否执行 Query，并显示浏览器实际消费的 rows/bytes 与最近一次 mount/update 耗时；不新增持久化协议或第二证据 Store。
- [x] Custom Renderer contract test 与会话诊断记录 mount/update/dispose，稳定拒绝空 mount、hook failure 和 dispose 后遗留 DOM；不夸大为任意事件监听器或第三方库内存泄漏检测。
- [x] 地理裁剪只提供 Transform Recipe：行政区编码规范化、Polygon/MultiPolygon、无效 Geometry、结果范围裁剪和 viewport 建议继续由 Python/JavaScript 完整表达，不增加 GIS DSL。
- [x] 暂不增加 Interactive Transform `outputs.<name>.depends_on_controls`。当前 Runtime 已按输出 value signature 只重绘真正变化的下游 View，但一个 Transform 函数仍会整体执行；只有真实重算成本证明拆 Transform 也无法接受时，才设计输出级执行计划并判断协议升版。
- [x] Remote Lookup 的成功、失败、分页与父级变化共用 request generation + parent-state signature 门禁；迟到失败不能覆盖较新的成功。当前 Picker 具有独立 `aria-busy`，参数作者模式显示 request/commit/visible-refresh 分段耗时。
- [x] browser-js session cache 去除仅用于审计的 Control revision 噪声，增加内部有界 LRU、hit/miss/eviction metrics，并把本次 cache 状态投影到既有 Interactive trace；没有新增 cache DSL 或持久化协议。
- [x] 多输入 View 的既有刷新证据增加 alias 投影；等待、失败和实际变化均指出 input alias 与 canonical Output reference，不增加 Renderer 输入协议。

默认价值顺序如下；顺序不等于人为串联的技术依赖：

| 顺序 | 工作 | 真正前置条件 |
| --- | --- | --- |
| 1 | P0.0–P0.5：最小 boundary gate、共享 fixtures、三项 parity 修复与发布门禁 | 无；这是其他可观察变化的基线 |
| 2 | P0.6：typed comparison 契约与版本决策 | P0 corpus 已记录当前行为 |
| 3 | P1-A：唯一 ControlRuntime authority 与最小 Host channel（已完成） | private lockstep `postMessage`、Dependency v9/Runtime v8/State v3/Analysis v2 与 generation evidence 已落地 |
| 4 | P1-C：`run_analysis()` 应用函数（已完成） | P0 的 Target/Output capability expected 已冻结；不依赖 P1-A/P1-B |
| 5 | P1-D：多 View writer（已完成） | Dashboard v13、Dependency v10、Runtime v9、State v4、Analysis v3 与真实 linked-brushing 跨 Runtime 门禁已落地 |
| 6 | P1-B：`dependencies.py` 内部模块化（已完成） | v10/v1/Manifest/ExecutionPlan/Catalog/inspect/diagnostics exact characterization 已落地；无协议升级或 consumer 迁移 |
| 7 | P2：当前协议版本与 Analysis producer 门禁（已完成） | `protocols.py` 单一映射、静态文档回归和严格 producer 已落地 |
| 8 | P3：Query Parameter 紧凑集合与 Dashboard-owned 物化候选（已完成） | v14/v2/v3/v1 协议迁移、Store、Lookup、Source binding、bundle、UI、完整测试与发行包验证已落地 |
| 9 | P4：Workspace Asset（已完成） | v2/v15/v6/v11、Bundle v2、Report Manifest v3 与 Browser/portable parity 已落地 |
| 10 | P5：原生 Map View + Entity Select Scaffold（已完成） | `map-lab` 的 point/region 两个真实 View 已删除 Custom Renderer 需求；复用 P3/P4/Plotly 现有 owner，不引入共享 Source 或第二状态模型 |
| 11 | P6：作者可观察性与开发反馈（已完成） | Query explanation、Result 输入复用、Map layers、参数作者投影和 Table emphasis 均复用既有 canonical owner；未增加第二套执行、状态或 Renderer |
| 12 | P7：Runtime 增量反馈与既有能力闭环（已完成） | Asset File Source 封存、stale-while-update、多输入 Renderer 文档与 Runtime 刷新因果已闭环；输出级依赖保持延后 |

P1-A、P1-B、P1-C、P1-D 已作为边界清楚的工作流分别完成；P1-B 只在 characterization expected 冻结后提取私有 derivation，没有迁移 consumer 或改变协议。P2 只增加 current-version 投影门禁与严格 producer，不改变 tolerant reader。P3 作为独立破坏式迁移删除了旧 Parameter Domain 双路径。任何后续删除协议、改变 Analysis reader 兼容性或重命名 public symbol 的决定仍必须先通过 P0.0 gate。

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

- 通用原始大表 View 的服务端分页或按需 Record Batch；P3 的 Parameter Lookup cursor 只读取 Dashboard 候选物化，不自动扩张为任意 View/Output 分页框架。
- Browser asset bytes 上传、远程 URL 抓取、Blob/data URL 持久化或通用 Binary Artifact materializer；P0 只要求能力矩阵和稳定 fail-fast，完整支持由真实 image/file Result/Share 需求触发，成功物化继续返回现有 `ArtifactDescriptor`。
- `number-range`、month/quarter/year 日期控件、Transfer、通用 Entity Picker Runtime 或 Drawer；P5 只提供组合现有契约的 Entity Select Scaffold。
- Workspace 级 Python 工具库；当前普通执行逻辑继续 Dashboard-local，只有多个真实项目证明 helper 重复显著且可搬运依赖闭包能够保持单一 owner 后才重新评估。
- 多套命名 Presentation、HTML Analysis Capsule、HTML Output 提取或远程分享链接分析。
- 多进程共同写一个 Workspace、内建账号体系、多租户资源配额或不可信代码沙箱。
- 自动 Apply Promote、自动 certified，或绕开人工审阅的知识写回。

## 明确非目标

- 旧实验契约兼容层、自动迁移或双协议 Runtime。
- 可编辑数据逻辑、依赖、布局或样式的通用网页开发器；Mosaic、坐标布局和旧 Widget 协议。
- 让 Python 直接操作 DOM 或成为第二套 View Renderer。
- Interactive Transform 隐式访问 Adapter 或重新查询 Source。
- Workspace 级共享 Source、Transform、View、Parameter Domain 或业务 SQL；稳定语义通过 Catalog Output 发现，静态文件通过 Workspace Asset 搬运，所有取数逻辑保持 Dashboard-local。
- 为 Analysis Plane 复制 Dependency Contract、Query Executor、InteractionExecutor 或 Browser Runtime。
- 让 AI 通过图像像素反推本可直接读取的 Base/Derived Output。
- 在没有真实需求和证据前增加空接口、Runtime、图表引擎或重复组件。

## Definition of Done

公开能力必须同时具备：严格 Schema 与稳定错误码、`validate` 提前发现、机器可读 CLI 文档、默认样式和扩展 hook、契约与真实浏览器测试、Server/HTML 一致行为、局部更新与状态隔离，以及准确的 README、DESIGN、plan 和 CHANGELOG。

同一语义存在 Python/JavaScript/Web Component 等多个实现时，还必须证明：规范 expected 只存在于共享 conformance corpus；所有适用实现得到相同 canonical value、rows、signature 或 error code；Browser source 与生成 bundle 同步；未支持的 Output kind/transport 在最早可判断边界稳定失败。没有这些证据，不得仅凭某一端 unit test 把跨 Runtime 能力勾为完成。

Typed comparison 完成还必须证明：operator × `value_type` 的允许表、coercion、空值和稳定错误在 Python、Canvas 与 Web Component 完全一致；数值 `2/10`、日期边界、文本排序决策、boolean operator 与不可转换输入均有 fixture；类型只来自声明和可选静态 Schema 校验，不通过逐行数据猜测。任何可观察语义变化必须有单独版本决定。

Query Parameter 与 Parameter Domain 完成还必须证明：static/SQL-materialized 之外没有第三条候选路径；SQL Domain 的远端查询只构建当前 Dashboard 的 immutable generation，父级、搜索和 cursor 分页都只读 pinned generation；`all/include/exclude/none` 在 Browser、Python、SQL filter、CLI、Result 与 HTML 一致；Reload/Revert、stale/hard expiry、失败回退、并发 lease、Server restart、visibility scope、reader pin/prune、同 Dashboard 多 tab 复用与跨 Dashboard 隔离都有确定结果。浏览器只持有当前页与有限 operands，固定规模 benchmark 必须证明响应有界；`dataviz bundle` 复制完整 Dashboard 与实际引用的 Workspace Asset，不复制 `.dataviz`、无关文件或凭据。

Workspace Asset 完成还必须证明：注册与 Browser allowlist 分离；File Source `asset:<id>` 与 Browser service 不互相授权；所有路径保持在 Workspace 内；Server URL 与 portable inline 对同一 `context.assets` 调用返回等价 bytes/text/JSON；Bundle 闭包包含 Browser/File Source 引用并排除未引用文件；目标不存在/为空门禁、staging hash 校验、来源变化失败清理与一次发布确定；AI context、Report Manifest 与日志只包含元数据而不重复泄露内容。

Control authority 收敛完成还必须证明：Server/Portable 使用同一个 ControlRuntime 实现；hello/restore/ready 不死锁且无 checkpoint 也能启动；Shell 只发送 typed action、保存最后确认 checkpoint 和显示所需 Header projection；只有 ControlRuntime 增加 Control revision，Server Python 不成为第二个 normalization reducer；普通连接采用“逐消息校验 identity”或“握手后绑定 MessageChannel port”中的一种；`consumer_revisions` 可由 Contract、Control state 与 applied revisions 重建且不能驱动执行；consumer 只在其启动时捕获的 generation 真正成功后推进；Result/Export 原子封存自包含的 `applied_control_state`。旧 frame、Contract mismatch、重复 action、stale version、迟到恢复与断连均有确定结果；没有 characterization 反例时，不以额外 transport sequence 或全量实时 audit graph 作为完成条件。

内部架构收敛还必须证明：现有公开 Schema、Dependency/Layout/Runtime projection 未发生无意变化；`LoadedDashboard` 继续分别持有和缓存三份 canonical lazy Contract，每个事实只有一套 derivation，Contract 间依赖显式、单向且无环，不新增包裹 owner、总编译 pass 或长期中间 plan；请求级 ExecutionPlan 只由当前 Contract 与 RunRequest 派生；recovery diagnostics 不能产生可执行 partial fact。CLI `run`/显式 Target API 只作 Adapter，`run_analysis()` 与直接 CLI 路径产生相同 immutable Result/provenance，普通 Server RunManager 生命周期未被合并。若实施多 View writer，还必须证明多个 writer 不产生反馈循环、隐式 union 或第二 authority，并且 source View 可审计。公共或持久化变化必须先通过最小 boundary/bump gate，最终登记进同一 canonical metadata source 并关联 conformance suite。

Analysis Plane 还必须证明 Output 语义和可信度可审查、Catalog 可重建且并发安全、CLI 复用 Server/Browser Runtime 的同一执行语义、Result/Evidence 携带可验证 provenance，且 Promote 只产生可 validate 和 Git 审查的普通 Workspace 变更。计划项只有在实现、测试和文档都完成后才能勾选。

# Dataviz Current Status and Roadmap

更新时间：2026-08-23

本文记录当前实现与后续工作。稳定产品边界见 [产品架构](docs/product-architecture.md)，使用入口见 [README](README.md)。

## 1. 产品目标

Dataviz 只优化两件事：

1. 提供体验可靠、契约清晰的 Section、View、Selector 和 Renderer 模板，减少用户困惑与 AI 试错。
2. 让 AI 用尽可能少且聚焦的上下文完成看板开发，同时保留从默认模板到完整 Canvas 的扩展空间。

以下约束属于当前设计，不是待选方案：

- 执行链为 `Adapter → Source → Server Transform → Named Output → Browser Transform → View Renderer → Presentation`，两个 Transform 都可选。
- Query Parameter 触发服务端执行；Selection 只处理浏览器已有数据。
- 页面内容可用受限 `{{ parameters.<id> }}` 引用最近一次 Run 已提交的 Query Parameter；Selection 不进入查询标题插值。
- View 只等待自己的依赖闭包，不受无关慢分支或失败分支阻塞。
- 无 Presentation 时使用朴素文档流；完整 Canvas 不受坐标网格约束。
- `dashboard.yaml` 负责分析逻辑，`presentation.yaml` 负责可选视觉覆盖。
- Dashboard 目录最后一段就是侧边栏显示名；`dashboard.id` 是稳定机器 ID，页面 `title` 不是导航别名。
- 当前只维护严格的 `dataviz/*/v1` 契约；Schema 变化直接迁移项目文件，不增加兼容执行分支。
- 浏览器框架只消费 `dataviz/runtime/v1` 协议；Runtime 契约不绑定某个 UI 框架。

## 2. 已完成

### 数据与执行

- [x] File、SQL、Python Source，以及文件、DuckDB、MySQL、StarRocks/SQLAlchemy Adapter。
- [x] Dashboard 逻辑 Adapter 到 Workspace 本地 Adapter 的映射，凭证与可分享看板分离。
- [x] Source 与 Server Transform 统一使用 OutputBundle / Named Output。
- [x] Table、scalar、object、text、html、chart、image、file Output Contract。
- [x] Server Transform DAG：多输入、参数、多输出、输入/输出 Table Schema。
- [x] Python 节点 fresh spawn 子进程、硬超时、完整 traceback 和 execution-log Artifact。
- [x] 缓存指纹覆盖入口代码、`code_dependencies`、声明依赖包版本、参数、Adapter 和上游 Artifact。
- [x] `run --target` 与 `output` 支持按依赖闭包执行和检查任意 Named Output。
- [x] SQL Source 在 Run Snapshot/Result 中保存无凭证查询证据：解析 SQL、实际参数化 statement、bound parameters、Adapter 类型、SQL 文件、超时策略和 query hash；成功、缓存、失败状态一致可查。

### 渐进式 Runtime

- [x] 从 View/Browser Transform 反推服务端目标闭包。
- [x] Node Output 完成立即写入 Run Snapshot，并通过 `output_ready` SSE 发布。
- [x] Canvas Shell 为每个 View 提供独立 Loading、Ready 和 Error 状态。
- [x] OutputStore 增量注入，只更新受影响 View。
- [x] `run_id`、Session 和 Dashboard 三层隔离；跨 tab 不能访问或复用彼此 Run。
- [x] 同一 tab 的 Dashboard 状态独立，切换页面不会取消其他 Dashboard 的查询。
- [x] Workspace 级并发 Run 上限、嵌入行数上限和字节上限。

### 浏览器计算与交互

- [x] Browser Transform 独立 JS 文件、拓扑执行、Named Output 和依赖失效图。
- [x] Dashboard / Section / View Selection 的 include 语义与作用域传播。
- [x] Selection Contract 按实际字段和显式 `selection_bindings` 判断 View 是否受影响。
- [x] 跨作用域级联会收缩选项并清理失效值；单 Selector 支持 `path_fields` 多层 Cascader。
- [x] Registry v3 的 `select`、`segmented`、`checkbox-group`、`cascader`、`tree-select`、`date-range` Selector；搜索与虚拟滚动是 `select` 能力，不再是独立模板。
- [x] Selection 面板点击外部或按 Esc 收起；View 级交互只重绘目标 View。
- [x] Canvas 完整 Selection 状态采用替换语义；历史 sessionStorage key 在接收时清理，导出边界再次按当前 Contract 过滤。
- [x] Server 和导出 HTML 共用同一 Selection、Transform 与 Renderer Runtime。

### Renderer、模板与 Presentation

- [x] Plotly、ECharts、Metric、普通 Table、Perspective、Markdown/Text、Image Renderer。
- [x] Renderer 生命周期统一为 `validate/mount/update/dispose`，单 View 扩展显式注册。
- [x] Table/Perspective 的滚轮边界释放与短内容页面滚动处理。
- [x] `small-multiples` 和 `selection-gallery` 使用共享 Dataset 与重复 View 蓝图。
- [x] 默认 Section/View 单列文档流和语义 Section 模板。
- [x] 功能 CSS 与默认视觉 CSS 分层；可选 `presentation.yaml` 按稳定 ID 覆盖。
- [x] 自定义 Canvas 可以自由布局稳定 View Host，不依赖坐标网格协议。
- [x] Dashboard、Section、View 与 Markdown 内容支持安全 Query Parameter 插值，并随 Server Run 和导出 HTML 使用同一已提交参数上下文。
- [x] `dataviz/runtime/v1` Manifest 作为 Python 生成层与浏览器实现之间的边界。

### Workspace 与 AI 开发体验

- [x] `##` 物理目录协议、空目录、拖动移动、回收站和磁盘重新扫描。
- [x] 文件夹最后一段直接作为导航显示名，不读取额外别名。
- [x] 单个损坏、重复或手动移除的 Dashboard fail-soft，不拖垮整个 Workspace。
- [x] 严格 Pydantic Schema；未知字段、无效引用和损坏资源给出结构化诊断。
- [x] `dataviz validate` 升级为无查询静态 preflight：支持 `--dashboard` 聚焦、`dataviz/validation/v1` JSON、稳定检查域/错误码/修复提示、SQL 参数双向检查和 `--strict` CI 门禁。
- [x] Component Registry 覆盖全部严格 View/Section/Layout/Theme 模板。
- [x] `docs`、`components`、`gallery`、`context --focus`、`scaffold` 和 `benchmark` CLI。
- [x] 内置 Gallery 使用生产 DSL 与 Runtime，并可导出为交互 HTML。
- [x] 发行 ZIP 构建脚本和 Runtime/Gallery/authoring 包资源。

## 3. 当前验证基线

2026-08-23 本地核验结果：

- [x] Python 3.11、3.12、3.13、3.14：各 124 项 unit/contract tests 通过；Chromium、Firefox、WebKit 各 9 项真实浏览器 tests 通过。
- [x] 0.1.1 pip ZIP 在干净 Python 3.12 环境完成 `version`、`docs validation`、`init`、focused `validate` 和 HTML report smoke；wheel、sdist、ZIP 均确认不包含 `.venv`、`build/`、Workspace `.dataviz` 或 `uv.lock`。
- [x] 四个示例 Workspace 严格校验通过。
- [x] Canvas、Declarative、Worker 与 Web Component Adapter JavaScript 通过 `node --check`。
- [x] README 最小 Dashboard 通过当前 Pydantic Schema。
- [x] wheel、sdist、pip ZIP 分别在干净 Python 3.12 环境完成安装与 HTML smoke；ZIP 连续构建 SHA-256 一致。
- [x] Registry v3 wheel 仅包含 13 个当前 Component Package；安装版 `components --check`、`docs selections` 与 Selector scaffold 通过，干净构建不会带入源代码之外的陈旧 Package。
- [x] 真实浏览器 E2E 覆盖弹层、级联、View 隔离、滚动、渐进分支和连续 Run。

测试重点包括 Adapter、严格 DSL、Named Output、Transform、缓存、超时、渐进分支、Session 隔离、Workspace 命名和 authoring CLI。源码开发采用 `uv sync --no-editable`，pytest 通过项目配置发现 `src`，不再要求手工设置 `PYTHONPATH`。

## 4. 已完成里程碑

P0、P1A、P1B 与 P2 已在当前版本完成并通过第 3 节的验证。这里保留每个阶段的验收边界，避免后续只根据功能名称误判实现程度。

### P0：正确性与开发可靠性（已完成）

- [x] 真实 Chromium E2E 覆盖点击外部收起、Selection 三级联动、Cascader 多分支选择、View 重绘隔离、Table/Perspective 滚动、渐进分支失败和连续 Run 隔离。
- [x] 真实 Chromium E2E 覆盖 Query Parameter 内容只在重新 Run 后更新、历史 Selection key 清理和导出 Contract 白名单。
- [x] Server Sources 弹层中的每个节点都可打开 Run Evidence；SQL 同时展示可读 Resolved SQL 与真实参数化 Driver statement，避免用户只能接受结果而无法 review 查询过程。
- [x] DuckDB 与 SQLAlchemy Adapter 统一使用独立查询进程、硬 timeout/cancel 和 `query_timeout` / `query_connection_error` / `query_execution_error` 分类；SQL 默认单次 120 秒、超时立即额外重试一次，Source 可覆盖次数；失败只沿对应 DAG 分支传播。
- [x] 源码安装不再依赖 editable `.pth`：文档与 CI 统一使用 `--no-editable`，覆盖 macOS、Linux、重复 CLI 导入和发行 ZIP 干净安装。
- [x] RunRecord、Artifact 和缓存具备数量/时间保留策略；`dataviz clean` 默认 dry-run，显式 `--apply` 后清理，活动 Run 始终受保护。

当前是可信单机工具。Python/SQL 节点的 CPU、内存配额不属于当前产品范围，也不作为近期任务；若未来进入多租户或不可信代码执行场景，再重新设计资源治理边界。

### P1A：规模与性能（已完成）

- [x] Browser Transform 已移入 fresh Web Worker：支持同步/Promise 入口、supersede cancellation、每节点 `timeout_seconds`、结构化克隆输出和可序列化错误协议。
- [x] 大 Table 已落地 Arrow IPC 自动传输：Server Output API + HTTP gzip，HTML gzip + base64 分片，浏览器异步解码；小表继续使用 JSON。
- [x] Perspective 已建立显式 create、命名 Table、replace/update、flush、ResizeObserver 释放、Viewer/Table dispose 和 v5 主版本/API 兼容检查。
- [x] Repeat 已增加全量分组搜索、`page_size` DOM 上限、Load more、视口懒挂载、离屏 Renderer 回收，以及 1,000 分组真实 Chromium 性能回归。
- [x] `dataviz benchmark --browser-runtime` 可记录 Arrow/Worker/Repeat Runtime metrics、Navigation Timing 和控制台错误。

当前规模边界：Arrow 优化传输与初始解析，但 generic Selection、图表和 Browser Transform 实际读取时仍会物化 JavaScript 行对象；服务端分页、列式浏览器执行和按可见 Record Batch 请求留待后续按真实数据规模决定。

### P1B：Component Package（已完成）

- [x] 13 个物理 Package 为 Registry v3 的 45 个 Component 提供 Manifest、Controller、Adapter、Style、Story 和 Test；共享生命周期的严格模板允许共用一个实现包，`dataviz components --check` 校验 owner、依赖、资产、Story/Test 和完整覆盖。
- [x] Gallery 从 23 个 Story 自动生成清单、锚点与导航，并用生产 DSL/Runtime 展示 specimen；真实 Chromium 覆盖键盘导航、焦点返回、可访问语义、视口几何和 1,000 项 Select DOM 上限。
- [x] `runtime.overlay` 已统一 Server Header、导出 Header、Dashboard/Section/View Selection、Select、Cascader 与 Tree Select 的同组互斥、定位、点击外部关闭、Esc 和焦点返回。
- [x] 六个公开 Selector 共用原生 form control canonical state；`auto` 对大平面选项仍解析为 `select`，只按阈值开启搜索与虚拟滚动。
- [x] `renderer.custom` Scaffold 同时生成 JS、CSS 和 `dataviz/renderer-contract/v1`；Runtime 支持异步 lifecycle、View 级结构化错误边界，`dataviz renderer-test` 在 Chromium 中检查 validate/mount/update/dispose。

已知拆分边界：Overlay、Selector 与 Custom Renderer 已完全由物理 Package 执行；声明式 View Renderer、Repeat、Arrow Output Store、Worker Controller，以及部分 Section/Presentation 桥接实现仍位于 `canvas-runtime.js`、`declarative-runtime.js` 或 Python `CanvasRenderer`。它们已有明确 owner 和稳定契约，但下一轮仍需完成代码归属的物理迁移。

### P2：AI 开发效率与发布（已完成）

- [x] Workspace 根目录使用 append-only `dataviz-authoring.jsonl` 记录 started/friction/finished；CLI 支持 start/note/finish/show，自动记录耗时，并聚合首次成功率、修正轮次、实际 Token 与不清晰文档/设计。拿不到的 Token 保持 unknown，`context` 会主动提示 AI 使用该协议。
- [x] `dataviz schemas [model] [--full]` 直接从安装版本的 Pydantic Schema 生成紧凑字段契约或完整 JSON Schema；`components` 继续直接从 Registry v3/物理 Package 生成行为、DOM、token、Story 与测试文档。
- [x] CI 覆盖 Python 3.11–3.14、macOS non-editable、Chromium/Firefox/WebKit；wheel、sdist 和 pip ZIP 分别干净安装并执行 version/schemas/components/init/validate/report smoke。
- [x] 所有 standalone DSL `schema` 收紧为 Literal；`dataviz migrate` 默认 dry-run，可补无歧义版本头并执行注册的离线 migration，未知 URI 阻断；版本流程与 `CHANGELOG.md` 已落地，Runtime 不保留双协议。
- [x] 第二 Web Component 参考 Adapter 只消费 `dataviz/runtime/v1` Manifest 和公共事件，不引用默认 `window.datavizRuntime`；真实浏览器测试在未加载 Canvas Runtime 时验证 Output、View input 与 Selection include 更新。

P2 已完成“可生成契约、可记录真实开发成本、可迁移、可验证、可发布”的工程闭环。使用入口见 [README](README.md)，评测协议见 [AI Authoring 真实评测](docs/authoring-evaluation.md)，版本流程见 [DSL 版本与发布](docs/versioning-and-release.md)。但“AI 是否真的更省”仍需持续收集真实 `dataviz-authoring.jsonl`，不能因为记录机制完成就宣称达成了某个 Token 或首次成功率目标。

## 5. 当前迭代与后续优化

以下内容不属于 P0–P2 的未完成验收项。P3 的 S0 已进入实现，其余项目继续根据真实使用数据降低代码债务、交互回归和大数据瓶颈。

### P3：Selection 交互体系（S0 第一阶段已完成）

本节以 [Ant Design Component Overview](https://ant.design/components/overview/) 及其 Select、Cascader、TreeSelect、DatePicker 等官方文档作为交互语言参考，不要求 Runtime 引入 Ant Design。Dataviz 要复用成熟的行为约定，同时继续保持框架无关的 `dataviz/runtime/v1` 契约和轻量导出 HTML。

#### 设计结论

1. **Selection 逻辑与控件外观必须分离。** `type`、字段、include 值、作用域和级联依赖属于数据契约；搜索、虚拟滚动、已选标签折叠等属于控件能力。
2. **减少公开模板的同义项。** 平面数据选择只有一个标准 `select`；`search`、`virtual`、`max_visible_tags` 等是能力参数。Ant Design 的 Dropdown 是操作菜单，数据选择使用 Select。
3. **`auto` 必须可预测。** AI 可以只声明数据语义，Runtime 根据单选/多选、层级、数据类型和选项规模选择控件；显式 `component` 永远覆盖自动决策。
4. **级联后默认只展示仍可选的值。** 上游 Selection 改变后，应立即重算下游选项、清除失效值并更新视图；不保留 disabled 的“幽灵选项”。只有诊断模式才允许显示 unavailable 值及原因。
5. **布尔筛选不默认使用 Switch。** 数据 Selection 通常需要“全部 / 是 / 否”三态；Switch 只适合立即生效且没有“全部”的二态设置。
6. **只实现当前 Registry。** Registry v3 不维护旧组件别名，也不提供旧 Registry 的离线改写；未知组件 ID 在校验期直接失败。

#### S0：优先开发

| 顺序 | Component | 适用场景 | 计划边界 |
| --- | --- | --- | --- |
| 1 | [Select](https://ant.design/components/select/) | 常规单选/多选、中大型平面选项 | 建立唯一 `selector.select`；内建搜索、分组、最大选择数、已选摘要、标签折叠、隐藏已选项和自动虚拟滚动。能力开关使用 YAML 安全的 `auto/always/never`，10、100、1,000 个选项使用同一 DSL。 |
| 2 | [Cascader](https://ant.design/components/cascader/) | 省/市/区、组织/团队等“路径本身有意义”的层级选择 | 强化多路径选择、完整路径搜索、父/叶选择策略、独立浏览多分支、级联失效值清理、键盘操作和窄视口定位。不要把官方 `loadData` 与搜索不能同时工作的限制照搬到 Dataviz 数据模型。 |
| 3 | [TreeSelect](https://ant.design/components/tree-select/) | 节点很多、需要展开/收起和跨分支勾选的树 | 补齐父子半选、严格选择、已选策略、树内搜索、懒渲染和多选摘要；与 Cascader 共用 canonical state，而不是另建 Selection 语义。 |
| 4 | [Segmented](https://ant.design/components/segmented/) / [Radio](https://ant.design/components/radio/) | 不超过 4 个、需要始终可见并便于比较的单选 | `auto` 的小规模单选默认使用 Segmented；Radio 作为更朴素、可换行的表现。遵循官方“选项少于 5 个时优先 Radio”的经验边界。 |
| 5 | [Checkbox](https://ant.design/components/checkbox/) / [Checkable Tag](https://ant.design/components/tag/) | 不超过 8 个的平面多选 | 建立 `checkbox-group` 语义组件，支持全选、半选和换行；标签式外观只是视觉 variant，不拥有独立状态控制器。 |
| 6 | [DatePicker / RangePicker](https://ant.design/components/date-picker/) | 日期、月份、季度、年份和区间 | 将当前基础 `date-range` 升级为日历 + 可校验输入；支持快捷区间、粒度、min/max 和可选开放端点。只有显式需要时才启用时间。 |

2026-08-23 的 S0 第一阶段已经完成：

- [x] `selector.select` 统一单选/多选、搜索、Choice 分组和描述、最大选择数、已选标签折叠、隐藏已选项，以及按阈值启用的虚拟滚动；同一 DSL 已用 1,000 项真实浏览器用例验证 DOM 上限。
- [x] Cascader 与 TreeSelect 支持完整路径搜索、跨分支叶子选择、父节点批量选择/清除、半选状态，以及 `child/parent/all` 的已选摘要策略；canonical state 始终保存完整叶路径。
- [x] `segmented` / Radio 和 `checkbox-group` / Checkable Tag 覆盖短列表，并保留 Selection 的“空值表示全部”语义；单选原生控件使用隐藏空值哨兵，避免浏览器误选第一项。
- [x] `date-range` 支持带标签的日期输入、顺序校验、min/max、开放端点、清空与可 review 的精确快捷区间。
- [x] `auto` 决策集中在一个 Python resolver，Server 与导出 HTML 接收相同解析结果；Registry 只接受当前 Selector ID，未知名称严格报错。
- [x] `dataviz docs selections`、`dataviz components selector.*` 和 `dataviz scaffold selector.*` 已覆盖当前公开组件。

日期的 month/quarter/year 专用输入、超大型树的节点级懒渲染，以及完整状态矩阵 Story 属于下一阶段；当前文档不会把这些能力描述成已完成。

#### S1：优先级中等，可在真实看板需要时开发

| 顺序 | Component | 适用场景 | 计划边界 |
| --- | --- | --- | --- |
| 7 | [Slider](https://ant.design/components/slider/) + [InputNumber](https://ant.design/components/input-number/) | 指标阈值、价格/数量区间 | `number-range` 同时提供拖动和精确输入，支持 min/max、step、precision；拖动中只更新预览，在 change-complete 时提交，避免连续重绘全部 View。 |
| 8 | [Transfer](https://ant.design/components/transfer/) | 从几十或几百家门店中明确挑选一组对象 | 提供双栏搜索、选中计数、全选当前可用项和清空；由于占用空间较大，默认放入 Drawer，而不是 Header 小 Popover。 |
| 9 | [Table row selection](https://ant.design/components/table/) | 选项还需要展示地区、状态、负责人等辅助字段 | 设计 `entity-picker`，用可搜索/排序 Table 帮助选择实体；与 Transfer 共用值契约，可作为同一个 Component 的不同 presentation。 |
| 10 | [Drawer](https://ant.design/components/drawer/) | Transfer、Entity Picker、复杂 Selection 编辑 | 作为 Overlay 容器能力扩展，不成为 Selection 类型；复用点击外部、Esc、焦点返回和 Apply/Cancel 生命周期。 |

#### S2：低优先级或暂不作为 Selection 模板

| Component | 判断 |
| --- | --- |
| [AutoComplete](https://ant.design/components/auto-complete/) | 只在将来允许自由输入或创建新值时开发。当前 Selection 是已有数据值的闭集，直接采用会引入无效值。 |
| [Switch](https://ant.design/components/switch/) | 适合“显示预测线”“紧凑模式”等二态展示设置，不适合通常需要 All/True/False 的数据 Selection。 |
| [TimePicker](https://ant.design/components/time-picker/) | 仅在分钟/小时级分析出现真实需求时加入；普通日期看板不应承担额外复杂度。 |
| 常驻 Tree、独立多手柄 Slider | TreeSelect 和 number-range 足以覆盖近期需求，先避免重复模板。 |
| Dropdown、Popover、Modal、Tooltip | 属于 Overlay/动作容器，不是 Selection 数据组件；继续由 `runtime.overlay` 统一管理。 |
| Tabs、Menu、Breadcrumb、Pagination | 属于导航或分页，不进入 Selection Registry。 |
| ColorPicker、Rate、Upload、Mentions | 与分析数据 include-selection 无关，不纳入近期路线图。 |

#### `auto` 的确定性决策表

| 数据语义 | 默认 Component |
| --- | --- |
| boolean include | 三态 Segmented：全部 / 是 / 否 |
| 单选平面值，选项 `<= 4` | Segmented；空间不足时 Radio |
| 多选平面值，选项 `<= 8` | Checkbox Group / Checkable Tag variant |
| 平面值，选项 `> 8` | Select；达到搜索阈值自动启用搜索 |
| 平面值，选项 `>= 200` | 同一个 Select 自动启用虚拟滚动，不改变模板名 |
| 有序层级路径 | Cascader |
| 大型、可展开的树 | TreeSelect |
| date / date_range | DatePicker / RangePicker |
| number_range | Slider + InputNumber（S1 落地后） |

阈值是 Registry 默认值，不进入 Selection 业务语义；Theme 或 Component 配置可以覆盖。自动选择结果必须在 `dataviz validate`、`components` 和浏览器调试信息中可见，避免 AI 猜测 Runtime 最终用了什么。

#### P3 统一验收条件

- [x] 六个公开 Selection Component 都有严格 Schema、物理 Package、Story、CLI 文档、契约测试和真实浏览器交互覆盖；不是独立视觉 Demo。
- [x] canonical state 统一支持 clear、single/multiple、select-all-available、最大选择数和上游级联后的确定性 reconciliation。
- [x] 平面多选保留显式全集：全选真实勾选全部子项并切换为反选，逐项取消不会被“空值代表全部”的归一化吞掉；空值仅表示没有 include 约束。
- [x] 搜索匹配 Choice 元数据；层级组件匹配完整路径并保留父级上下文。
- [x] 多选使用有限标签与 `+N` 摘要；浮层在窄屏和页面边缘自动重定位，1,000 项 Select 使用有界 DOM。
- [x] 点击外部、Esc、焦点返回、键盘选择和 ARIA 基础语义在 Server 与导出 HTML 共用同一组件实现。
- [x] Selection 变化只重算受影响的 Browser Transform 和 View，View Selection 不再造成兄弟 View 闪烁。
- [ ] Gallery 继续补齐 10/100 项独立 specimen、Selector Loading/Error/Unavailable 状态矩阵和超大型 Tree 的懒渲染；1,000 项、动态级联、窄视口和三种作用域已有真实浏览器覆盖。
- [x] Registry、Runtime、CLI 文档和发行包只包含当前 Selector；没有旧组件别名或迁移分支。
- [ ] 用真实 authoring log 比较 Registry v3 与直接生成完整 HTML 的文档读取量、首次成功率和修正轮次。

### 其他工程候选

1. 把声明式 View Renderer、Arrow Output Store、Worker Controller、Perspective Adapter、Repeat Controller 和剩余 Section/Presentation 桥接实现迁入现有物理 Component/Runtime Package。
2. 用真实默认看板、三级 Selection、复杂 Transform、多 Output 与自定义 Renderer 任务积累 authoring log，再据此修改文档、Schema 和模板。
3. 为 Story fixture 增加 Loading/Empty/Error 独立状态画布和跨浏览器像素基线。
4. 根据真实大数据看板的 benchmark 决定是否进入服务端分页、Record Batch 按需获取和浏览器列式执行。

# Changelog

Dataviz 的 package、DSL、Component Registry 与浏览器 Runtime 分别版本化。这里记录使用者可观察到的变化；字段细节以 `dataviz schemas` 和 `dataviz components` 为准。

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
- 源码 CLI 文档固定使用 non-editable `uv sync --reinstall-package workspace-dataviz`，规避部分 macOS/Python 组合忽略 hidden editable `.pth` 导致的 `ModuleNotFoundError`；发布 smoke 仍使用独立干净环境。
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

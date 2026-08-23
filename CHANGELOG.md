# Changelog

Dataviz 的 package、DSL、Component Registry 与浏览器 Runtime 分别版本化。这里记录使用者可观察到的变化；字段细节以 `dataviz schemas` 和 `dataviz components` 为准。

## Unreleased

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
- 新增五类固定 AI authoring 对照任务、带任务/输入哈希的 `authoring prepare`、`authoring verify/assess`、`authoring-event/v3` trial identity 与逐项验收证据，以及 `authoring tasks/protocol/compare` 成对评测；只有身份一致、输入完整且两边全部验收通过的 pair 进入效率聚合。

### Fixed

- Query/Compute/Selection 在 Python、父页面与 Canvas 共享严格 Value Contract；整数不再被浏览器静默截断，空日期范围固定为 `[]`，typed choice、required、min/max/step 使用稳定错误码。
- Named Output 严格校验 required/optional、kind、JSON 与 Table schema；直接返回已有 Artifact 也不能绕过声明契约。
- server-python Interactive 依赖链可复用相同 Query Run 与状态下已经完成的上游 generation；Interaction/event/cache 内存保留量有界。
- Run/Interaction 事件截断使用单调 offset，长时间轮询不会因保留窗口移动而漏掉后续事件。
- snapshot 的可选 Output 不再被误判为缺失并触发重算。
- Pyodide package catalog 对齐固定 Runtime；bundle 校验核心文件、lockfile、`micropip`、传递 wheel 闭包与 SHA-256 后随 ZIP 分发。没有活动 browser-python 的报告不再携带 Python Worker、Pyodide URL 或 bundle 资产。
- 源码 CLI 文档固定使用 non-editable `uv sync --reinstall-package workspace-dataviz`，规避部分 macOS/Python 组合忽略 hidden editable `.pth` 导致的 `ModuleNotFoundError`；发布 smoke 仍使用独立干净环境。

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
- `dataviz migrate` 离线迁移入口、严格 `dataviz/*/v1` Literal 以及 Web Component Runtime v1 参考 Adapter。
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

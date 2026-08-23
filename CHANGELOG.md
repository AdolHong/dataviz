# Changelog

Dataviz 的 package、DSL、Component Registry 与浏览器 Runtime 分别版本化。这里记录使用者可观察到的变化；字段细节以 `dataviz schemas` 和 `dataviz components` 为准。

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

当前仍是 `0.x`：新 DSL 版本会提供显式离线 migration 和 changelog，但允许强制迁移已有 Workspace。

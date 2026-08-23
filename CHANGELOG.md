# Changelog

Dataviz 的 package、DSL、Component Registry 与浏览器 Runtime 分别版本化。这里记录使用者可观察到的变化；字段细节以 `dataviz schemas` 和 `dataviz components` 为准。

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

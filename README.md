# Workspace Dataviz

Workspace-first 的数据看板工具：Python 负责取数、服务端计算和 Server，浏览器负责 Selection、轻量计算与渲染。Server 面向人提供交互页面，CLI 面向 AI、自动化和 HTML 报告。

Dataviz 的默认开发方式是填写稳定 DSL、复用组件模板，而不是为每个看板重写整页 HTML/CSS/JavaScript。普通看板只需要数据、View 和顺序；特殊页面再通过 `presentation.yaml`、自定义 Renderer 或完整 Canvas 扩展。

## 核心模型

```text
Adapter
  ↓
Source
  ↓
Server Transform（可选）
  ↓
OutputBundle / Named Output
  ↓
Browser Transform（可选）
  ↓
View Renderer
  ↓
Presentation
```

- Adapter 保存 Workspace 本地的数据连接与文件访问边界。
- Source 从文件、SQL 或可信 Python 入口读取数据。
- Server Transform 用隔离 Python 进程执行复杂、多输入计算。
- Source 和 Transform 都可产生多个有名称、有类型的 Output。
- Browser Transform 只处理已经加载的数据，不重新查询。
- Renderer 将 Output 展示为图、表、指标、文本或自定义 View。
- Presentation 只调整布局、容器、组件和样式，不改变分析逻辑。

简单路径可以只有 `Source → View`。正式页面术语是 `Canvas → Section → View → Component / Renderer`。

## 当前能力

- Python 3.11–3.14，推荐 3.12。
- File、SQL、Python Source；DuckDB、MySQL、StarRocks/SQLAlchemy 和本地文件 Adapter。
- Server Transform DAG：多输入、多 Named Output、Table Schema、缓存、子进程隔离、硬超时、traceback 和运行日志。
- Browser Transform DAG：独立 Web Worker、同步/异步 JavaScript、Selection 依赖、取消、硬超时、可序列化错误和分支级失败隔离。
- Plotly、ECharts、普通 Table、Perspective、Metric、Markdown/Text、Image 和自定义 Renderer。
- Dashboard / Section / View Selection；统一 Select、小选项 Segmented/Checkbox Group、日期范围、多层 Cascader 和 Tree Select。搜索与虚拟滚动是 Select 能力，不再是独立模板。
- `small-multiples` 与 `selection-gallery` 重复 View；内置搜索、分页式 DOM 上限、视口懒渲染和离屏图表回收。
- 默认单列页面、语义 Section 模板、可选 Presentation 和不受坐标网格限制的完整 Canvas。
- 分支级渐进执行：一个 View 的依赖完成后即可展示，不等待无关慢分支。
- Sources 是可点击的查询证据入口：每个节点展示本次 Run 的状态、执行/缓存来源、耗时与错误；SQL 还展示解析后 SQL、参数化 Driver statement、bound parameters、Adapter 和超时策略。
- 同一浏览器 tab 内按 Dashboard 隔离状态；不同 tab、浏览器和用户不共享 Selection 或默认缓存。
- 大 Table 自动使用 Arrow IPC；Server 走 HTTP gzip，HTML 导出使用 gzip + base64 分片并在浏览器延迟解码。
- 可交互 HTML 导出；Server 与 HTML 使用同一浏览器 Runtime。
- 文件夹驱动的导航、拖动移动、空目录和回收站。
- 面向 AI 的内置文档、Pydantic 生成 Schema、Component Registry、Gallery、focused Context、Scaffold、确定性 Benchmark 和真实 authoring 日志。
- `dataviz validate` 静态 preflight：支持 Dashboard 聚焦、稳定 JSON 错误码、修复提示和严格 CI 模式，不查询数据即可检查 Schema、Adapter、SQL 参数、DAG、Selection、Renderer 与资源。
- 严格 DSL 版本、离线迁移器、可复现 pip ZIP，以及 Python/浏览器/发行物 CI 矩阵。

完整职责边界见 [产品架构](docs/product-architecture.md)，当前完成度与后续工作见 [计划](plan.md)。

## 安装与启动

源码开发：

```bash
uv sync --python 3.12 --extra dev --no-editable --reinstall-package workspace-dataviz
uv run --no-editable dataviz --help
```

源码环境统一使用 `--no-editable`，避免依赖 editable `.pth`，也规避部分 macOS/File Provider 环境把 `.pth` 标记为 hidden 后出现的 `ModuleNotFoundError: dataviz.cli`。非 editable 安装不会自动感知源码变化，因此修改框架源码后重新执行上面的 `uv sync ... --reinstall-package workspace-dataviz`。

创建一个最小 Workspace：

```bash
uv run --no-editable dataviz init myworkspace
uv run --no-editable dataviz serve myworkspace --port 8080
```

打开 `http://127.0.0.1:8080`。命令必须写在同一行；Shell 换行时需要在上一行末尾加 `\`。

安装发布 ZIP 或 wheel 后，不再需要 `uv run`：

```bash
python -m pip install /path/to/workspace-dataviz-0.1.2.zip
dataviz serve /path/to/workspace --port 8080
```

生成 pip 可安装 ZIP：

```bash
uv build                              # wheel + sdist
python scripts/build_release_zip.py
```

ZIP 同时生成 `.zip.sha256`；内容使用固定顺序和时间戳。发布流程会把 wheel、sdist、ZIP 分别安装到干净环境再运行 CLI、Component 与 HTML smoke test。

校验并安装发布 ZIP：

```bash
cd dist
shasum -a 256 -c workspace-dataviz-0.1.2.zip.sha256
python -m pip install workspace-dataviz-0.1.2.zip
dataviz version
```

Excel 支持是可选依赖：

```bash
python -m pip install 'workspace-dataviz[excel]'
```

## AI 开发入口

新的 AI 会话应先读取小而精确的内置 Context，不需要先阅读 Runtime 源码：

```bash
dataviz authoring start /path/to/workspace \
  --dashboard DASHBOARD_ID \
  --task "Describe the requested dashboard change"

dataviz docs quickstart
dataviz docs pipeline --format json
dataviz schemas dashboard --format json
dataviz components --format json

dataviz list /path/to/workspace
dataviz context /path/to/workspace DASHBOARD_ID --focus view:VIEW_ID --format json
dataviz validate /path/to/workspace --dashboard DASHBOARD_ID --format json
```

`context` 也会返回 `authoring_feedback`，提示 AI 在任务结束时写入 Workspace 根目录的 `dataviz-authoring.jsonl`。该文件只保存实际测得的首次成功、修正轮次、耗时、可用 Token 与不清晰点；缺失 Token 保持 `unknown`，不做估算。它可提交 Git 或直接分享给 Dataviz 作者，详见 [AI Authoring 真实评测协议](docs/authoring-evaluation.md)。

这套记录解决的是“可以用真实任务评估 AI 开发效率”，并不代表目前已经证明 Dataviz 节省了固定比例的 Token。首次成功率、输入/输出量和目标阈值必须在积累真实 `dataviz-authoring.jsonl` 后再确定。

### 编辑后的固定 Preflight

每次修改 `dashboard.yaml`、Source/Transform、SQL、Presentation 或资源路径后，先执行：

```bash
dataviz validate WORKSPACE --dashboard DASHBOARD_ID --format json
```

该命令使用稳定的 `dataviz/validation/v1` 输出，且 `queries_executed` 固定为 `0`。它不会连接数据库、执行 Source 或启动 Server，适合 AI 在把结果交给用户之前反复运行。重点字段是：

- `passed` 与 `exit_code`：是否可以进入 query/report 阶段。
- `checks`：Schema、Adapter、SQL、DAG、内容/Selection、Presentation 和依赖七个检查域。
- `diagnostics`：稳定 `code`、Dashboard、相对文件、字段、Schema 细节和可执行的 `hint`。
- `next_actions`：当前状态下最短的后续动作。

分享或 CI 门禁可增加 `--strict`，让 warning 也返回退出码 `1`。默认输出是面向人的 text；AI 和自动化统一使用 `--format json`。只改一个 Dashboard 时应始终带 `--dashboard`，避免 Workspace 中另一个暂时损坏的画布干扰本次迭代。完整契约可运行：

```bash
dataviz docs validation --format json
```

通过 preflight 后再逐层查询。Server 页面中可打开 `Sources` 并点击节点核对本次 Run 证据；SQL 的 `Resolved SQL` 是便于 review 的字面量预览，实际数据库请求仍是参数化 Driver statement 与 bound parameters，不会把拼接后的预览 SQL 用于执行。

常用开发命令：

```bash
# 分层检查 Source、Named Output 和完整 DAG
dataviz validate WORKSPACE --dashboard DASHBOARD_ID --format json
dataviz query WORKSPACE DASHBOARD_ID --source SOURCE_ID --param start_date=2026-01-01
dataviz output WORKSPACE DASHBOARD_ID transform:MODEL_ID/trend --format json
dataviz run WORKSPACE DASHBOARD_ID --target transform:MODEL_ID/trend

# 导出交互 HTML
dataviz report WORKSPACE DASHBOARD_ID --output report.html

# 查看组件契约、生成模板和打开真实 Runtime Gallery
dataviz schemas view --format json
dataviz docs selections
dataviz components selector.select
dataviz components selector.cascader
dataviz components --check
dataviz scaffold view.line --id revenue
dataviz scaffold selector.select --id region
dataviz scaffold selector.tree-select --id location
dataviz gallery
dataviz gallery --output component-gallery.html

# 自定义 Renderer 同时生成 JS、CSS 与契约；在 Chromium 中验完整生命周期
dataviz scaffold renderer.custom --id team.spark --output ./renderer-recipe
dataviz renderer-test ./renderer-recipe/assets/team.spark.js \
  --renderer-id team.spark \
  --contract ./renderer-recipe/assets/team.spark.contract.json

# 比较完整 Context 与 focused Context 的确定性大小
dataviz benchmark WORKSPACE DASHBOARD_ID --format json

# 再在真实 Chromium 中测 Arrow、Worker、Repeat 分组/挂载和页面时序
dataviz benchmark WORKSPACE DASHBOARD_ID --browser-runtime --format json

# 先预览，再清理旧 Run Artifact 与缓存
dataviz clean WORKSPACE
dataviz clean WORKSPACE --apply

# 完成真实 AI authoring 记录
dataviz authoring note WORKSPACE SESSION_ID \
  --category documentation --reference selections --message "Unclear behavior"
dataviz authoring finish WORKSPACE SESSION_ID \
  --outcome success --first-attempt failure --correction-rounds 1
dataviz authoring show WORKSPACE --format json

# 预览/执行离线 DSL 迁移；未知版本会阻断，不会进入 Runtime
dataviz version
dataviz migrate WORKSPACE
dataviz migrate WORKSPACE --apply
```

更多主题可用 `dataviz docs` 查看，包括 Source、Output、Server/Browser Transform、Renderer、Selection、Repeat、严格 Schema、运行边界和排错流程。

## Workspace 契约

```text
workspace/
├── workspace.yaml
├── auth/
│   ├── adapters.example.yaml
│   └── adapters.local.yaml       # 本地凭证，不提交 Git
└── dashboards/
    ├── sales/
    │   ├── dashboard.yaml        # 必需：逻辑
    │   ├── presentation.yaml     # 可选：呈现
    │   ├── sources/
    │   ├── transforms/
    │   ├── data/
    │   ├── assets/
    │   └── canvas/               # 可选：完整自定义页面
    └── 业务分析##门店周报/
```

Dashboard 目录名是导航事实来源：`##` 前的段表示目录路径，最后一段就是侧边栏显示名，不存在另一个显示别名。

- `sales` 显示在根目录，名称为 `sales`。
- `业务分析##门店周报` 显示为 `业务分析 / 门店周报`。
- `__TRASH__##sales` 位于回收站，原 Dashboard 文件仍保留。

`dashboard.id` 是 CLI、DAG 和缓存使用的稳定机器 ID；`title`、`subtitle`、`description` 是画布内容，不参与侧边栏命名。`workspace.yaml` 只补充 Runtime 配置、空目录和顺序；Server 会重新扫描手动复制、改名或移除的 Dashboard，并隔离单个损坏目录。

## 最小 Dashboard

一个无需前端代码的自包含看板：

```yaml
schema: dataviz/dashboard/v1
kind: dashboard
id: sales-overview
title: 销售概览

sources:
  - id: sales
    kind: source
    type: file
    path: data/sales.csv
    format: csv

dashboard_selections:
  - id: region
    label: 区域
    type: multi_select
    field: region

views:
  - id: revenue
    title: 销售趋势
    template: line
    input: sales
    x: date
    y: revenue
    series: region
    aggregate: sum

  - id: detail
    title: 销售明细
    template: perspective
    input: sales
    columns: [date, region, revenue]

sections:
  - id: overview
    title: 经营概览
    views: [revenue, detail]
```

`input: sales` 是 `source:sales/main` 的简写。没有 `presentation.yaml` 时，Section 和 View 按声明顺序自上而下展示。

### 让分析对象出现在页面中

Query Parameter 不应只藏在 Header 弹层。Dashboard、Section 和 View 的内容字段可以直接引用本次查询已经提交的参数：

```yaml
title: 小时销售与晚间占比
subtitle: "仓 {{ parameters.warehouse_id }} · 商品 {{ parameters.product_id }}"
description: "{{ parameters.start_date }} 至 {{ parameters.end_date }}"

query_parameters:
  - {id: warehouse_id, label: 仓, default: 5740}
  - {id: product_id, label: 商品, default: "980464683"}
  - {id: start_date, type: date, default: "2026-08-09"}
  - {id: end_date, type: date, default: "2026-08-22"}

sources:
  - id: hourly-sales
    type: sql
    adapter: warehouse
    code: sources/hourly-sales.sql
    params: [warehouse_id, product_id, start_date, end_date]
```

只支持安全、可校验的 `{{ parameters.<id> }}` 直接引用，不执行任意 Jinja 或表达式。可用字段包括 Dashboard 的 `title/subtitle/description/assumptions`、Section 的 `title/description`、View 的 `title/description` 和 Markdown `text`。选择参数优先显示 choice label，`date_range` 显示为“开始 至 结束”，多值使用顿号连接。

Server 中编辑参数不会立刻改动旧数据集的标题；点击 **Run query** 后，数据和内容一起提交更新。导出 HTML 固定保存这次 Run 的参数上下文。运行 `dataviz docs interpolation` 可查看机器可读契约。

## Adapter 与凭证

Dashboard 只声明可替换的逻辑绑定：

```yaml
adapters:
  warehouse: team-starrocks
```

真实连接放在 Workspace 的 `auth/adapters.local.yaml`：

```yaml
adapters:
  team-duckdb:
    type: duckdb
    database: data/team.duckdb

  team-mysql:
    type: mysql
    host: 127.0.0.1
    database: analytics
    username_env: MYSQL_USER
    password_env: MYSQL_PASSWORD

  team-starrocks:
    type: starrocks
    host: 127.0.0.1
    port: 9030
    database: analytics
    username_env: STARROCKS_USER
    password_env: STARROCKS_PASSWORD

  shared-files:
    type: files
    root: shared-data
```

分享 Dashboard 文件夹时，同事只需把逻辑 Adapter 映射到自己的本地配置。可信 Python Source 可以通过 `context.adapter` 读取已解析配置；Server Transform 只能消费显式输入，不直接获得凭证。

## Parameter、Selection 与局部更新

- Query Parameter 进入 Source/Server Transform 和缓存键；修改后必须重新 Run query。
- Selection 是浏览器端 include 选择；立即作用于已加载数据，不触发查询。
- `report --selection key=value` 只设置 HTML 的初始选择，不裁掉可继续交互的数据。

Selection 的传播范围是：

```text
Dashboard Selection → 所有绑定 View
Section Selection   → 当前 Section 的绑定 View
View Selection      → 当前 View
```

上游 Selection 会收缩下游可用选项并清除失效值。一个 Selector 内的层级关系使用 `path_fields`，宽屏分栏浏览可选 `cascader`，窄面板树形浏览可选 `tree-select`；`hierarchy_selection: cascade` 允许父节点批量选择后代，`checked_strategy: child|parent|all` 只改变摘要方式，不改变完整叶路径 canonical state。日期区间使用 `date-range`。平面选项统一使用 `select`：搜索和虚拟滚动通过 `search: auto|always|never`、`virtual: auto|always|never` 控制，超过阈值时 `auto` 只切换能力而不更换模板名。不同字段名通过 View 的 `selection_bindings` 显式映射；不包含目标字段的 View 不筛选，也不应重绘。

小规模选项可以保持直接可见：单选不超过 4 项时使用 `segmented`，多选不超过 8 项时使用 `checkbox-group`。两者分别支持 `variant: radio` 与 `variant: tags`，但仍写回同一个 Selection canonical state。完整字段、示例与自动选择规则使用 `dataviz docs selections` 查看。Registry v3 只接受当前公开组件 ID；未知模板直接校验失败，不提供别名或旧 Registry 迁移路径。

`multi_select` 区分“空选择”和“显式全选”：空选择表示没有 include 约束；点击 `select_all_label` 会把所有当前可用值真实写入 canonical state，并将按钮切换为 `invert_label`。所有子项会保持勾选，用户可以直接取消少数项；显式全集不会再被 Runtime 自动折叠为空。当前数据上两者都展示全集，但在后续可用项变化时语义不同。

## Output、Transform 与渐进执行

节点没有显式 `outputs` 时只产生 `main`；复杂计算可以声明多个稳定引用，例如：

```text
source:orders/main
transform:sales-model/trend
transform:sales-model/total
browser:visible-series/main
```

Server 只执行目标 View 的依赖闭包。Output 完成后立即发布，因此 `source:fast → view:summary` 可以先于另一条慢 Transform 分支展示。一次新 Run 通过 `run_id` 与旧结果隔离。

Server Transform 适合 Pandas、模型和多表业务逻辑；Browser Transform 适合跟随 Selection 的浏览器计算。每次执行位于独立 Web Worker，可返回值或 Promise；新的 Selection/Output 会取消旧任务，`timeout_seconds` 默认 30 秒。详细 Schema 和可复制配方使用：

```bash
dataviz docs outputs
dataviz docs server-transforms
dataviz docs browser-transforms
```

SQL Source 默认每次尝试最多运行 120 秒，第一次超时后立即使用新进程、新连接重试一次。可以在内联的 `dashboard.yaml` Source 或独立 Source YAML 中覆盖：

```yaml
sources:
  - id: sales
    kind: source
    type: sql
    adapter: warehouse
    code: sources/sales.sql
    timeout_seconds: 90
    timeout_retries: 2  # 额外尝试次数；0 表示不重试，最大 5
```

重试只响应 `query_timeout`，不会掩盖连接配置、权限或 SQL 语法错误，并且不增加等待间隔。最坏耗时上界约为 `timeout_seconds × (timeout_retries + 1)`。SQL 超时使用独立查询进程硬取消；MySQL 与 StarRocks 还会设置数据库 Session 级 statement timeout。错误类型稳定区分为 `query_timeout`、`query_connection_error` 与 `query_execution_error`。Python Source 仍可显式配置 `timeout_seconds`，但不会自动重试。

## View、Section 与 Presentation

内置 View 包括 `metric`、`line`、`bar`、`stacked-bar`、`pie`、`scatter`、`heatmap`、`radar`、`table`、`perspective`、`markdown`、`image` 和 `custom`。

内置 Section 包括 `single`、`stack`、`grid`、`split`、`hero-metrics`、`chart-and-table`、`comparison`、`band`、`small-multiples` 和 `selection-gallery`。

推荐扩展顺序：

```text
默认模板
  → 模板参数
  → presentation.yaml / Theme token / css_class
  → 单 View 自定义 Renderer
  → 完整 Canvas
```

普通 Table 提供易定制样式；Perspective 提供排序、筛选、分组、透视和图表探索。完整 Canvas 可以自由组织稳定 View Host，但仍复用 Output、Selection 和 Renderer Runtime。

## Component Package

Registry 中每个 Component 都由一个物理包拥有；共享同一生命周期的 View、Section、Layout/Theme 可以共用实现包。包目录固定共置六类资源：

```text
src/dataviz/components/packages/<package>/
├── manifest.yaml   # 版本、依赖、组件与公开契约
├── controller.js   # headless state / lifecycle
├── adapter.js      # 当前 Vanilla Runtime Adapter
├── style.css       # 运行必需结构与可覆盖视觉 token
├── story.yaml      # Gallery specimen 来源
└── test.yaml       # 行为、键盘、可访问性或性能契约用例清单
```

`dataviz components --check` 会检查缺失资产、重复组件、依赖、Story/Test 引用及 Registry 覆盖。`dataviz gallery` 根据 `story.yaml` 自动生成 Story 索引，再把 Story 指向生产 DSL/Runtime 中的真实 specimen；Server 与导出 HTML 都加载同一份 Component Runtime。

当前 Component Registry 版本是 `3.0.0`。`dataviz/component-package/v1`、`dataviz/component/v1`、`dataviz/runtime/v1` 和各 Package 的 `1.0.0` 分别是 Package 文档格式、Component 文档格式、浏览器协议与单个 Package 的独立版本，不代表 Registry v1。Registry v3 没有 v1/v2 Package、别名或兼容加载分支。

当前 `runtime.overlay`、`runtime.selector`、全部 Selector 和 `renderer.custom` 已由包内 Controller/Adapter 直接实现。`view.declarative`、`section.declarative`、`data.pipeline` 与 `presentation.shell` 目前是物理 Package owner 和桥接层；已有 View Renderer、Repeat、Arrow/Worker 与 Python Canvas 生成代码仍在按生命周期逐步搬入对应 Package。这个边界记录在 `plan.md`，不会伪装成已经完成的物理拆分。

所有弹层使用 `runtime.overlay`：同组互斥、点击外部关闭、Esc 关闭并把焦点还给触发器、滚动/缩放时重新定位且不越出视口。Header、Dashboard/Section/View Selection、Select、Cascader 与 Tree Select 不再各自实现一套弹层状态。

除生产用 Vanilla Adapter 外，包内还提供一个零依赖 Web Component 参考 Adapter，用来验证 `dataviz/runtime/v1` 的框架解耦。它只读取公开 Manifest、Output、View input 与 Selection contract，不引用 `window.datavizRuntime` 或 Python Renderer 私有实现：

```bash
dataviz frontend-adapters --format json
dataviz frontend-adapters web-component --output runtime-v1-adapter.js
```

Server 也从 `/runtime/web-component-adapter.js` 提供同一资源。它是契约探针和第二实现样例，不替代功能完整的默认 Canvas。

Repeat 的规模参数直接写在 `repeat` 中：

```yaml
repeat:
  view: store-trend
  by: [store_id]
  render: lazy
  searchable: true
  page_size: 40
  recycle_offscreen: true
```

`page_size` 限制首批卡片 DOM 数，不截断 Dataset；搜索仍覆盖所有分组，“Load more”逐批增加卡片。离开视口缓冲区的 Plotly/ECharts/Perspective 实例会执行 `dispose`，再次滚回时重建。

大表传输由 Workspace Runtime 配置：

```yaml
runtime:
  browser_table_transport: auto  # auto | json | arrow
  arrow_min_rows: 2000
  arrow_chunk_bytes: 524288
  max_embedded_rows: 100000
  max_embedded_bytes: 25000000
```

`auto` 对达到阈值的 Table 使用 Arrow IPC。Server Output API 返回二进制流并由 HTTP gzip 压缩；单文件 HTML 内嵌 gzip 后的独立 base64 分片。浏览器在 Output 就绪时解码 Arrow，避免服务端先构造整表 JSON 和 HTML 再解析整表 JSON。

## 当前边界

- Arrow 解决传输与初始解析成本；普通图表、Selection 和 Browser Transform 实际消费大表时，仍会按需物化为 JavaScript 行对象，尚未提供列式查询执行器或服务端分页表格。
- Browser Transform Worker 是可信本地代码执行边界，不是第三方 JavaScript 沙箱；它没有 DOM，但可以消耗当前页面允许的浏览器资源。
- HTML 导出的 Arrow/ECharts/Perspective 默认从 CDN 加载 JavaScript；完全离线环境需要把对应 Runtime URL 配为 Workspace 本地资产。
- Python 与 SQL 节点使用独立进程和可选硬超时；当前产品定位是可信单机执行，不设计多租户资源配额。
- Run、Artifact 与缓存按 Workspace Runtime 的数量和时间策略自动保留；`dataviz clean` 可预览或手动清理。
- Workspace 中的 Python、JavaScript 和 Canvas 按可信本地代码执行，不是多租户沙箱。

## DSL 版本与发布

Standalone `workspace.yaml`、`dashboard.yaml`、`presentation.yaml`、Source 和 Transform 文件必须显式带 `schema`，并由 Literal 拒绝未知版本。字段参考直接由安装版本生成：

```bash
dataviz schemas
dataviz schemas dashboard --format json
dataviz schemas source --full --format json
```

修改 Schema 时先添加显式离线 migration，再迁移 Workspace 文件；Runtime 不保留旧、新双协议。完整流程见 [DSL 版本与发布](docs/versioning-and-release.md)，使用者可观察变化见 [Changelog](CHANGELOG.md)。

## 验证

```bash
uv run --no-editable pytest -m "not e2e"
uv run --no-editable playwright install chromium firefox webkit
for browser in chromium firefox webkit; do
  DATAVIZ_BROWSER="$browser" uv run --no-editable pytest tests/e2e
done
node --check src/dataviz/server/static/canvas-runtime.js
node --check src/dataviz/server/static/declarative-runtime.js
node --check src/dataviz/server/static/runtime-web-component-adapter.js
uv run --no-editable dataviz validate examples/minimal-workspace --format json
uv run --no-editable dataviz validate examples/sales-workspace --format json
uv run --no-editable dataviz validate examples/repeat-workspace --format json
uv run --no-editable dataviz validate examples/legacy-showcase --format json
```

2026-08-23 的 0.1.1 本地基线是：Python 3.11、3.12、3.13、3.14 各 124 项 unit/contract tests；Chromium、Firefox、WebKit 各 9 项真实浏览器 tests。0.1.1 pip ZIP 已在干净 Python 3.12 环境完成安装，并执行 `version`、`docs validation`、`init`、focused `validate` 和交互 HTML 报告 smoke；wheel、sdist 与 ZIP 均确认不包含 `.venv`、`build/`、Workspace `.dataviz` 或 `uv.lock`。持续集成定义见 [quality.yml](.github/workflows/quality.yml)。

长期目标是一套低误导、可扩展且适合 AI 编写的看板 DSL。模板是否节省 Token 将通过真实任务中的首次成功率、输入/输出量、修正轮次和完成时间衡量；当前优先保证功能正确、默认体验稳定和诊断清晰。

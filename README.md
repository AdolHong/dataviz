# Workspace Dataviz

一套 workspace-first 的 Python 数据看板工具：Server 面向人，CLI 面向 AI 和自动化。

## 设计原则：模板优先，代码兜底

Dataviz 的默认开发方式不是让人或 AI 为每个看板重新编写一套前端，而是：

> AI 选择稳定模板、填写数据绑定和业务配置；Runtime 负责数据 DAG、筛选、布局、渲染与导出。

Adapter、Source DAG、Query Parameter、Selection、View、Section、Layout 和 Theme 都应有固定但可调整的模板。普通看板走声明式默认路径，不需要 HTML、CSS 或 JavaScript；有特殊表达需求时，再逐级使用扩展能力：

Dataviz 的核心分析链路是：

```text
Adapter
  ↓
Source
  ↓
Server Transform（可选）
  ↓
Dataset
  ↓
Browser Transform（可选）
  ↓
Named Output
  ↓
View Renderer
  ↓
Presentation
```

这条链路既是产品的职责边界，也是后续重构的目标架构。Adapter 只负责连接与授权；Source 获取原始数据；Server Transform 使用 Python 等服务端能力完成查询时计算；Dataset 是 Server、CLI、导出 HTML 与浏览器 Runtime 之间的稳定数据契约；Browser Transform 使用 JavaScript 对已经加载的数据执行 Selection 响应式计算；Named Output 让一次计算可以产生多个可复用的表、指标、文本或图表模型；View Renderer 只负责把结果渲染为图、表或文本；Presentation 只负责布局与视觉表达。

其中两个 Transform 都是可选的。简单看板可以直接采用 `Adapter → Source → Dataset → View Renderer → Presentation`，只写少量声明式 YAML；复杂看板再按需加入 Server Transform、Browser Transform 和多个 Named Output。复杂度应由业务需求引入，而不是由框架强迫所有看板承担。

必须保持以下边界：

- Query Parameter 驱动 Source 与 Server Transform，并需要重新查询。
- Selection 作用于已经加载的 Dataset，驱动 Browser Transform 和受影响的 View 局部重绘，不得偷偷重新查询。
- Browser Transform 不持有 Adapter 凭证，不直接访问受保护的数据源，也不直接操作 DOM。
- Transform 负责计算，View Renderer 负责表达，Presentation 负责样式；删除 Presentation 不得改变分析结果。
- Server 页面和导出的交互 HTML 必须执行同一套 Browser Transform、Named Output 和 View Renderer 协议。

当前版本已经具备 Adapter、Source DAG、单表 Python Source、Dataset Artifact 和声明式 View Renderer；独立的 Server Transform、Browser Transform、Named Output Contract 与可注册 View Renderer 仍属于后续重构目标。文档中的目标分层不应被误解为这些高级接口已经全部完成。

```text
声明式配置
  → 模板参数
  → Theme token / CSS 变量
  → 单个 View 自定义 renderer
  → 完整 Canvas HTML / CSS / JavaScript
```

看板长期采用“两层文件契约”：必需的 `dashboard.yaml` 只负责 Adapter、Source DAG、参数、Selection、View 数据绑定和最小阅读顺序；可选的 `presentation.yaml` 通过稳定 ID 覆盖布局、容器、Theme 和局部资源。删除呈现层后，看板仍必须能以默认样式查询、选择、展示和导出。完整的职责边界、ID 协议、容错规则、兼容策略与实现状态见 [`docs/product-architecture.md`](docs/product-architecture.md)。

长期目标是把 Dataviz 演进为一套面向人和 AI 的看板 DSL：普通需求用少量声明式配置复用 Runtime，高级需求沿 Presentation、CSS token、局部 Renderer 到完整 Canvas 逐级扩展。Token 优化是长期收益，但当前优先保证正确、好用、模板低误导且诊断清晰；Compact Context 和量化 Token 指标将在产品稳定并积累真实样本后再设计，详见产品架构文档中的“长期目标：面向人和 AI 的看板 DSL”。

> 当前状态：声明式默认 Renderer、独立 `presentation.yaml` 加载与容错合并均已实现；内联 `layout` / `theme` / `canvas` 继续作为兼容写法。命名多套 Presentation 和文档中明确标注的目标 CLI 命令尚未上线。

因此，一个极简看板只需要完成五件事：

1. 把逻辑 Adapter 绑定到 Workspace 中的真实 Adapter。
2. 声明 Source、依赖 DAG 和 Query Parameter。
3. 声明 Selection 与 View 的字段绑定。
4. 声明最简单的 Section 顺序和 View 顺序；默认自上而下铺开。
5. 为 Parameter、Source、Selection、Section 和 View 提供稳定 ID，供依赖、诊断、跳转和 Presentation 覆盖共同使用。

下面是完整可运行的声明式看板；没有 `canvas/`、Widget 文件或前端代码：

```yaml
schema: dataviz/dashboard/v1
id: sales-overview
title: 销售概览
subtitle: 华东大区经营专题
description: 收入、订单与区域结构的交互分析。

adapters:
  warehouse: team-starrocks

query_parameters:
  - {id: start_date, type: date, required: true}
  - {id: end_date, type: date, required: true}

sources:
  - id: sales
    type: sql
    adapter: warehouse
    code: sources/sales.sql
    params: [start_date, end_date]

dashboard_selections:
  - id: region
    field: region
    type: multi_select
    choices:
      - {label: 华东, value: East}
      - {label: 华南, value: South}

views:
  - id: revenue
    title: 销售趋势
    source: sales
    template: line
    x: date
    y: revenue
    series: region
    aggregate: sum

  - id: detail
    title: 销售明细
    source: sales
    template: perspective
    columns: [date, region, revenue]

sections:
  - id: overview
    title: 经营概览
    template: split
    views: [revenue, detail]

layout:
  template: overview

theme:
  preset: plain
  accent: "#2457d6"
  density: compact
```

Runtime 自动完成 Source DAG、执行状态、Query Parameter 表单、Dashboard / Section / View Selection、浏览器端样本选择、Plotly / ECharts / Perspective 渲染、响应式布局、空数据与失败状态，以及 Server 和交互 HTML 导出。

内置 View 模板包括 `metric`、`line`、`bar`、`stacked-bar`、`pie`、`scatter`、`heatmap`、`table`、`perspective`、`markdown` 和 `image`；Section 模板包括 `single`、`stack`、`grid`、`split`、`hero-metrics`、`chart-and-table`、`comparison`、`band`、`small-multiples` 和 `selection-gallery`；Dashboard Layout 包括 `overview`、`monitoring`、`report`、`exploration` 和 `freeform`。模板名称稳定，样式通过 Theme token 调整，因此更适合 AI 生成、审查和复用。

`small-multiples` 和 `selection-gallery` 共用 Repeat Runtime：一个声明式 View 作为蓝图，Runtime 按 `repeat.by` 对同一份 Dataset 分组并创建动态 View 实例。前者展示全部分组，后者使用 Section Selection 只展示搜索或级联选中的分组；默认通过 `IntersectionObserver` 懒渲染，100 个分组不会产生 100 次 Source 查询。完整示例位于 `examples/repeat-workspace`，CLI 手册可运行 `dataviz docs repeated-views`。

## 当前能力

- File、SQL、Python 三类数据源
- DuckDB、MySQL、StarRocks、SQLAlchemy 与本地文件 Adapter
- 基于依赖图的 Source 查询
- Source 节点级状态、错误、缓存与 Artifact
- Plotly 动态图
- ECharts 动态图
- 浏览器端表格、筛选、聚合和派生字段
- Perspective 交互分析表：排序、过滤、分组、透视与图表切换
- CLI 查询、执行和 HTML 报告
- 人用 Server：参数交互、状态灯、画布预览、HTML 下载
- 默认画布风格
- 每个 dashboard 独立 HTML/CSS/JS 画布
- Query Parameter 与 Dashboard / Section / View 三级 Selection

## 安装与运行

### 从发布 ZIP 安装

发布包 `workspace-dataviz-0.1.0.zip` 是 pip 可识别的源码 Distribution，不需要先解压：

```bash
python -m pip install workspace-dataviz-0.1.0.zip

dataviz --help
dataviz docs quickstart
dataviz serve /path/to/workspace --port 8080
```

建议在独立虚拟环境中安装：

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install workspace-dataviz-0.1.0.zip
dataviz docs quickstart
```

也可以安装标准 wheel：

```bash
python -m pip install workspace_dataviz-0.1.0-py3-none-any.whl
```

安装包支持 Python 3.11–3.14，推荐使用 Python 3.12。pip 会安装 DuckDB、FastAPI、Pandas、Plotly、SQLAlchemy 等 Runtime 依赖；Excel 文件支持是可选依赖，可使用 `python -m pip install 'workspace-dataviz[excel]'` 安装已发布版本。尚未发布的未来 Python 版本需要等待 Runtime 依赖完成兼容验证后再扩大范围。

维护者重新生成 ZIP：

```bash
python scripts/build_release_zip.py
```

脚本从 `pyproject.toml` 读取版本并输出到 `dist/`，只打包安装所需源码、README 和 Server 静态资源，不包含 `.venv`、缓存、测试数据或旧构建目录。标准 wheel 和 sdist 仍使用 `uv build` 生成。

### 从源码开发

```bash
uv sync --python 3.12 --extra dev
uv run dataviz validate examples/sales-workspace
uv run dataviz serve examples/sales-workspace
```

打开 `http://127.0.0.1:8080`。

## CLI

```bash
# 新环境或新 AI 首先读取内置开发手册
uv run dataviz docs quickstart
uv run dataviz docs workflow

# 查看所有主题，或搜索内置文档
uv run dataviz docs
uv run dataviz docs --search Perspective
uv run dataviz docs charts --format json

# 查看 workspace
uv run dataviz list examples/sales-workspace

# 给 AI 输出上下文
uv run dataviz context examples/sales-workspace sales --format json

# 查看 AI 可以直接选择的稳定模板及字段要求
uv run dataviz templates

# 浏览可复用 Component，或查看单个 Component 的逻辑、展示、DOM、Token 和示例
uv run dataviz components
uv run dataviz components selector.cascader
uv run dataviz components selector.cascader --format json

# 单独查 File / SQL / Python source
uv run dataviz query examples/sales-workspace sales --source orders --format json
uv run dataviz query examples/sales-workspace sales --source targets --param target_factor=1.1
uv run dataviz query examples/sales-workspace sales --source forecast

# 查询 dashboard 的全部 Source
uv run dataviz run examples/sales-workspace sales

# 直接生成 HTML 报告
uv run dataviz report examples/sales-workspace sales \
  --output examples/sales-workspace/dist/sales.html
```

`dataviz init <folder>` 生成的也是声明式示例：只有 Workspace、`dashboard.yaml` 和示例 CSV，不再脚手架出 Widget JavaScript 或 Canvas 文件。`dataviz context` 会把 Template Registry、当前 Dashboard、Selection 契约、Source 定义与相关代码一起输出给 AI。

### CLI 内置开发手册

`dataviz docs` 是随 Python 包一起安装的 AI 上手入口，不依赖仓库中的 README。当前主题包括：

- `quickstart`：从发现 Workspace 到导出第一个 HTML 的最短路径；
- `workflow`：Discover → Read → Validate → Query → Render → Present → Interact 的固定顺序；
- `dashboard`、`sources`、`adapters`：文件契约、取数和授权边界；
- `charts`、`tables`：模板字段矩阵、最小可复制配方和渲染前检查；
- `selections`、`presentation`：交互语义与视觉层职责；
- `troubleshooting`：按 Workspace、Source、View、Presentation、Export 分层定位错误。

主题名支持常用别名，例如 `dataviz docs chart` 等价于 `dataviz docs charts`。`--format json` 面向 AI 和自动化工具；`--search` 可跨主题检索。CLI 运行时错误会在 JSON 中附带 `dataviz docs troubleshooting` 与 `dataviz docs workflow`，让新环境中的 AI 获得稳定的下一步，而不是盲目重复修改图表。

推荐 AI 在任何修改前执行：

```bash
dataviz docs quickstart
dataviz list <workspace>
dataviz context <workspace> <dashboard-id> --format json
dataviz validate <workspace>
```

开发图表时，再读取：

```bash
dataviz docs charts --format json
dataviz query <workspace> <dashboard-id> --source <source-id> --format json
```

必须先在 Query Preview 中确认字段名、数据类型和样本行，再调整 View；默认 Renderer 成功导出之前，不应进入 CSS/JS 调试。

## Component Template Registry

通用 Component 不是散落在 Canvas 中的代码片段，而是可发现、可验证的产品契约。每个 Component 条目必须说明：

- `purpose` / `use_when`：解决什么问题，何时选用；
- `logic`：写入 `dashboard.yaml`、会影响分析语义的数据字段；
- `presentation`：写入 `presentation.yaml`、只影响交互与外观的配置；
- `behavior`：键盘、浮层定位、滚动和响应式等 Runtime 行为保证；
- `semantic_dom`：允许 Dashboard CSS 稳定定位的语义类；
- `tokens`：推荐覆盖的设计变量；
- `example`：可以直接交给人或 AI 改写的最小样例。

首批 Registry 包含 `selector.chips`、`selector.dropdown`、`selector.searchable`、`selector.cascader`、`view.echarts-category`、`view.table` 和 `view.perspective`。后续 Date Picker、Tree Select、Range、Tabs 等组件应通过 Registry 注册并实现独立 Renderer，而不是继续向 Dashboard Canvas 填入专用代码。`dataviz templates` 用于机器读取整个模板目录；`dataviz components [name]` 用于终端中的渐进式文档与开发帮助。

最小声明式样例位于 [`examples/minimal-workspace`](examples/minimal-workspace)，可直接运行：

```bash
uv run dataviz serve examples/minimal-workspace --port 8080
uv run dataviz report examples/minimal-workspace sales-overview \
  --output examples/minimal-workspace/dist/sales-overview.html
```

Plotly 和 ECharts 在 HTML 中保留浏览器交互，但不能重新查询数据。

仓库同级的 [`../myworkspace`](../myworkspace) 是完整渲染验收 Workspace：它将 `dashboard2/data/files` 中四个旧看板重建为纯声明式逻辑层 + 可选 Presentation，覆盖 SQL、Python、文件 Adapter、Plotly、ECharts、普通 Table、Perspective、Query Parameter 和三级 Selection。

## Workspace 入口

```text
workspace/
├── workspace.yaml
├── auth/
│   ├── adapters.example.yaml
│   └── adapters.local.yaml
└── dashboards/
    └── sales/
        ├── dashboard.yaml
        ├── presentation.yaml  # 可选；独立呈现覆盖层
        ├── presentations/     # 可选；未来的命名呈现方案
        ├── sources/
        ├── widgets/
        ├── data/
        ├── assets/
        └── canvas/            # 兼容现有完整自定义 Canvas
```

`dashboard.yaml` 是可分享看板的唯一必需文件：没有 `presentation.yaml`、`assets/` 或 `canvas/` 时，Runtime 使用确定的默认布局与样式。Presentation 只能按 Section、View 等稳定 ID 改变呈现，不能改变 Adapter 凭证、查询、聚合口径和 Selection 作用域。当前版本仍允许在 `dashboard.yaml` 内联 `layout`、`theme` 和 `canvas`，并把独立 Presentation 作为更高优先级的稀疏覆盖层。

看板身份分为三层，不能混用：

- **Canvas Name**：来自 Dashboard 文件夹的末级逻辑名称，是侧栏、移动、回收站、复制和分享时看到的名称；不重复写入 YAML。
- **`id`**：程序使用的稳定标识，供 CLI、Source DAG、运行状态和 API 引用；移动目录或修改标题时不变。
- **内容元数据**：`title`、`subtitle`、`description` 只描述页面内容。`title` 可省略，省略时默认 Renderer 和浏览器标题回退到 Canvas Name；修改它们不会重命名文件夹。

最小 Presentation 示例：

```yaml
schema: dataviz/presentation/v1
dashboard: sales-overview

theme:
  preset: business
  accent: "#d5532d"

layout:
  template: overview
  columns: 12
  gap: 18

sections:
  trend:
    template: split
    class: trend-section

views:
  revenue-trend:
    width: 8
    height: 420
    container: chart
    options:
      legend: top
  sales-detail:
    width: 4
    container: table
    class: compact-detail

assets:
  css: [assets/presentation.css]
  js: [assets/presentation.js]
```

ECharts 分类图的图例交互也是 Presentation 契约，而不是 Selection。默认 `legend_interaction: filter`：点击图例隐藏某个 series 时，也移除只属于该 series 的 x 轴分类，避免留下无数据的空刻度。需要 ECharts 原生“仅隐藏 series、保留坐标轴”行为时设为 `visibility`；不希望图例可点击时设为 `none`：

```yaml
views:
  district-bars:
    options:
      legend_interaction: filter  # filter（默认）| visibility | none
```

图例状态只属于单个图表的浏览器交互，不会修改 Dashboard / Section / View Selection，也不会影响兄弟 View。需要多个 View 联动时仍应声明 Selection。

合并优先级为 Runtime 默认值 → 模板默认值 → `dashboard.yaml` 内联呈现字段 → `presentation.yaml` → 局部 CSS/JS。Presentation 引用已经删除的 Section/View、缺少资源或自身 YAML 无效时，`validate` 和 Server 返回 warning，并继续使用剩余有效覆盖或纯逻辑默认页面。`dataviz context` 同时输出 `dashboard_logic`、合并后的 `dashboard`、`presentation` 和 `presentation_diagnostics`，便于 AI 分开修改逻辑与视觉。

真实授权只放在 `adapters.local.yaml` 或环境变量中。旧的 `connections.example.yaml` / `connections.local.yaml` 仍向后兼容。

## 可分享的 Data Adapter

Dashboard 不保存主机、账号或密码。Source 只引用逻辑 Adapter 名，Dashboard 再把逻辑名绑定到当前 Workspace 的真实 Adapter：

```yaml
# dashboards/my-report/dashboard.yaml
adapters:
  warehouse: team-starrocks

# dashboards/my-report/sources/orders.yaml
type: sql
adapter: warehouse
code: orders.sql
```

同事收到整个 Dashboard 文件夹后，通常只需把 `team-starrocks` 改成自己 Workspace 里定义的 Adapter 名。SQL 和画布代码不需要改。

Workspace Adapter 放在 `auth/adapters.example.yaml`（可提交的结构示例）和 `auth/adapters.local.yaml`（本地覆盖、禁止提交）：

```yaml
adapters:
  local-duckdb:
    type: duckdb
    database: data/analytics.duckdb
    options: {read_only: true}

  local-files:
    type: files
    root: shared-data

  team-mysql:
    type: mysql
    host: mysql.internal
    port: 3306
    database: analytics
    username_env: DATAVIZ_MYSQL_USER
    password_env: DATAVIZ_MYSQL_PASSWORD

  team-starrocks:
    type: starrocks
    host: starrocks.internal
    port: 9030
    database: analytics
    username_env: DATAVIZ_STARROCKS_USER
    password_env: DATAVIZ_STARROCKS_PASSWORD
```

MySQL 与 StarRocks 共用 MySQL wire protocol。`files` Adapter 的 `root` 是文件访问边界，Source 不能用 `..` 越出该目录；不声明 Adapter 的 File Source 仍可读取 Dashboard 文件夹内的自带 CSV/Parquet/JSON，适合把数据和看板一起分享。

完整的四看板迁移示例：

```bash
uv run dataviz serve examples/legacy-showcase --port 8080
```

### 目录名就是 Dashboard 导航

Dashboard 的物理目录名直接编码逻辑位置，固定分隔符为 `##`：

```text
dashboards/
├── 销售概览/                      # 根目录；Canvas Name = 销售概览
├── Adol##销售概览/                # Adol / 销售概览
├── Adol##周报##销售概览/          # Adol / 周报 / 销售概览
└── __TRASH__##Adol##销售概览/     # 回收站；原逻辑位置仍是 Adol / 销售概览
```

Server 启动和每次导航操作后都扫描 `dashboards/**/dashboard.yaml` 重建目录树。看板位置不再依赖 `workspace.yaml` 中的重复映射，人和 AI 看文件名即可定位，也可以按前缀选择并打包一个逻辑分组。

- 手工复制目录：刷新后自动出现，无需登记。
- 手工改名：刷新后按新位置出现。
- 手工删除：该 Dashboard 安静消失，不影响其他 Dashboard，也不留下悬空记录。
- 多个副本使用相同 `dashboard.id`：全部展示并标记 `conflict`，Runtime 生成唯一临时运行 ID。
- 单个 Dashboard YAML 损坏：仅该项标记 `invalid`，其他 Dashboard 继续工作。
- `workspace.yaml` 损坏或缺失：仍从磁盘发现 Dashboard，只会失去空目录和自定义排序等辅助信息。

目录末段就是 **Canvas Name**，Server 侧栏必须展示它，而不是 `dashboard.title`。`dashboard.id` 仍是 Source、CLI 和运行状态中的稳定业务身份；`title`、`subtitle`、`description` 是页面内容。三者允许不同，例如目录为 `Adol##销售概览`、`id: sales-overview-v2`、`title: 2026 华东经营复盘`。

`workspace.yaml` 只保存没有 Dashboard 也必须存在的逻辑目录、目录顺序和 Workspace Runtime 配置：

```yaml
folders:
  - {path: Adol, order: 10}
  - {path: Adol/周报, order: 20}
```

旧 `navigation` 可作为一次性空目录信息读取；第一次在 Server 中管理目录后会写成 canonical `folders`，并移除旧 `navigation` / `trash`。

### Server 侧栏目录管理

侧栏空白处或目录/看板上点击右键，可以管理物理命名形成的目录树：

- 空白处：新建根目录
- 目录：新建子目录、重命名、移到回收站
- 看板：移动到根目录或任意目录、移到回收站

移动操作优先使用拖拽：Dashboard 或 Folder 可以直接拖进目标 Folder；拖动时侧栏顶部会出现“放到根目录”投放区。Folder 不能拖入自己或自己的子目录，前端和 Server 都会阻止循环结构。右键移动保留为键盘、触屏和精确选择时的备用方式。

Sidebar 可以从右缘拖拽调整宽度，也可以通过页面 Header 左侧的 Navigation 按钮完全收起。宽度和折叠状态保存在当前浏览器 Tab 的 `sessionStorage` 中：刷新后保持，不与其他 Tab 或用户共享。拖拽范围为 180–480px；分隔条支持方向键微调、Home/End 跳到边界以及双击恢复默认宽度。

标题旁的 `＋` 也可以新建目录。回收站固定在侧栏底部并默认折叠；移入回收站会给有关 Dashboard 目录增加 `__TRASH__##` 前缀，不删除目录内任何文件，恢复时去掉前缀。空目录的回收状态记录为 `folders[].path: __TRASH__/原路径`。

重命名或移动多个 Dashboard 时，Runtime 会先做 Windows/macOS/Linux 通用的大小写冲突预检，再通过隐藏临时目录分两阶段重命名；失败时尽力回滚，避免只移动一半。

目录段不允许包含 `##`、`__TRASH__`、控制字符、`<>:"/\\|?*`、尾随空格/句点，以及 `CON`、`AUX`、`COM1` 等 Windows 保留名。内部 API 的 Folder/Trash ID 是 URL-safe 的不透明值，不应由 Dashboard 代码自行拼接。

## Query Parameter 与 Selection

页面输入严格分为四类：Query Parameter、Dashboard Selection、Section Selection 和 View Selection。`query_parameters` 会进入 File、SQL、Python 数据节点；在 Server 中，编辑它只会形成待查询值，点击 **Run query** 后才创建新数据集。其余三类 Selection 只从已加载的数据集中选择样本并在浏览器重绘 View，不访问数据源，也不执行 Python View：

```yaml
query_parameters:
  - id: target_factor
    type: number
    default: 1.0

dashboard_selections:
  - id: region
    type: multi_select
    default: [North, South, East, West]

sections:
  - id: pulse
    title: 经营脉搏
    selections:
      - id: min_revenue
        type: number
        default: 0
    views:
      - revenue
      - widget: detail
        selections:
          - id: min_orders
            type: number
            default: 0
```

作用范围由所在层级决定：

- `dashboard_selections`：全部 View
- `sections[].selections`：当前 Section 的全部 View
- `sections[].views[].selections`：单个 View

这里刻意区分四个词：`Selector` 是页面控件定义，`Selection` 是用户当前选择值，`Predicate` 是 Runtime 根据 binding 编译出的逐行判断，`Selected rows` 是最终交给 View 的数据。Selection 默认是包含语义：

```yaml
dashboard_selections:
  - id: region
    type: multi_select
    mode: include       # 默认值，可省略
    default: []         # 空选择表示全部
    field: region
```

选择 `East`、`West` 只展示这两个区域。只有明确需要排除语义时才写 `mode: exclude`。旧字段 `dashboard_filters`、`filters`、`filter_bindings`、`canvas.client_filters` 和 CLI `--filter` 仍可读取，但只作为迁移兼容入口；新生成的上下文、API、RunResult 和文档统一输出 Selection 命名。

三级 Selection 默认同时形成浏览器端级联：Dashboard Selection 改变后，Section Selection 的离散选项按上游已选数据收缩；Section 改变后，View Selection 再收缩。Runtime 在一次交互中严格按 Dashboard → Section → View 提交每层的新值，再推导下一层，避免 View 暂时读取已失效的 Section 值。失效的下游值会自动取消，`All` 只选择当前可用值，整个过程不重新查询 Source。某个下游 Selector 只想保持固定选项时，可显式设置 `cascade: false`。Server Canvas 与导出的交互 HTML 使用同一逻辑。

Selector 的业务逻辑仍写在 `dashboard.yaml`，控件外观则可在 `presentation.yaml` 中按 canonical key 选择模板：

```yaml
selectors:
  "dashboard:sales/province":
    template: dropdown
  "section:geography/city":
    template: chips
    show_unavailable: false
  "view:detail/district":
    template: cascader
    search_placeholder: 搜索省 / 市 / 区县…
    level_labels: [省份, 城市, 区县]
    class: district-picker
```

| 模板 | 适用场景 |
| --- | --- |
| `auto` | 默认值；根据单/多选与选项数自动决定 |
| `chips` | 少量多选项，适合直接比较 |
| `dropdown` | 紧凑单选或不需要搜索的选项 |
| `searchable` | 大量单选或多选，支持搜索和滚动 |
| `cascader` | 省 / 市 / 区县、产品分类等关联层级；分栏浏览并搜索完整路径 |

`auto` 当前规则为：声明了 `path_fields` 时使用 `cascader`；否则多选不超过 8 项用 `chips`，超过时用 `searchable`；单选不超过 20 项用 `dropdown`，超过时用 `searchable`。级联后不可用的选项默认隐藏，避免在几十个选项中堆积灰色噪音；需要解释可选域时可设 `show_unavailable: true` 以禁用态显示。`class`/`css_class` 会添加到 Selector 根容器，Dashboard 可用自己的 CSS 调整宽度、颜色和密度，但不改变 Selection 语义。Server 和导出 HTML 使用同一套模板配置。

作用域级联和单个 Selector 内的路径级联是两件事。前者决定 Dashboard、Section、View 之间谁影响谁；后者用 `path_fields` 保留一个选择值的完整父子上下文：

```yaml
# dashboard.yaml：分析语义
sections:
  - id: geography
    views:
      - widget: detail
        selections:
          - id: district
            type: multi_select
            path_fields: [province, city, district]
            default: []

# presentation.yaml：交互外观
selectors:
  "view:detail/district":
    template: cascader
    placeholder: 全部地域
    level_labels: [省份, 城市, 区县]
    path_separator: " / "
```

路径值按完整数组保存，例如 `["广东", "深圳", "南山区"]`；多选值则是路径数组的数组。Runtime 用整条路径判断数据行，因此不同城市下的同名区县不会串联。选项树从该 View 已加载的浏览器数据构建，支持逐级展开、完整路径搜索和跨分支多叶节点选择，不重新查询数据源。Cascader 的当前浏览路径与已选路径彼此独立：在厦门选中若干区县后仍可切换泉州继续选择，不会被自动拉回第一个已选分支。

重绘也按同一份 Selection Contract 隔离：Runtime 比较前后 canonical selection key，只把 `affectedViewIds` 交给 Renderer。Dashboard Selection 更新所有受其约束的 View，Section Selection 只更新该 Section 的相关 View，View Selection 只更新自身；无变化的值不会触发重绘。自定义 `window.datavizClient.render(state, context)` 可以读取 `context.changedSelectionKeys`、`context.affectedViewIds` 和 `context.initial`，遵守相同的局部渲染协议。

一个 View 只能属于一个 Section。Selection 在运行结果中使用 `dashboard:sales/region` 这样的 canonical key，因此两个不同 Section 都可以定义 `region` 而不会意外联动。浏览器 View 获得当前作用域的简化映射：

数值阈值不要依赖 Selection 名称猜测，应在 View 上显式声明 binding。内置 operator 包括 `auto`、`equals`、`in`、`between`、`contains`、`gte`、`lte`、`gt` 和 `lt`：

```yaml
views:
  - id: detail
    source: orders
    template: table
    selections:
      - {id: min_revenue, field: revenue, type: number, default: 0}
    selection_bindings:
      min_revenue: {field: revenue, operator: gte}
```

```js
const selections = state.getViewSelections("revenue");
const rows = state.data.source("orders")
  .where("region", "in", selections.region)
  .where("revenue", ">=", selections.min_revenue);
```

CLI `--selection region=...` 只设置页面打开时的默认选择状态；它不会裁剪嵌入 HTML 的源数据。短名称唯一时可直接使用，存在同名 Selection 时使用完整 canonical key。`dataviz context` 会输出每个 View 的 `effective_selections`，AI 不需要自行推断继承关系。

Server 中只有 **Run query** 会创建后端 run。修改 Dashboard、Section 或 View Selection 时，父页面通过 `postMessage` 把状态交给画布的 `window.datavizClient.render(state)`；run id 和数据集保持不变。重新 Query 期间旧数据集仍可交互，查询成功后再替换。

导出 HTML 时，Query Parameter 作为只读快照写入报告；因为页面已经没有 Python 后端，它不能重新查询。Dashboard、Section 和 View 三层 Selection 仍可继续操作嵌入的数据。Server 导出时当前 Selection 仅成为 HTML 的初始状态，不会裁剪内嵌数据。

交互 HTML 可以把取数后的 Source 表、Selection 契约和浏览器端 View renderer 一起嵌入。这样接收报告的人可以继续切换 Dashboard、Section 和 View Selection，而不需要 Python 或 Server。开启方式：

```yaml
canvas:
  script: canvas/script.js
  client_selections: true
  client_sources: [orders, targets]
  client_libraries: [plotly, echarts, perspective]
```

`script.js` 注册统一入口：

```js
window.datavizClient = {
  render(state) {
    const rows = state.data.source("orders").rows();
    state.renderView("revenue", () => ({
      type: "plotly",
      data: [{x: rows.map(row => row.date), y: rows.map(row => row.revenue)}],
    }));
  }
};
```

`client_sources` 是显式数据白名单：只有列出的 Source 才会进入浏览器和 HTML。开启后必须检查敏感列和报告体积。Python 不执行 View 或画图代码。

### Perspective 分析表

`table` 和 `perspective` 是两种不同模板：

| 模板 | 目的 | 特点 |
| --- | --- | --- |
| `table` | 展示型明细、固定格式报表 | 轻量、随 Theme 变化、CSS 完全可覆盖 |
| `perspective` | 用户自助分析 | 排序、过滤、分组、透视、表达式与图表切换 |

普通 Table 示例：

```yaml
- id: detail
  title: 销售明细
  source: sales
  template: table
  columns: [date, region, revenue, orders]
  limit: 100
  options:
    labels: {date: 日期, region: 区域, revenue: 收入, orders: 订单}
    formats: {revenue: currency, orders: number}
    align: {revenue: right, orders: right}
    striped: true
    compact: false
    show_count: true
    empty_text: 暂无符合条件的数据
```

普通 Table 提供稳定的自定义选择器：`.dv-widget--table`、`.dv-table-meta`、`.dv-table-wrap`、`.dv-table`、`.dv-table-empty`，每个表头和单元格还有 `data-column="字段名"`。Dashboard CSS 可以直接调整列宽、颜色、字体、行高和响应式行为。

Perspective 示例：

```js
state.renderView("detail", () => ({
  type: "perspective",
  rows,
  columns: ["date", "region", "revenue", "orders"],
  config: {
    plugin: "Datagrid",
    group_by: ["region"],
    columns: ["revenue", "orders"],
    aggregates: {revenue: "sum", orders: "sum"},
    settings: false,
  },
}));
```

用户可继续排序、筛选、创建表达式、拖动字段做 `group_by` / `split_by`，以及切换 Datagrid 或图表插件。初始 `config` 可以由 AI 编写，也可以在浏览器中调整后通过 Perspective 的 `save()` 得到，再写回 Dashboard 配置。

Perspective Table 与 Viewer 实例会在 Selection 重绘时保留，只用 `table.replace(rows)` 更新选中的样本，因此用户已经设置的透视结构不会被清空。Runtime 依据 Perspective v5 的 `flush()` 作为首次绘制和增量更新的完成边界，成功或失败都必须结束 `rendering` 状态。Server Canvas 和导出 HTML 使用同一实现。若 Perspective CDN 不可访问，Runtime 会降级为基础 HTML Table，数据仍然可读。

版本由 Workspace 固定，避免 CDN 的 `latest` 漂移：

```yaml
runtime:
  perspective_version: 5.2.0
```

当前集成遵循 Perspective v5 API：Viewer 绑定命名 Table 所在的 Client，插件使用 `viewer-datagrid` 与新版 `viewer-charts`，不再使用旧版 `@finos/*` 和 `viewer-d3fc`。

## AI 开发独立画布

在 `dashboard.yaml` 中声明：

```yaml
canvas:
  template: canvas/template.html
  style: canvas/style.css
  script: canvas/script.js
  use_default_style: true
  client_selections: true
  client_sources: [orders, targets, forecast]
  client_libraries: [plotly, echarts, perspective]
```

### `template.html`

这是 HTML `body` fragment，不需要写 `<html>`、`<head>` 或运行库。Runtime 会自动注入 Plotly.js、ECharts.js、默认 CSS 和 hydration 脚本。

模板使用 Jinja：

```html
<header class="dv-canvas-header">
  <h1>{{ dashboard.title }}</h1>
  <p>{{ dashboard.description }}</p>
</header>

<section class="dv-section dv-section--split" data-section-id="overview">
  <header class="dv-section__header">
    <div>
      <p class="dv-section__eyebrow">Overview</p>
      <h2>经营概览</h2>
    </div>
    {{ section_selections("overview") }}
  </header>
  <div class="dv-section__body">
    <div class="dv-view-slot dv-view-slot--primary dv-view--chart">{{ widget("revenue") }}</div>
    <div class="dv-view-slot dv-view--metric">{{ widget("target") }}</div>
  </div>
</section>
```

可用上下文：

- `workspace`：WorkspaceDefinition
- `dashboard`：DashboardDefinition
- `parameters`：当前执行参数
- `run`：RunResult
- `widget(id)`：生成指定 View 的浏览器渲染容器
- `section_selections(id)`：在对应 Section 位置生成折叠 Selection
- `widgets`：`view_id -> HTML shell` 映射

### Section 与 View 容器约定

自由画布仍应复用少量稳定的语义容器。容器负责布局、标题层级、响应式规则和 Selection 的固定位置；Dashboard 自定义 CSS 负责字体、颜色、边框、留白和视觉叙事。这样不同 Dashboard 可以长得完全不同，但用户总能在相同位置找到 Selection。

Section 模板推荐实现四种常用容器：

| 容器 | 适用场景 | 默认结构 |
| --- | --- | --- |
| `dv-section--stack` | 叙事报告、纵向阅读 | View 单列依次排列 |
| `dv-section--grid` | 同级图表集合 | 响应式多列网格 |
| `dv-section--split` | 主图 + 辅助图 | 主 View 较宽，辅助 View 较窄 |
| `dv-section--band` | KPI、摘要、阶段结论 | 横向紧凑条带，可放多个 Metric View |

Section 使用统一骨架：

```html
<section class="dv-section dv-section--grid" data-section-id="performance">
  <header class="dv-section__header">
    <div class="dv-section__title">
      <p class="dv-section__eyebrow">Performance</p>
      <h2>经营表现</h2>
      <p>可选的 Section 说明。</p>
    </div>
    {{ section_selections("performance") }}
  </header>

  <div class="dv-section__body">
    <div class="dv-view-slot dv-view--chart">{{ widget("revenue") }}</div>
    <div class="dv-view-slot dv-view--chart">{{ widget("orders") }}</div>
  </div>
</section>
```

Section Selection 必须位于 `.dv-section__header` 的末尾：桌面端在标题右侧，窄屏时移动到标题下方。没有 Section Selection 时，保留相同标题结构但不渲染空占位。不要把 Section Selection 放进某个 View，也不要复制一份 Selection DOM。

View 模板推荐实现五种常用容器语义。这些类加在 `.dv-view-slot` 包装层，由 Dashboard 的 `style.css` 定义外观；Runtime 仍只负责内部 `.dv-widget` shell：

| 容器 | 适用内容 | 视觉倾向 |
| --- | --- | --- |
| `dv-view--panel` | 通用图表 | 有标题栏和边界的默认容器 |
| `dv-view--metric` | 单值 KPI、变化率 | 强调数字，弱化边框 |
| `dv-view--chart` | Plotly / ECharts 主图 | 最大化绘图区，保留紧凑标题栏 |
| `dv-view--table` | 明细表、透视表 | 固定表头、内容区滚动 |
| `dv-view--plain` | 文字、注释、自定义 HTML | 无卡片外观，融入画布叙事 |

`widget(id)` 会生成标准 `.dv-widget` View shell，并自动把 View Selection 放在 `.dv-widget-header` 的操作区。模板用 `.dv-view-slot.dv-view--chart` 这样的包装层控制位置和视觉语义；不要手写第二套 View 标题或 View Selection。上述 Section/View 类是模板契约，不是新的 Runtime 配置字段；使用自定义模板时应在该 Dashboard 的 `style.css` 中提供相应样式。

推荐的 View 插槽修饰符：

- `dv-view-slot--primary`：当前 Section 的主要 View，占据更多宽度。
- `dv-view-slot--wide`：跨满当前容器。
- `dv-view-slot--compact`：适合 KPI 或短文本，降低最小高度。

AI 开发 Dashboard 时遵循以下顺序：

1. 先选择一种 Section 容器，再为每个 View 选择一种容器语义。
2. 使用 `section_selections(id)` 和 `widget(id)`，不手写 Selection 控件。
3. 优先调整 CSS 变量和修饰类，不改变 Selection、标题栏和状态区的 DOM 关系。
4. 只有模板无法表达特殊叙事时才创建自定义布局；即便自定义，也保持 Section Selection 在 Section 标题旁、View Selection 在 View 标题旁。
5. Server iframe 与导出 HTML 使用同一份容器结构，不能为两种输出分别维护模板。

这套约定是默认设计系统，不是对创意的限制。`use_default_style: false` 可以完全重写外观，但仍建议保留语义类名和 Selection 放置规则，以保证交互一致性、可访问性和 AI 可维护性。

### `style.css`

样式只作用于当前画布。若 `use_default_style: true`，可以复用以下变量和组件：

```css
var(--dv-ink)
var(--dv-paper)
var(--dv-panel)
var(--dv-line)
var(--dv-accent)
var(--dv-green)

.dv-widget
.dv-widget-header
.dv-widget-body
.dv-chart
.dv-table-wrap
.dv-image
```

设为 `false` 时，AI 可以从空白样式开始设计，但仍建议保留 `.dv-chart` 的明确高度。

### `script.js`

Runtime 完成 Plotly/ECharts hydration 后触发：

```js
window.addEventListener("dataviz:ready", (event) => {
  console.log(event.detail.run_id, event.detail.parameters);
});
```

`window.dataviz` 包含 `run_id`、状态、参数、Selection 契约和白名单数据。导出 HTML 与 Server iframe 使用同一份模板、CSS 和 JS。

## Python Source API

```python
def load(context):
    upstream = context.table("orders")
    region = context.params["region"]
    return upstream[upstream["region"].isin(region)]
```

返回 pandas DataFrame、PyArrow Table 或可转换为 DataFrame 的数据。

## Browser View API

```js
window.datavizClient = {
  render(state) {
    const rows = state.data.source("orders")
      .derive({avg: row => row.revenue / row.orders})
      .groupBy("region")
      .aggregate({revenue: {field: "revenue", op: "sum"}})
      .rows();

    state.renderView("revenue", () => ({
      type: "echarts",
      options: {series: [{type: "bar", data: rows.map(row => row.revenue)}]},
    }));
  },
};
```

`renderView` 支持：

- `plotly`：`data / layout / config`
- `echarts`：`options`
- `table`：普通可定制表格，使用 `rows / columns / limit / options`
- `perspective`：自助分析表，使用 `rows / columns / config`
- `text` 和受信任 workspace 的 `html`

## Browser Tab、Dashboard 与缓存隔离

Server 的状态边界是：

```text
Browser Tab Session
  └── Dashboard
        ├── 当前已提交的 Query Parameter
        ├── 当前数据集 Run
        ├── 正在执行的 Run 与 Source 状态
        └── Dashboard / Section / View Selection
```

- 每个浏览器 Tab 使用独立的随机 Session ID；新 Tab、不同浏览器和不同用户之间不共享最近 Run、参数、Selection 或默认缓存。
- 同一 Tab 内，每个 Dashboard 有独立运行槽位。切换 Dashboard 不会取消其他 Dashboard 的查询；回到原 Dashboard 会恢复它自己的进度、数据集和 Selection。
- 点击 **Run query** 只编排当前 Dashboard 的 Source DAG，不会遍历或触发其他 Dashboard。
- 同一 Tab 刷新页面后，会通过 Session ID 恢复各 Dashboard 的最近 Run。复制 Tab 时通过 `BroadcastChannel` 检测重复 Session，并为新 Tab 重新生成 ID。
- Run、SSE、Canvas、Artifact 和 HTML Export API 都校验 Session；拿到另一个 Tab 的 Run ID 也不能读取其结果。

Source Cache 默认同样是 Tab 隔离的：

```yaml
cache:
  mode: persistent   # none / session / ttl / persistent
  scope: tab         # 默认值；不同 Tab 使用不同缓存命名空间
  ttl_seconds: 3600
```

只有确定结果不包含用户差异、并希望多个 Tab 共用查询缓存时，才显式配置 `scope: workspace`。共享范围只影响不可变 Source Artifact 的复用，不会共享最近 Run、页面参数或 Selection：

```yaml
cache:
  mode: ttl
  scope: workspace
  ttl_seconds: 300
```

## Server API

- `GET /api/workspace`
- `POST /api/dashboards/{dashboard_id}/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/events`（SSE）
- `GET /api/dashboards/{dashboard_id}/canvas`
- `GET /api/dashboards/{dashboard_id}/report`
- `GET /api/runs/{run_id}/artifacts/{artifact_id}`
- `GET /api/session/runs`

`POST .../runs` 的请求体包含 `session_id`、`parameters`（以及可选的 `refresh`）。其余 Run、Canvas、Artifact 和 Report 请求通过 `session_id` Query Parameter 绑定当前 Tab。三层 Selection 不属于查询 API。

## 安全说明

Workspace 中的 Python、SQL、HTML 和 JavaScript 都会被执行。只运行你信任的 workspace。Server 默认只监听 `127.0.0.1`，HTML 报告不会嵌入数据库授权。

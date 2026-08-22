# Dataviz 产品架构与看板文件契约

本文记录 Dataviz 的长期产品边界，供人和 AI 在恢复上下文、设计功能、生成看板及审查代码时共同使用。具体字段仍以 Schema、`dataviz templates` 和运行时校验为准；本文解释这些字段为什么存在，以及不同文件分别应该承担什么职责。

## 产品目标

Runtime 的 Python 支持策略是 **3.11–3.14，推荐 3.12**。最低版本跟随 Pandas、DuckDB、FastAPI、PyArrow、Pydantic 等核心依赖的共同稳定区间；不为已经停止维护的 Python 版本长期冻结旧依赖，也不在依赖尚未验证前提前承诺未来 Python 版本。每次扩大范围都必须通过安装包、CLI、完整测试与示例 Workspace 验证。

Dataviz 是一个 workspace-first 的分析工具：Server 面向人提供交互页面，CLI 面向 AI 和自动化提供查询、检查与 HTML 导出。

普通看板不应要求开发者编写大量前端代码。AI 的主要工作是选择稳定模板、绑定数据和填写业务表达式；Runtime 负责 Source DAG、参数表单、Selection、默认布局、渲染、状态与导出。自定义 HTML、CSS 和 JavaScript 是渐进式扩展能力，不是普通看板的起点。

## 核心分析链路与职责边界

Dataviz 的数据处理、交互计算、渲染和呈现必须遵循同一条分层链路：

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

这条链路是产品的目标架构，不要求每个看板实现全部层级：

- **Adapter**：管理连接能力、授权边界和本地凭证；可分享的 Dashboard 只引用逻辑 Adapter 名称。
- **Source**：从文件、SQL、API 或其他数据入口获取原始数据，接收 Query Parameter，并参与服务端 DAG。
- **Server Transform**：可选的查询时计算层，适合 Python 业务包、多表处理、模型计算、大数据量任务和不能进入浏览器的逻辑。
- **Dataset**：跨 Server、CLI、Artifact、HTML 导出和浏览器 Runtime 的稳定数据契约，不绑定具体图表。
- **Browser Transform**：可选的 Selection 响应式计算层，只处理已经加载且获准暴露给浏览器的数据；适合派生字段、分组、窗口、透视、同比环比、异常标记和复杂图表模型。
- **Named Output**：Transform 的稳定命名结果；一次计算可以输出多个 table、scalar、object、text 或 chart model，并由多个 View 复用。
- **View Renderer**：把 Dataset 或 Named Output 转换为 Plotly、ECharts、Table、Perspective、文本等 UI；不得承担取数授权和隐蔽的业务口径。
- **Presentation**：通过稳定 ID 调整布局、容器、Theme、CSS token 和视觉资源；不得改变数据结果、Selection 语义或计算口径。

最简单的看板走短路径：

```text
Adapter → Source → Dataset → View Renderer → Presentation
```

只有业务确实需要时，才加入 Server Transform、Browser Transform 或多个 Named Output。系统应允许复杂逻辑充分展开，但不能让复杂接口成为普通图表的必经之路。

运行时边界必须稳定：

1. Query Parameter 驱动 Source 和 Server Transform；修改后需要重新查询并生成新的 Dataset。
2. Dashboard、Section 和 View Selection 只作用于已经加载的 Dataset；它们驱动 Browser Transform 和受影响 View 的局部重绘，不触发隐式查询。
3. Browser Transform 不直接访问 Adapter、不读取凭证、不直接操作 DOM；它只接收显式输入并返回可序列化 Named Output。
4. Transform 负责计算，View Renderer 负责表达，Presentation 负责视觉；同一业务逻辑不得散落在三层中形成不同口径。
5. Server Canvas 与导出的交互 HTML 必须复用同一套 Browser Transform、Named Output、Selection Contract 和 View Renderer 协议。
6. 每个层级都通过稳定 ID、依赖关系、输入输出 Contract、状态和诊断关联，便于人和 AI 定位到具体节点。

当前实现已经覆盖 Adapter、Source DAG、单表 Python Source、Dataset Artifact、浏览器 Selection 和内置 View Renderer。独立 Server Transform、Worker 化 Browser Transform、多 Named Output Contract、输入输出 Schema 和可注册 View Renderer 是后续需要逐步落地的目标；在完成之前，文档和 CLI 必须明确区分“当前可用”与“目标接口”。

### 重复 View 与分组阅读

当同一分析结构需要应用到大量实体时，不得复制 Source、View 定义或前端代码。Section 通过一个稳定 View 蓝图和 `repeat.by` 从共享 Dataset 创建动态实例：`small-multiples` 展示全部分组，`selection-gallery` 只展示 Section Selection 搜索或级联选中的分组。动态实例 ID 由基础 View ID 和分组键派生，Presentation 仍只覆盖基础 View；默认懒渲染视口附近实例，并在分组退出 Selection 时释放图表资源。导出 HTML 保留全部可选数据和相同 Repeat Runtime，导出时的 Selection 只是初始状态，而不是截断数据集。

最小看板只需要：

1. 将逻辑 Adapter 绑定到 Workspace 中的真实 Adapter。
2. 声明 Source、Source DAG 和 Query Parameter。
3. 声明 Dashboard / Section / View Selection 与 View 数据绑定。
4. 声明最简单的 Section 顺序和 View 顺序；默认自上而下铺开。
5. 为 Parameter、Source、Selection、Section 和 View 提供稳定 ID。

只有这些逻辑配置时，看板必须已经正确、可读、可查询、可筛选、可在 Server 中打开并可导出为交互 HTML。它可以朴素，但不能残缺。

## 两层看板模型

看板由“必需的语义逻辑层”和“可选的呈现层”组成：

```text
dashboards/sales/
├── dashboard.yaml          # 必需：数据与分析逻辑
├── presentation.yaml       # 可选：当前默认呈现覆盖
├── presentations/          # 可选：未来可命名的多套呈现
│   ├── executive.yaml
│   └── exploration.yaml
├── sources/                # SQL、Python 或随看板分享的数据文件
└── assets/                 # 可选：局部 CSS、JS、图片等呈现资源
```

核心约束是：

> 删除全部 Presentation 与自定义前端资源后，`dashboard.yaml` 仍然必须形成一个完整可用的默认看板。

### `dashboard.yaml`：语义逻辑层

`dashboard.yaml` 回答“分析什么”和“各部分如何关联”，负责：

- Dashboard 的稳定 ID、标题和业务说明。
- 逻辑 Adapter 到 Workspace Adapter 的绑定；不保存账号密码。
- Query Parameter、Source、Source DAG 和查询文件。
- Dashboard / Section / View Selection 的作用域与字段绑定。
- View 的数据源、分析字段、聚合方式和基础 renderer/template。
- Section 与 View 的语义归属和默认顺序。
- 一个无需设计工作的朴素布局。

示例：

```yaml
schema: dataviz/dashboard/v1
id: sales
title: 销售分析

adapters:
  warehouse: team-starrocks

query_parameters:
  - id: start_date
    type: date
  - id: end_date
    type: date

sources:
  - id: sales
    type: sql
    adapter: warehouse
    code: sources/sales.sql
    params: [start_date, end_date]

dashboard_selections:
  - id: region
    source: sales
    field: region
    type: multi_select
    mode: include

views:
  - id: revenue-trend
    title: 销售趋势
    source: sales
    template: line
    x: date
    y: revenue
    series: region
    aggregate: sum

  - id: sales-detail
    title: 销售明细
    source: sales
    template: table

sections:
  - id: overview
    title: 经营概览
    views: [revenue-trend, sales-detail]
```

Selection 是面向用户的包含式选择，不再用 Filter 指代 UI 状态：`Selector` 是控件定义，`Selection` 是当前值，`Predicate` 是 Runtime 内部行判断。默认 `mode: include`，选择哪些值就保留哪些行；空选择表示全部。排除行为必须显式写成 `mode: exclude`。三级作用域仍是 Dashboard → Section → View，canonical key 仍通过作用域和 owner ID 隔离同名选择器。

Dashboard → Section → View 也是默认的选项级联顺序。Runtime 使用已经加载到浏览器的数据集和同一份 Selection Contract 计算下游离散 Selector 的可选域；同一次交互必须按 scope rank 逐层提交状态，完成 Dashboard 后再推导 Section，完成 Section 后再推导 View，不能让下游读取上一轮的中间值。上游变化会禁用并取消不再有效的下游值，但不会重新查询 Source，也不会反向改写上游。`All` 表示当前上游约束下的全部可用值。特殊场景可在下游 Selection 上声明 `cascade: false` 保持静态 choices。

Selector 的展示属于 Presentation，不属于逻辑层。`presentation.yaml` 通过 canonical selection key 配置 `selectors` Registry，内置 `auto`、`chips`、`dropdown`、`searchable` 和 `cascader` 五种模板。`auto` 对少量多选使用 chips，对大量选项自动使用可搜索下拉；当逻辑层声明 `path_fields` 时自动使用 cascader。级联产生的不可用项默认不显示；`show_unavailable: true` 才以 disabled 状态保留。Presentation 还可提供 `placeholder`、`search_placeholder`、`empty_text`、`level_labels`、`path_separator` 和 `class`/`css_class`，但不得改变 field、mode、scope 或 cascade 语义。Server Runtime 与 Portable HTML Runtime 必须解析同一配置，不得分别实现两套交互规则。

必须区分两类级联：作用域级联是 Dashboard → Section → View 的影响传播；路径级联是一个 Selector 内部的关联维度，例如省 → 市 → 区县。路径的分析语义由 `dashboard.yaml` 的 `path_fields: [province, city, district]` 声明，Selection 值保存完整字段数组；列名、占位符、路径分隔符与 Cascader 外观属于 `presentation.yaml`。Predicate 必须比较整条路径，不能只比较叶节点。路径树由该 View 已加载的数据构建，支持多选与完整路径搜索，并参与相同的局部重绘和 Portable HTML 协议。Cascader 的浏览路径属于瞬时导航状态，不能由第一个已选值持续覆盖；它必须允许用户在保留既有选择时进入其他父分支继续多选。

Selection 作用域同时是浏览器端重绘边界。Runtime 必须对比前后 canonical selection key，并从 Contract 推导 `affectedViewIds`：View Selection 不得重建兄弟 View，Section Selection 不得重建其他 Section，值没有变化时不得重绘。默认 Renderer 接收局部 View 集合；自定义 Canvas 的 `datavizClient.render(state, context)` 也应读取 `context.changedSelectionKeys`、`context.affectedViewIds` 与 `context.initial`。加载状态只能标记真正受影响的 View，禁止用 Canvas 根节点透明度制造全局闪烁。

旧 Schema 字段 `dashboard_filters`、`filters`、`filter_bindings` 和 `canvas.client_filters` 只作为读取别名保留；Runtime、Server API、CLI context、RunResult 与新文档统一输出 `dashboard_selections`、`selections`、`selection_bindings` 和 `client_selections`。

这里的 `template: line`、字段编码和聚合属于分析语义，应保留在逻辑层。颜色、图例位置、容器外观和具体宽高属于呈现层。Presentation 可以在兼容的前提下替换 renderer，但不能偷偷改变 Source、聚合口径或 Selection 作用域。

### `presentation.yaml`：可选呈现层

`presentation.yaml` 回答“如何展示”，只通过稳定 ID 引用逻辑对象，负责：

- Theme preset、Design token、密度和强调色。
- Dashboard、Section 与 View 的布局模板。
- View 宽高、容器类型、视觉参数和局部 class。
- 可选 CSS、JavaScript、图片等资源。
- 特殊 Canvas 编排，但不拥有查询与业务口径。

文件契约示例：

```yaml
schema: dataviz/presentation/v1
dashboard: sales

theme:
  preset: business
  accent: "#d96032"
  density: comfortable

layout:
  template: overview

sections:
  overview:
    template: chart-and-table
    columns: 12

views:
  revenue-trend:
    width: 8
    height: 420
    container: elevated
    options:
      legend: top
      palette: warm

  sales-detail:
    width: 4
    container: plain
    class: compact-detail

assets:
  css: [assets/dashboard.css]
  js: [assets/dashboard.js]
```

`presentation.yaml` 已由独立 Schema 和 Loader 支持。当前版本的 `dashboard.yaml` 仍允许内联 `layout`、`theme` 和 `canvas`，以保持现有看板可运行；Loader 把这些字段视为较低优先级的内联 Presentation，再应用独立文件中的稀疏覆盖，不要求一次性迁移旧看板。

图表库自身的局部交互必须与 Selection 明确区分。ECharts 分类图通过 Presentation 的 `options.legend_interaction` 声明图例行为：`filter`（默认）在隐藏 series 时同步收缩 category axis，`visibility` 保留 ECharts 原生显隐语义，`none` 禁止图例切换。图例状态不得写回 Selection，也不得触发兄弟 View；需要跨 View 联动必须使用 Dashboard / Section / View Selection。

## 职责边界

| 能力 | 逻辑层 | 呈现层 |
| --- | --- | --- |
| Adapter 逻辑名与绑定 | 是 | 否 |
| Query Parameter | 是 | 否 |
| Source、SQL、Python、文件与 DAG | 是 | 否 |
| Selection 作用域和字段绑定 | 是 | 否 |
| View 数据源、字段与聚合口径 | 是 | 否 |
| 基础 View 类型 | 是 | 可做兼容的视觉覆盖 |
| Section 归属与默认阅读顺序 | 是 | 可重新编排布局 |
| 宽高、网格、留白、颜色、字体 | 默认值 | 是 |
| CSS / JS / 自定义 Canvas | 否 | 是，可选逃生口 |

判断一个字段放在哪里，可以使用一个简单测试：删除 Presentation 后，如果该字段丢失会改变分析结果、业务口径或 Selection 行为，它就必须属于逻辑层；如果只改变阅读和视觉表达，它属于呈现层。

## 稳定 ID 是跨层协议

每个可引用对象都必须有稳定 ID。推荐使用类型限定形式进行诊断、CLI 定位和页面锚点：

```text
parameter:start_date
source:sales
selection:region
section:overview
view:revenue-trend
```

ID 的用途包括：

- Source DAG 和字段绑定。
- Selection 到 Section / View 的作用域绑定。
- Presentation 对布局与样式的覆盖。
- CLI、错误信息、运行状态和 AI 上下文中的精确定位。
- 页面深链接，例如 `#view:revenue-trend`。

ID 是持久身份，不应因为标题、目录名或显示位置变化而改变。同一类型内 ID 必须唯一；不同类型可以同名，但 API 和诊断应携带类型前缀，避免歧义。

### Canvas Name、ID 与内容标题

Dashboard 同时存在三种不同用途的名称：

| 名称 | 来源 | 用途 | 改动影响 |
| --- | --- | --- | --- |
| Canvas Name | Dashboard 目录编码后的末级名称 | 导航、文件管理、复制、打包与分享 | 只改变文件系统位置和侧栏名称 |
| `dashboard.id` | `dashboard.yaml` | CLI、API、DAG、缓存与运行状态的稳定身份 | 属于显式迁移，不随目录改名 |
| `title` / `subtitle` / `description` | `dashboard.yaml` | 页面标题与内容说明 | 只改变阅读内容，不改变目录和程序身份 |

Canvas Name 是文件系统事实，不在 YAML 中复制保存。`title` 可选；缺失或为空时，Runtime 必须以 Canvas Name 作为页面标题和 HTML document title。侧栏、移动确认、回收站与恢复界面始终使用 Canvas Name，即使 `title` 与它不同。API 和 `dataviz list/context` 应同时暴露 Canvas Name 与内容标题，避免 AI 猜测字段含义。

计划中的定位接口应遵循同一协议，例如：

```bash
dataviz inspect sales --id source:sales
dataviz inspect sales --id view:revenue-trend
dataviz render sales --focus view:revenue-trend
```

这些命令是目标接口，不代表当前 CLI 已全部实现。

## 默认渲染规则

没有 Presentation 时，Runtime 应采用确定且无惊喜的默认行为：

1. Section 按 `dashboard.yaml` 中的声明顺序自上而下排列。
2. Section 内 View 按 `views` 引用顺序自上而下排列。
3. 使用默认标题、容器、间距、响应式宽度和可访问的空状态。
4. Selection 使用 Runtime 统一组件，不要求 Dashboard 自己制作控件。
5. 普通 Table 使用可主题化 HTML 表格；Perspective 使用其独立分析组件。
6. Server Canvas 和导出 HTML 使用相同结构及浏览器端 Selection 逻辑。
7. 不加载任何 Dashboard 自定义 CSS 或 JavaScript。

默认样式的价值不是视觉独特，而是让最小配置始终可以生成结构清晰、行为一致的分析页面。

## Component Registry 与扩展边界

Runtime Component 采用 Registry 而不是 Dashboard 内的临时实现。Registry 条目必须包含稳定名称、用途、适用条件、逻辑契约、Presentation 契约、语义 DOM、设计 Token 和可运行示例。AI 先查 Registry 选择组件，再填写业务字段；不应默认生成新的控件 JavaScript。

Component 的解耦规则是：

1. 分析语义位于 `dashboard.yaml`，例如 Cascader 的 `path_fields`。
2. 展示选择位于 `presentation.yaml`，例如 `template: cascader`、层级标题和搜索文案。
3. Runtime Renderer 只依赖通用 Component Contract 和 Selection Contract，不依赖某个 Dashboard ID。
4. Server Canvas 与 Portable HTML 使用同一 Renderer、状态机和语义 DOM。
5. CSS 通过 Component 的语义类和 Token 扩展，不覆盖数据绑定或 Selection 语义。
6. CLI 必须能列出组件并输出单组件完整契约，供人和 AI 在不阅读 Runtime 源码的情况下开发看板。

## 覆盖、合并与容错

呈现层采用 ID 定位和稀疏覆盖，而不是复制整个 Dashboard。推荐优先级从低到高为：

```text
Runtime 默认值
  → View / Section / Layout 模板默认值
  → dashboard.yaml 中的兼容内联呈现字段
  → 选中的 presentation.yaml
  → Design token / CSS 变量
  → Dashboard 局部 CSS / JS
```

合并必须 fail-soft：

- 没有 `presentation.yaml`：直接使用默认 Renderer。
- Presentation 引用不存在的 ID：记录 warning 并忽略该覆盖，不阻止查询和页面打开。
- 新增 View 尚未被 Presentation 编排：放回其逻辑 Section 的默认位置；没有 Section 时进入自动生成的默认 Section。
- 删除或改名 View：遗留覆盖变成 warning，不让整个 Dashboard 失败。
- Presentation 字段缺失：逐级继承模板或 Runtime 默认值。
- 自定义 CSS 失败：保留默认结构和内容。
- 单个自定义 JS renderer 失败：只标记对应 View，不能破坏其他 View 或 Source 结果。
- Presentation 不能覆盖 Adapter、Query Parameter、Source SQL、聚合口径或 Selection 作用域。

Workspace 导航也遵循“文件系统是事实来源”：Dashboard 目录用 `##` 编码逻辑层级，例如 `Adol##周报##sales`；`__TRASH__##` 前缀表示回收状态。`workspace.yaml` 只保留空逻辑目录、顺序与 Runtime 配置。人工移动、复制、改名或删除 Dashboard 文件夹后，Server 直接按磁盘重建树，不应因悬空配置导致整个 Workspace 无法启动。

移动 Dashboard、移动/重命名 Folder、移入回收站和恢复，本质上都是 Dashboard 目录的安全重命名。`dashboard.id` 是业务身份，不承担导航位置；目录末段是用户可见且可重命名的 Canvas Name。目录协议必须跨 Windows、Linux 和 macOS，因此禁止 `##`、`__TRASH__`、平台非法字符、尾随空格/句点和 Windows 保留设备名。空 Folder 无法从 Dashboard 目录推导，才由 `workspace.yaml.folders` 保存。

## 多套 Presentation

逻辑层稳定后，同一个看板可以拥有多种阅读方式，而不复制 Source 和业务定义：

```text
presentations/plain.yaml
presentations/executive.yaml
presentations/exploration.yaml
```

- `plain`：默认、低代码、适合快速检查。
- `executive`：强调 KPI 和叙事，适合管理层报告。
- `exploration`：强调 Selection、普通 Table 和 Perspective，适合分析人员。

目标 CLI 可以按名称选择：

```bash
dataviz serve workspace --presentation executive
dataviz report sales --presentation exploration
```

多套 Presentation 是独立呈现层之后的演进方向，不应阻塞单个 `presentation.yaml` 的第一阶段实现。

## 长期目标：面向人和 AI 的看板 DSL

Dataviz 的长期定位是一套看板 DSL，而不是一个要求 AI 反复生成整页 HTML、CSS 和 JavaScript 的脚手架。DSL 应把已经稳定的工程能力——数据源执行、状态管理、Selection、图表初始化、响应式、空数据、错误处理、Server 与 HTML 导出——沉淀到 Runtime 中；人和 AI 主要表达数据绑定、分析语义和视觉差异。

这条路线的 Token 收益来自两方面：声明式配置减少重复生成前端代码的 output token；可发现的模板、精确诊断和渐进式上下文减少理解框架与反复试错所需的 input token。两者必须一起优化。只减少输出、却要求 AI 每次读取完整 Workspace 和全部模板，不算完成；只压缩输入、却让 AI 为每个看板重写 Runtime，也不是目标。

模板体系长期必须同时满足：

1. **简单好用**：常见图表只有少量必填字段，默认值可以直接形成可交付页面。
2. **低误导性**：一个常见需求尽量只有一条明显正确的表达路径；近义字段、不兼容组合和隐式行为应尽量减少。
3. **低试错**：Schema、字段类型检查和 Runtime 诊断应指出具体 Source、View、字段、可用值及修复建议，而不是只报告渲染失败。
4. **渐进扩展**：默认模板不足时，依次开放模板参数、Presentation、CSS token、局部 class、单 View Renderer 和完整 Canvas。
5. **语义稳定**：高级样式不能悄悄改变查询、聚合、Selection 作用域或数据口径。
6. **可发现、可组合**：模板拥有机器可读契约、最小配方、适用条件、限制和兼容信息，AI 不需要阅读 Runtime 源码才能正确使用。

长期可探索 Compact Context、按 View/Source 截取依赖上下文、最小 Recipe、字段 Schema/Preview 和更精确的 `inspect` 能力。例如，修改单个 View 时只提供该 View、直接依赖的 Source、有效 Selection 和所选模板契约，而不是默认发送完整 Dashboard 与全部 Registry。但这些属于后续优化方向，不是当前阶段的交付前提。

当前优先级仍然是：

```text
正确可用
  → 默认体验稳定
  → 模板覆盖常见需求
  → 诊断减少试错
  → 再优化上下文范围和 Token 成本
```

现阶段不设定固定的 input/output token 指标。真实消耗会随 Dashboard 规模、模型、任务类型、缓存方式和 CLI 协议变化；应在产品稳定、积累真实开发样本后建立基准，再确定可验证的量化目标。Token 数量是后续衡量 DSL 效率的指标之一，不能反过来迫使当前设计牺牲正确性、易用性或扩展空间。

## AI 开发流程

CLI 文档属于 Runtime 的产品能力，而不是仓库附属说明。AI 进入只有已安装 Python 包和一个 Workspace 的新环境时，必须仍能通过 `dataviz docs` 获得完整开发路径。内置文档采用稳定主题和结构化 JSON，至少覆盖 Quickstart、固定工作流、Dashboard、Adapter、Source、Chart、Table、Selection、Presentation 与 Troubleshooting；组件级字段则继续由 `dataviz components` 和 `dataviz templates` 提供。

推荐的机器入口是：

```bash
dataviz docs quickstart
dataviz docs workflow --format json
dataviz list workspace
dataviz context workspace dashboard-id --format json
```

CLI 错误必须携带可执行的下一步帮助入口。图表开发文档必须给出字段矩阵、最小配方、数据类型检查与固定排错顺序，避免 AI 在 Source 尚未正确时反复修改前端。文档、Schema、Component Registry 和 Runtime 行为应在测试中共同演进；新增模板而没有同步 CLI 文档，不视为完整实现。

AI 应分两个阶段开发看板：

### 阶段一：分析逻辑

1. 读取 Workspace Adapter 名称与数据约束。
2. 编写最小 `dashboard.yaml`、Source 和查询文件。
3. 为全部对象分配稳定 ID。
4. 验证 DAG、参数、Selection 和 View 数据绑定。
5. 使用默认 Renderer 验证 Server 与 HTML 导出。

阶段一结束时，看板已经可以交付数据正确性审查。

### 阶段二：呈现优化

1. 读取现有 ID，不重命名逻辑对象。
2. 选择 Dashboard、Section、View 和 Theme 模板。
3. 在 Presentation 中按 ID 调整布局与视觉参数。
4. 只有模板和 token 不足时才添加局部 CSS。
5. 只有稳定组件无法表达需求时才添加局部 JS 或完整 Canvas。
6. 再次验证 Server 与导出 HTML 行为一致。

这种流程使数据逻辑便于 review，也让视觉迭代不会反复修改查询代码。

## 实现状态与演进约束

当前已经具备：

- 声明式 `dashboard.yaml`。
- Adapter、Source DAG、Query Parameter 与三级 Selection。
- 默认 View / Section / Layout / Theme 模板。
- 普通 Table 与 Perspective 两种独立模板。
- Dashboard 内联 `layout`、`theme`、`canvas` 和自定义资源。
- 独立 `presentation.yaml` Schema、Loader、按 ID 合并和结构化 warning。
- 无效 Presentation 回退、失效 ID 忽略和缺失资源忽略。
- `dataviz context` 同时暴露逻辑定义、有效定义和 Presentation。
- Server 与交互 HTML 共用渲染与 Selection 逻辑。

尚需落地：

- CLI `inspect --id`、`render --focus` 和命名 Presentation 选择。
- `presentations/*.yaml` 多套命名方案的选择与继承。
- 更细粒度的 Presentation Schema 版本迁移和兼容 renderer 检查。

实现这些能力时必须保持以下验收条件：

1. 旧 Dashboard 无需迁移即可运行。
2. 删除 Presentation 后，查询、Selection、默认页面和 HTML 导出仍然工作。
3. Presentation 的错误不能阻止 Source DAG 执行。
4. 同一逻辑 Dashboard 套用不同 Presentation 时，数据结果与 Selection 语义不变。
5. AI 可以只读取逻辑层完成数据开发，也可以只读取 ID 契约完成视觉编排。

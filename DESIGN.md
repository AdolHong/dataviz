# Dataviz 设计

> 快速安装和当前可用命令见 [README](README.md)；后续工作见 [plan.md](plan.md)。安装版本真正接受的字段始终以 `dataviz schemas`、`dataviz docs` 和 `dataviz components` 为准。

本文描述 Dataviz 当前已经落地的执行架构与必须长期保持的设计不变量。`0.3.1` 对应的严格契约是 `dataviz/dashboard/v3` 与 `dataviz/runtime/v2`；scoped Controls、Selection-before-Compute、两种 Transform 和三种 Interactive Runtime 已进入实现、CLI、Schema、示例与测试，不是兼容旧实验接口的抽象层。当前实现不保留 Dashboard v2 字段，使用者必须按 v3 重写未迁移的实验看板。

Dataviz 是一个 workspace-first、AI-friendly 的数据看板工具。看板是普通文件，能够被 Git 管理、复制和审查；Server 面向人提供交互页面，CLI 面向 AI 与自动化提供校验、查询和 HTML 导出。

项目长期只用两个维度衡量价值：

1. 模板和组件是否可靠、易懂、可扩展，能减少用户困惑与 AI 试错。
2. AI 开发新看板所需的输入上下文、输出代码和修正轮次是否更少。

第二项必须通过真实任务测量，不预设没有证据的 Token 目标。第一优先级始终是先把工具做得好用。

## 1. 核心执行模型

执行模型由两个阶段组成：查询阶段先确定基础数据，交互阶段只在基础数据之上计算。

```text
查询阶段

Query Parameter → Workspace Adapter → Source → Dataset Transform（可选，Server）
                                                   ↓
                                           Base Named Output
                                                   ↓
                            scoped Controls（Dashboard / Section / View）
                               ├─ kind: selection → 选择数据
                               └─ kind: compute   → 改变计算逻辑
                                                   ↓
                                        Interactive Transform（可选）
                                         ├─ server-python
                                         ├─ browser-python
                                         └─ browser-js
                                                   ↓
                                           Derived Named Output
                                                   ↓
                                      View Renderer → Presentation
```

这是一张 DAG，不要求每层都出现。最简单的看板仍然只有：

```text
Source/main → View → 默认 Presentation
```

### 稳定职责

- **Adapter**：Workspace 本地的数据连接和凭证边界。
- **Source**：从 File、SQL 或可信 Python 入口读取外部数据。
- **Dataset Transform**：查询阶段在 Server 对 Source Output 做清洗、合并、特征加工和基础模型计算。
- **Base Named Output**：一次 Query Run 确定后保持不变的基础结果。
- **Control**：Query 后的统一交互入口；由作用域和 `kind` 同时定义可见范围与数据/计算语义。
- **Interactive Transform**：不重新取数，只根据 Base Output 与显式 Control 输入产生交互结果。
- **Derived Named Output**：Interactive Transform 的标准命名结果。
- **View Renderer**：把 Base/Derived Output 渲染为图、表、指标、文本或自定义组件。
- **Presentation**：按稳定 ID 调整布局、容器、组件与样式，不改变分析语义。

“Dataset”不是额外的隐式对象。表格 Dataset 是一种 Named Output；所有节点必须通过显式 Output 引用连接，Runtime 不暗中猜测数据来源或执行隐藏聚合。

## 2. 两个入口与两种 Control 语义

用户和 AI 只面对两个一级入口：

| 入口 | 声明位置 | 语义 | 修改后发生什么 | HTML 导出 |
| --- | --- | --- | --- | --- |
| Query Parameter | `dashboard.query_parameters` | 决定取什么数据 | 新建 Query Run，重新执行 Source/Dataset Transform | 固定为导出时已提交值 |
| Control | Dashboard/Section/View 的 `controls` | Query 后选择数据或改变计算 | 局部筛选、重绘或重算 Interactive Transform | 保持交互；能力取决于 Runtime/export mode |

Control 不是无类型参数袋。每一项必须显式声明 `kind: selection | compute`；统一入口只消除重复的 authoring/UI 结构，不抹掉两者在 Runtime 中的不同 delta、提交周期和失效语义。

### Query Parameter

- 只在用户执行 **Run query** 后提交。
- 进入 Source/Dataset Transform 的执行上下文和缓存键。
- 修改草稿但没有重新查询时，页面仍展示上一次 Run 的已提交值和结果。

### Selection Control

`kind: selection` 只有 include 语义，不承担任意表单参数职责。三个固定作用域是：

```text
Dashboard Control → 所有绑定 View
Section Control   → 所属 Section 的绑定 View
View Control      → 单个 View
```

一个 View 的有效 Selection Control 由它可见的三个作用域合成，不支持任意 Group、多个归属或隐式同名联动。相同业务含义需要联动时使用同一个上游 Control；不需要联动时使用不同稳定 ID。

Selection 有两种不同的级联：

1. **作用域级联**：上游 Selection Control 改变可用数据域，下游组件立即重算选项并清除失效值。
2. **组件内路径级联**：一个 Selection Control 用 `path_fields` 表达省/市/区、组织/团队等完整路径，由 Cascader 或 Tree Select 展示父级上下文。

Canonical state 中空值表示没有 include 约束。交互上的“全选”显式选中当前可用项，从而允许继续反选或取消少量项；上游域变化后再做确定性 reconciliation。

Select 型 Selection 的“选项域”和“被筛选 View 数据”是两个不同契约：

- 静态枚举直接写 `choices`。
- 动态枚举默认沿消费 View 的输入向上穿过 Interactive DAG，追溯到不可变 Base Named Output。
- 多输入或需要消除歧义时，使用 `options_from: source:<id>/<name>` 或 `dataset:<id>/<name>` 显式指定。
- `options_from` 只允许表格 Base Output，不允许 Interactive Output。后者可能依赖当前 Selection，会形成 `options → Selection → Interactive Transform → options` 的启动环。

Runtime 的首次启动顺序固定为：

```text
hydrate Base Output → reconcile Selection option domains
→ commit canonical Controls → render Base Views → start reachable Interactive branches
```

因此一个无关或直接消费 Base Output 的 View 不会再因为另一个必填动态 Selector 尚未生成 DOM option 而停在 `Waiting for dataset`。渐进 Query 尚未发布 option domain 时保留已验证 canonical 值；Base Output 到达后再做确定性 reconciliation。

`canvas-ready` 是完成上述初始化后的生命周期事件，不是脚本加载通知。Server Shell 只有收到当前 dashboard/run/frame identity 的 ready 后，才把该 tab 记忆的 Control state 回灌 Canvas；Canvas 在初始化窗口内捕获到的用户输入先进入 canonical state，因此不会被迟到的默认值覆盖。

对 Interactive Transform，Selection 不是一个需要业务代码自行解释的普通参数。Transform 通过 `selection_inputs` 声明依赖后，Runtime 必须在进入三种 Interactive Runtime 前，对每个具有相应字段契约的表输入应用 include 筛选；不含该字段的无关输入保持不变。因此统一顺序是：

```text
Base/Derived Output → Selection 选择样本 → Compute 逻辑 → Derived Output → Renderer
```

`context.table(name)` / `context.input(name)` / 浏览器的 `context.inputs` 看到的是已选样本；`context.selections` 仍保留局部 alias 与已提交值，供日志、标签或确定性分支使用。Transform 不应再手写同一层数据筛选；若某个值只选择算法/模型而不选择数据，它应声明为 `kind: compute`。

### Compute Control

随机种子、模拟次数、算法、风险系数、优化约束等不筛选数据，统一声明为 `kind: compute` Control。它们与 Selection Control 使用相同的作用域和容器：

```yaml
controls:
  - id: region
    kind: selection
    type: multi_select
    field: region

  - id: seed
    kind: compute
    label: 随机种子
    type: number
    default: 42

  - id: simulations
    kind: compute
    label: 模拟次数
    type: number
    default: 1000000
```

- Compute Control 不进入 Source 或 Dataset Transform。
- Interactive Transform 必须通过 `compute_inputs` 把局部 alias 映射到 canonical Control key。
- Compute Control 可以真实声明在 Dashboard、Section 或 View；作用域决定哪些 View 能依赖它，Presentation 只调整同一作用域控件的呈现。
- 多个 View 共享同一个 Interactive Output 时，不复制参数或计算。

### 草稿、提交与触发

Interactive Transform 支持：

- `trigger: apply`：默认。控件变化先形成草稿，分支标记 stale，用户点击 Apply/Run analysis 后提交。
- `trigger: auto`：提交前 debounce；新状态会取消或 supersede 旧计算。
- `trigger: manual`：只由明确按钮或 CLI/API 调用。

直接 Selection Control 筛选仍即时生效；只有依赖该 Control 的重型 Interactive Transform 可以进入 stale 状态等待 Apply。页面标题、说明和运行证据引用的是产生当前结果的 **已提交值**，不能把未应用的草稿伪装成结果上下文。

## 3. 两种 Transform

阶段和执行位置是两个不同维度：Dataset/Interactive 描述业务生命周期，Server/Browser 描述 Runtime 位置。

### Dataset Transform

- 字段：`dataset_transforms`。
- standalone schema：`dataviz/dataset-transform/v1`。
- 执行位置固定为 Server Python。
- 由 Query Parameter 和上游 Named Output 决定。
- 适合多 Source 合并、数据清洗、特征构造、基础指标和一次 Run 内固定的复杂计算。
- 执行完成后产生 Base Named Output；任何 scoped Control 都不得触发它。

### Interactive Transform

- 字段：`interactive_transforms`。
- standalone schema：`dataviz/interactive-transform/v1`。
- 只消费已经确定的 Base/Derived Named Output。
- 可以显式消费已提交 Query Parameter 快照，以及 selection/compute Control。
- 不访问 Adapter、不重新查询 Source。
- 适合 Monte Carlo、模型推断、运筹优化、情景分析和交互聚合。

DSL 形态：

```yaml
dataset_transforms:
  - id: features
    runtime: server-python
    code: transforms/features.py
    inputs:
      orders: source:orders/main
    query_params: [start_date, end_date]
    outputs:
      main: {kind: table}

interactive_transforms:
  - id: monte-carlo
    runtime: server-python
    code: transforms/monte_carlo.py
    inputs:
      base: dataset:features/main
    query_params: [start_date, end_date]
    compute_inputs:
      seed: dashboard:sales-overview/seed
      simulations: dashboard:sales-overview/simulations
    selection_inputs:
      region: dashboard:sales-overview/region
    trigger: apply
    export: {mode: snapshot}
    outputs:
      summary: {kind: table}
      distribution: {kind: table}
```

DSL 中的值是 canonical Control key，Transform 代码只看到作者显式选择的局部 alias。运行上下文继续把两类 delta 分开，以便调度器准确做局部失效：

```text
context.query_params
context.compute_params
context.selections
context.inputs
```

其中可读取的表输入已经按所声明的 `selection_inputs` 裁剪，之后才执行 `compute_inputs` 驱动的业务计算。浏览器 Runtime 直接从 `context.inputs` 读已选数据；Server Python 分析代码通过 `table()` 或 `input()` 读取，`context.inputs` / `context.artifact(name)` 中的 descriptor 只用于 provenance 与调试。

Interactive Transform 的上下文不提供 Adapter。即使运行在 Server，也不能因为实现位置方便而偷偷重新取数。

## 4. Interactive Runtime

Interactive Transform 有三种 Runtime，但共享同一个输入、Output、状态、错误和生命周期契约。

| Runtime | 主要用途 | Python 包能力 | 独立 HTML 重新计算 |
| --- | --- | --- | --- |
| `server-python` | 原生模型、运筹优化、大规模或专有 Python 计算 | 使用 Workspace Server 环境 | 不支持；只能 snapshot 或 unavailable |
| `browser-python` | 希望保留 Python 逻辑并让导出页继续交互 | Pyodide 支持的纯 Python/WASM 包 | 支持，但需要可用的 Pyodide Runtime 与锁定依赖 |
| `browser-js` | 筛选、聚合、轻量模拟和常规交互计算 | JavaScript/Web API | 支持，默认首选 |

当三种 Runtime 都能清楚、可靠地实现同一逻辑，且输入规模适合浏览器时，默认选择顺序是：

```text
browser-js → browser-python → server-python
```

这个顺序优先考虑启动开销、分发体积、离线交互能力和部署复杂度，不是“JavaScript 在所有算法上一定更快”的性能排名。原生 Python 依赖、大模型、运筹求解器、无法进入 Pyodide 的包或明显超出浏览器内存的数据，应直接使用 `server-python`，不要为了导出能力强行移植。

### server-python

- Server 根据 `run_id + Named Output reference` 读取当前 tab 的 Base Artifact，浏览器不重新上传整份 Dataset。
- Query 计划会显式分类所有被可达 `server-python` 分支消费的 Base Output；分类结果进入 Run 诊断，不能靠 Interactive 运行时临时猜测或重新取数。
- Artifact 的物理位置是 Workspace `.dataviz/runs/<run-id>/artifacts/`，不在 Dashboard 文件夹；逻辑所有权是 `tab session + dashboard + run + canonical output reference`。刷新同一 tab 可恢复，跨 tab 请求必须拒绝。
- 每次计算在独立 Python 进程执行，支持 timeout、cancel、traceback、progress 和结构化运行证据。
- 缓存键至少包含上游 Output content hash、代码/依赖、已提交 Query Parameter 与声明消费的 Control delta。
- 新交互只取消当前 Dashboard 的目标分支，不干扰其他 Dashboard、tab 或用户。

### browser-python

- 当前引擎确定为 Pyodide，但公开语义使用 `runtime: browser-python`，避免把业务 DSL 与某个加载器 API 绑死。
- 必须运行在 module Web Worker，不允许阻塞主线程或直接操作 DOM。
- Python 只负责计算并返回 Named Output；Plotly.js、ECharts、Perspective 和其他 Renderer 仍由 JavaScript 管理。
- 依赖必须显式锁定。纯 Python wheel 和 Pyodide 已构建的 WASM wheel 可以使用；普通原生 CPython wheel 不能假设可用。
- JS/Python 数据交换优先使用 Arrow、TypedArray 或受控结构化数据，避免把大表重复转换为百万个行对象。
- PyProxy、Worker、buffer 和临时 Python namespace 必须在 dispose 时释放。

Pyodide 有两种资产策略：

- `cdn`：报告较小，打开时从 `runtime.pyodide_index_url` 加载；适合有稳定外网或内部镜像的环境。
- `bundle`：从 Workspace 的 `runtime.pyodide_bundle_path` 复制经过 `validate` 检查的本地 Pyodide 分发；适合公司内网和离线分发。

`bundle` 当前导出为一个文件包，而不是把 WASM、标准库和 wheel base64 塞进单个 HTML：CLI 产生 `report.html`、`report.assets/pyodide/` 与 manifest，Server 下载 ZIP。解压后应通过 HTTP 静态服务打开，因为 module Worker/WASM 在 `file://` 下没有可靠的跨浏览器行为。它只打包 Pyodide：Plotly 由 Dataviz 内嵌，ECharts/Arrow 需要显式配置 Workspace 本地文件，Perspective 当前仍是 CDN-only。manifest 的 `portable_without_network` 只覆盖声明的 Runtime/View 资产；任意 Canvas/Presentation 脚本自行发起的请求不在静态证明范围内。

配置目录必须是版本匹配的官方完整分发根目录，至少直接包含 `pyodide.mjs`、`pyodide.asm.mjs`、`pyodide.asm.wasm`、`python_stdlib.zip`、`package.json` 与 `pyodide-lock.json`。`validate` 会核对 `package.json` 版本，在 Pyodide/Emscripten 目标环境中解析 dependency marker，沿 lockfile 检查 `micropip`、声明的 Python 包及其传递依赖 wheel，并要求每个所需文件都有匹配的 SHA-256；因此旧版本、只有 loader 文件或不可验证 wheel 的伪 bundle 都不会通过预检。

Pyodide 是按需能力。只有导出后仍需执行的 `browser-python` 分支才携带 Python Worker、Pyodide URL 或 bundle 资产；没有 `browser-python`，或者该分支已经是 `snapshot/unavailable` 时，不加载也不打包 Pyodide。

参考官方约束：[Web Worker](https://pyodide.org/en/stable/usage/webworker.html)、[加载 Python 包](https://pyodide.org/en/stable/usage/loading-packages.html)、[内置包列表](https://pyodide.org/en/stable/usage/packages-in-pyodide.html)、[中断执行](https://pyodide.org/en/stable/usage/keyboard-interrupts.html)。

### browser-js

- 运行在独立 Web Worker，不能访问 DOM。
- 继续作为开箱即用和导出 HTML 的默认 Interactive Runtime。
- 支持 Promise、timeout、supersede cancellation 和可序列化错误。

## 5. Named Output 与 Export Contract

Source、Dataset Transform 和三种 Interactive Transform 共用同一个 Named Output 协议。Renderer 不关心 Output 来自哪个 Runtime。

每个 Interactive Transform 必须声明导出模式：

```text
interactive  → 导出后仍可根据控件重新计算
snapshot     → 只导出当前已提交状态和结果
unavailable  → 导出页明确展示该分支不可用
```

约束：

- `browser-js`、`browser-python` 可以使用 `interactive`、`snapshot` 或 `unavailable`。
- `server-python` 只能使用 `snapshot` 或 `unavailable`。
- `server-python` 在交互 Server 中可以正常运行，但导出的 HTML 没有 Python Server；这是能力边界，不是导出器可以补齐的脚本。必须在导出时固化结果，或明确显示离线不可用。
- `snapshot` 必须把影响结果的 selection/compute Controls 以只读上下文展示，不能留下能修改但不会重算的假控件。
- `unavailable` 必须显示原因和需要 Server 的能力，不能静默留白。
- `browser-python` 的“支持 HTML”不等于自动得到单文件报告；Pyodide、WASM 和 wheel 必须由明确的 `cdn` 或 `bundle` asset policy 提供。

一次百万次模拟不应该输出一百万个 UI 节点。Transform 应返回汇总、分布、置信区间和必要样本；Renderer 只消费适合展示的 Named Output。

## 6. Workspace 与分享边界

```text
workspace/
├── workspace.yaml
├── auth/
│   ├── adapters.yaml
│   └── adapters.local.yaml
└── dashboards/
    └── 业务分析##门店周报/
        ├── dashboard.yaml
        ├── presentation.yaml       # 可选
        ├── sources/
        ├── transforms/
        ├── data/
        ├── assets/
        └── canvas/                  # 可选的完整逃生口
```

- Dashboard 文件夹末级名称是导航显示名，不存在额外导航别名。
- `##` 前的片段表达逻辑目录；`__TRASH__##` 表示回收站，只改名、不删除文件。
- `dashboard.id` 是 CLI、API、DAG、缓存与状态使用的稳定机器 ID。
- 所有机器 ID 使用同一可移植语法：ASCII 字母或下划线开头，只含字母、数字、点、下划线、连字符，不能以点结尾或使用 Windows 保留设备名。显示语言属于文件夹名、title/label/description；机器 ID 不承担展示职责。
- `title`、`subtitle`、`description` 是页面内容，可以与文件夹名称不同。

`workspace.yaml` 只承担 Workspace 元数据、Runtime 配置、空目录和顺序等无法从 Dashboard 文件夹推导的状态。加载 Workspace 时按磁盘发现 Dashboard；单个损坏 Dashboard 不得拖垮整个 Workspace。

Dashboard 只引用逻辑 Adapter 名称，不保存账号、密码或连接 URL。分享 Dashboard 时，同事只需要绑定自己的 Workspace Adapter。Dataviz 自己不会把 Adapter secret 序列化进浏览器、HTML 或查询证据，并会从错误、日志和 traceback 中脱敏；但可信 Python Source 拿到 Adapter 后仍能主动把任意值作为业务 Output 返回，作者必须避免输出凭据。

Adapter 只有两个权威位置：提交到 Git 的 `auth/adapters.yaml` 保存非敏感定义，本地忽略的 `auth/adapters.local.yaml` 按同名键覆盖凭证。Runtime 不扫描根目录旧文件或 `*.example.yaml`，避免多个隐式来源造成覆盖顺序不确定。

## 7. 逻辑与呈现解耦

`dashboard.yaml` 是必需的逻辑文件，负责：

- 稳定 ID 和业务内容；
- Adapter、Query Parameter 与 scoped Controls；
- Source、Dataset Transform、Interactive Transform 与 Named Output；
- Dashboard、Section、View 的 Selection/Compute Control；
- View 模板、字段编码、聚合与最小阅读顺序。

`presentation.yaml` 是可选的稀疏覆盖，负责：

- Theme、颜色、密度和 design token；
- 语义 Layout、Section/View 容器和 Selector/Control 模板；
- Query 与 Dashboard/Section/View Controls 托盘的模板、宽度、列数与密度；
- 不改变业务语义的 Renderer options/config；
- 局部 CSS/JS 与 Canvas 资源。

删除 Presentation 后，`dashboard.yaml` 必须仍能生成一个朴素、完整、自上而下的看板。推荐扩展顺序是：

```text
声明式默认页面
  → 模板参数
  → Theme token / css_class
  → 单 View 自定义 Renderer
  → 完整 Canvas HTML/CSS/JS
```

默认布局是文档流。`grid`、`split`、`chart-and-table` 等只是语义模板，不是 Mosaic、拖拽坐标或固定画布协议。

Header 只有 `Parameters` 与 `Controls` 两个入口。Controls 在同一托盘里按 DATA（selection）与 LOGIC（compute）分组；默认 `auto` 在单项时堆叠、多项时自适应分栏，最大高度受视口约束并在内部滚动。Dashboard 可在 `presentation.yaml` 的 `controls.query`、`controls.dashboard` 中调整一级托盘，Section/View 可在各自 Presentation 条目的 `controls` 中调整局部托盘。Presentation 不得重写值、kind、校验、级联、tab 隔离或执行事件；Query 在导出 HTML 中只是固定快照，scoped Controls 保持交互。

## 8. 内容绑定

页面内容可以安全引用产生当前结果的已提交状态：

```text
{{ parameters.<id> }}
{{ controls.dashboard.<id> }}
{{ controls.section.<section-id>.<id> }}
{{ controls.view.<view-id>.<id> }}
```

- `parameters` 只在新 Query Run 提交后更新。
- Compute Control 内容只在对应 Interactive Transform 提交后更新。
- Selection Control 在浏览器内即时更新；如果重型分支使用 `trigger: apply`，结果区域必须标记 stale，直到重新计算完成。
- 引用本身就是依赖声明；跨不可见作用域、未知 ID 和任意模板表达式由 `dataviz validate` 拒绝。

## 9. 渐进执行、局部失败与隔离

Query DAG 和 Interactive DAG 都按依赖闭包渐进执行。假设：

```text
source1 + source2 → dataset:features → view1
source3                             → view2
dataset:features + dashboard:sales-overview/seed (kind: compute)
                  → interactive:simulation → view3
```

- `source3` 先完成时，`view2` 先展示，不等待无关分支。
- `simulation` 只在自己的 Base Output 和已提交交互状态就绪后执行。
- Interaction endpoint 归属于 Query Run，而不是 Query 的最终状态；一个 Base Output 发布后，其下游 `server-python` 可以立即计算，不必等待无关 Query 分支完成。
- Interactive 计算不会创建新的 Query Run，也不会修改 Base Named Output。
- 分支失败只影响该分支下游；执行队列的 `queued` 在 View 层映射为 `loading`，Component 统一展示 ready/loading/stale/empty/error/cancelled/unavailable 七种状态。
- 新 Query Run 通过 `run_id` 隔离；同一 Run 内的新交互计算使用独立 generation/interaction id，不能混用旧结果。
- Run 与 Interaction 的内存事件流都有保留上限；截断使用单调 `event_offset`，轮询/SSE 不会把截断后的数组下标误当成全局事件序号。
- 活动 Query 以及仍有活动 Interaction 消费的已完成 Query Run 都受保留策略保护；清理不能在长计算期间移除它们的 Artifact 或缓存。
- Query Run 会持久化所有已发布 Base Output，既用于浏览器传输、报告证据，也用于后续交互。`server-python` 所需引用另有显式分类，但不会复制第二份数据。
- Source/Dataset 节点缓存的逻辑键包含 Dashboard 和节点 ID，tab scope 再由不可逆 session namespace 隔离；`scope: workspace` 只允许显式选择的确定性内容缓存。
- Server Interactive 只能读取所属 Query Run 的 Artifact。即使 Source 很慢、已经不可用或凭证变化，也不得在交互路径回退为重新查询；需要新数据时只能明确创建新的 Query Run。

父页面和 Canvas 通过 `dashboard_id + run_id + frame_id` 握手。Query 最终完成时只同步 endpoint 状态，不重载 Canvas；已经挂载的 View、Control 和 Worker 状态因此不会被整页替换。Selection delta、Compute delta 与 Output 发布都必须显式：某类状态未变化要表达为空集合，不能被解释成“全部变化”。一个无关 Output 在 Interactive Transform 运行期间发布，也不能仅因派生 Output 尚未产生而取消或重启该分支。

浏览器状态以 tab 为边界：

- 同一 tab 可以记住当前 Dashboard 的 Query Parameter，以及 scoped Controls 的草稿/已提交值。
- 不同 tab、浏览器和用户不共享交互状态、Run 或运行证据。
- 一个 Dashboard 的查询或交互计算不会触发、中断另一个 Dashboard。
- `sessionStorage` 与 Browser Runtime 的 `none/session` cache 只允许 tab scope。
- Source、Dataset Transform 和 `server-python` Interactive Transform 默认也按 tab/session 隔离；Source/Dataset 缓存键同时包含 Dashboard 与节点 ID，只有显式的 `ttl/persistent + scope: workspace` 才能按内容哈希跨 tab 复用确定性结果。
- Workspace cache 只复用 Artifact，不共享草稿、Selection、Run、generation、取消信号或运行证据。

## 10. 数据执行与可审查性

每个 Source、Dataset Transform 和 Interactive Transform 都必须有稳定状态、耗时、缓存来源、输入指纹、错误和运行证据。

SQL Source 还要展示：

- 便于人 review 的 Resolved SQL；
- 实际执行的参数化 Driver statement；
- bound parameters、Adapter、SQL 文件、timeout/retry 和 query hash。

Resolved SQL 只用于解释；真实执行始终使用参数化 statement。默认 SQL 单次超时 120 秒，明确超时后立即额外重试一次；SQL Source 可以覆盖 timeout 与 retry。连接、权限和语法错误不盲目重试。

Dataset Transform 与 `server-python` Interactive Transform 都是可信单机 Python，使用独立子进程、timeout、traceback、依赖指纹、结构化日志、多输入和多 Named Output。当前产品不把 Workspace Python 当作不可信多租户沙箱，也不设计 CPU/内存配额。

## 11. View、Section 与 Component

### 默认模板

- View：Metric、Line、Bar、Stacked Bar、Pie、Scatter、Heatmap、Radar、普通 Table、Perspective、Markdown、Image、Custom。
- Section：Single、Stack、Grid、Split、Hero Metrics、Chart and Table、Comparison、Band、Small Multiples、Selection Gallery。
- Selector：Select、Segmented/Radio、Checkbox Group、Date Range、Cascader、Tree Select。
- Compute Control：复用参数型输入组件，但通过 `kind: compute` 保持独立 delta 和 Apply/Run analysis 语义。

普通 Table 和 Perspective 是不同模板：前者便于自定义样式，后者提供排序、筛选、分组和透视。Small Multiples/Selection Gallery 从共享 Named Output 和一个 View 蓝图生成实例，不复制查询或计算。

每个 Component 都有明确 owner Package；Package 是 headless controller、Runtime Adapter、功能 CSS、Story 和测试声明的唯一实现来源。`canvas-runtime.js` 只保留 Runtime Manifest、Named Output Store、Interactive Scheduler、Selection Binding 等共享主机能力，不再实现声明式 View、Repeat Section、Presentation 或 Data Frame/Interactive Adapter。已删除独立的 `declarative-runtime.js`，Runtime 内也不保留同功能副本。

四个核心 owner 的边界是：

| Package | 唯一拥有的行为 |
| --- | --- |
| `data.pipeline` | Frame/Grouped Frame、Named Output 数据 API、Selection-before-Compute 输入边界、三种 Interactive Runtime Adapter |
| `view.declarative` | View descriptor、内置 Renderer、Perspective/Table/Chart 生命周期与 View 状态边界 |
| `section.declarative` | Section 编排、Repeat/Selection Gallery、懒挂载与 Section 聚合状态 |
| `presentation.shell` | Theme/Layout shell 与七状态语义、ARIA 映射 |

Package 内的 `test.yaml` 是机器可读验收声明，不是测试执行器；`dataviz components --check` 验证 Package 元数据、资产和声明，真实行为由 pytest 与浏览器 E2E 执行。当前 Registry 有 13 个 package-owned Package，不存在 bridge implementation。

Gallery 是这些契约的可执行说明，而不是截图目录。Selector、Control、View、Section 各自拥有 ready/loading/stale/empty/error/cancelled/unavailable 七状态矩阵；Select 另外提供真实含 10、100、1,000 个原生 option 的 Story，验证搜索、自动虚拟化、键盘和有界可视 DOM。

公开浏览器边界是版本化 Runtime Manifest、Output Store 和稳定事件。Vanilla JS、Web Component 或未来 React/Vue Adapter 只能消费公开协议，不能依赖 Python Renderer 私有结构或默认 Runtime 内部函数。

自定义 Renderer 使用：

```text
validate → mount → update → dispose
```

Server 页面与导出 HTML 必须使用同一组件实现。

## 12. Server、CLI、HTML 与 AI

- **Server** 面向人：提交 Query Parameter、操作 scoped Controls、运行 Interactive Transform、查看 Source/Transform 证据。
- **CLI** 面向 AI/自动化：validate、query、run、compute、output、report、docs、schemas、components、context、scaffold 和 benchmark。
- **HTML** 是一次 Query Run 的可移植快照：Query Parameter 固定；Browser Interactive Transform 可以继续执行；Server Interactive Transform 只能保留 snapshot 或 unavailable。

AI 的默认工作应该是选择模板、绑定 Output、填写状态依赖和业务表达式，而不是每次生成整页前端代码。安装包必须提供严格 Schema、静态 validate、机器可读 docs/components/context、Scaffold、Gallery、稳定错误码和 authoring 日志。

`validate` 不执行查询或计算；静态通过后，再按 Source、Base Output、Interactive Output、View 的顺序动态验证。框架是否节省 Token 必须通过相同任务与完整 HTML 对照，不能由模板数量自行推断。当前安装包提供五类固定任务、严格的 `authoring-event/v3` 日志和 identity/quality-gated 成对比较。Trial 会固定任务契约与输入 SHA-256；每条验收条件必须记录 human/automation/mixed assessor 和证据，只有两种方案均保持输入完整并通过全部验收时才进入聚合。在积累真实重复 trial 前，不发布节省比例。

## 13. 当前实现边界

当前执行契约：

| 契约 | 版本 |
| --- | --- |
| Dashboard schema | `dataviz/dashboard/v3` |
| Browser Runtime Manifest/Event | `dataviz/runtime/v2` |
| Dataset Transform schema | `dataviz/dataset-transform/v1` |
| Interactive Transform schema | `dataviz/interactive-transform/v1` |
| Component Registry | `3.0.0` |

已经实现：

1. Query Parameter 与 scoped Controls 是两个一级入口；Control 统一作用域结构，同时按 selection/compute delta 保持不同提交周期和失效路径。
2. Query DAG 与 Interactive DAG 分离；Base Output 对一次 Query Run 不可变，Derived Output 由 generation 隔离；快分支可在无关 Query 分支仍运行时进入 Server/Browser Interactive 计算。
3. Dataset Transform 使用 `server-python`；Interactive Transform 支持 `server-python`、`browser-python` 和 `browser-js`。
4. 三种 Interactive Runtime 只接收显式状态和 Named Output，不访问 View DOM；Interactive Runtime 不持有 Adapter。
5. Query 与 Interaction 都支持局部并发、分支失败隔离、timeout、cancel、progress、缓存证据和资源释放。
6. Python 节点支持 `context.log(message, level=..., **fields)`；实时事件和 `dataviz/execution-log/v1` Artifact 保留结构化日志及完整失败 traceback，并可通过 session 隔离 API 与 Sources 证据面板检查。
7. HTML Export 强制声明 `interactive`、`snapshot` 或 `unavailable`；Server Python 不伪造离线交互。
8. `validate`、`compute`、`docs`、`schemas`、`components`、`context` 和 Scaffold 使用同一当前契约。
9. 同一 tab 的状态可恢复，不同 tab、Dashboard、用户、Query Run 与 Interaction generation 相互隔离；父页面/Canvas 消息还校验当前 frame identity。
10. `authoring prepare/verify/assess/start/finish/compare` 可以用固定任务、经过完整性校验的 approach prompt、输入完整性、逐项验收证据、真实客户端 Token、首次成功率、修正轮次和耗时对比 Dataviz 与 standalone HTML；缺失 Token 不做估算。
11. `data.pipeline`、`view.declarative`、`section.declarative`、`presentation.shell` 已从 bridge 完整迁入物理 owner Package；Runtime v2 通过公开 ready event 装配且 dispose 幂等。
12. Gallery 已覆盖四类组件的七状态矩阵，以及真实 10/100/1,000 选项 Select Story；Story 元数据、页面目标与 Chromium 行为测试使用同一 Package。
13. `selection_inputs` 在 Server `ExecutionContext` 和 Browser `data.pipeline` 的公共输入边界先裁剪表数据，三种 Interactive Runtime 都保证 Selection 先于 Compute。
14. 动态 Selection option domain 从 Base Output 建立；首次运行先 hydration/reconciliation，再渲染与调度 Interactive 分支。`canvas-ready` 只在首次 canonical state 提交后发布，Browser Interactive 状态通过 frame identity 约束的事件同步到 Server `Pipeline` 面板。

仍属于后续优化，而不是隐藏的兼容工作：

1. Arrow 已优化传输和浏览器 Interactive Transform 输入；通用 Selection 与部分 Renderer 首次消费大表时仍可能物化 JavaScript 行对象。
2. 内置聚合已经避免把大数组 spread 到 `Math.min/Math.max`，并有 150K 行浏览器回归；固定 10K/100K/1M 内存与耗时证据仍未完成。
3. Server 尚未提供通用服务端分页或按需 Record Batch。这应由真实 benchmark 触发，而不是提前扩张 DSL。
4. authoring 评测工具已实现，但尚未积累足够的重复真实 trial，不能声称固定 Token 节省比例。
5. Firefox/WebKit 仍需扩展窄视口、弹层几何、滚动、键盘、ARIA、Perspective 恢复和重复 dispose 的组合矩阵。
6. 当前协调模型是单进程：`dataviz serve` 启动一个进程，Run、Navigation、Cache 与报告发布锁不提供跨进程互斥；多个进程不得同时写同一 Workspace/输出路径。Runtime 并发上限在启动时捕获，修改配置后需重启。
7. Server 不提供账号体系或 HTTP 鉴权，默认只绑定回环地址；非回环 `--host` 必须显式使用 `--allow-remote`，访问控制由可信网络或外部代理承担。`session_id` 是 tab 状态命名空间，不是身份认证。

Component Registry 独立版本化，只在公共组件契约变化时升级，不跟随 Dashboard schema 机械改号。

## 14. 已明确放弃的旧方向

以下内容不是待恢复功能：

- 不以中心 Server 数据库保存页面和多人编辑状态；Git/文件夹是协作边界。
- 不把网页可视化编辑器作为主要开发路径。
- 不使用 Filter/exclude；Selection 只表达 include。
- 不把 Selection 与 Compute 的 Runtime 语义抹平成无类型参数；统一入口必须保留显式 `kind`。
- 不支持任意 Filter Group 或一个 View 同时归属多个组。
- 不恢复 Mosaic、Widget 坐标或拖拽画布协议。
- 不让 browser-python/Pyodide 直接操作 DOM 或承担 View Renderer；它只产生 Named Output。
- 不把凭证写进 Dashboard，也不让 Dataset/Interactive Transform 获得隐式 Adapter。
- 不为已经移除的实验性字段、Schema 或 Runtime 保留 alias、自动迁移或双协议分支。
- 不要求普通 Dashboard 编写自定义 HTML/CSS/JS；完整 Canvas 只是最后逃生口。

## 15. 演进规则

1. 先固定状态与执行语义，再实现 Runtime，最后扩展 UI 模板。
2. 阶段和执行位置必须正交；不能再以 Server/Browser 命名业务阶段。
3. 新 Runtime 必须输出相同 Named Output，并遵守相同局部失效、错误和 dispose 契约。
4. 新组件由真实 Dashboard 需求触发，不能因为某个 UI 库存在就照单全收。
5. Schema、Runtime protocol、Component Registry 和 Package 独立版本化。
6. 0.x 阶段不为未投入生产的旧设计保留兼容分支。
7. 文档声明必须能由当前 Schema、CLI、Runtime 或测试证明；尚未实现的目标必须明确标记。

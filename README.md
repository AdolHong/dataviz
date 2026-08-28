# Dataviz

Dataviz 是一套 **workspace-first、AI-friendly** 的 Python 看板工具。

它不把分析锁在中心服务或可视化编辑器里。一个 Dashboard 就是一个普通文件夹，可以进入 Git、复制给同事并接受代码审查；数据连接和凭证留在每个人自己的 Workspace 中。

- 人使用 `dataviz serve` 浏览、查询和交互。
- AI 与自动化使用 CLI 校验、查数、计算、调试和导出 HTML。
- 普通看板只写声明式 YAML、SQL/Python/JavaScript 逻辑和简单布局。
- 特殊页面可以逐级覆盖 Theme、Component、Renderer、CSS/JS，完整 Canvas 是最后的逃生口。
- Server 与导出 HTML 默认使用连续白色 Shell；Server Header 横跨屏幕，左侧 Dataviz 品牌按钮负责展开/收起其下方 Sidebar，Query 状态灯紧随品牌。Header、Sidebar、Workbench 和 `business` Canvas 不再各自争夺注意力；靛蓝用于交互与默认分析序列，绿色只用于 Ready/成功状态。
- Server Header 把 Controls 放在 Run 左侧；Query Pipeline 不再是操作按钮，而是 Dataviz 品牌旁的一组取数节点状态灯，悬停显示任务名、点击查看执行证据。每个 View 在类型标签左侧投影自己的依赖链与 Renderer 灯，但仅在 Running/Stale/Error 等需要注意的状态出现；Ready 与 Not run 自动隐藏。
- Server 提供受限的参数编辑入口：右键 Run 编辑 Query Parameter，右键 Dashboard/Section/View Controls 编辑对应作用域。人可以修改默认值、静态候选项和同级顺序；面板内不常驻额外编辑按钮。它只原子写回 `dashboard.yaml`，不允许修改 ID、类型、依赖、数据逻辑、布局或样式；数据推断的候选项保持只读。编辑默认配置不会覆盖当前分析状态，新默认值在下一次初始化该 Dashboard 时生效。导出 HTML 不包含编辑能力。

## 核心模型

```text
Query Parameter → Adapter → Source → Dataset Transform（可选）
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

- Query Parameter 决定取什么数据，提交后创建新的 Query Run。
- Control 是 Query 后唯一的交互入口，并且可以声明在 Dashboard、Section 或 View。
- `kind: selection` 只表达“包含哪些已有样本”，不重新取数。
- `kind: compute` 决定如何计算已选数据，只重算声明依赖它的交互分支。
- Interactive Transform 一旦通过 `selection_inputs` 声明依赖，Runtime 会先对其表输入应用 include Selection，再把已选样本交给 Compute 逻辑；业务代码不应再手写一遍相同筛选。
- 三种 Interactive Runtime 使用相同 Named Output 契约；图、表和文本统一由 JavaScript Renderer 呈现。

每次载入或热更新后的 Dashboard 快照会以并发安全方式只编译一次 `dataviz/dependency-contract/v5`。Query Planner、Server、Browser Runtime、HTML Export 和 AI context 都消费同一个对象；浏览器注册配置只用于检查漂移，Transform 调度、Control 候选域、View 输入和 View 诊断信号仍以契约为准，不会再次猜测拓扑或按 DOM 重建依赖。契约会直接拒绝环、未知 Output、非法跨 Runtime 依赖、越界 Control consumer 和非法 Control 依赖。可以在运行前直接检查：

```bash
dataviz dependencies myworkspace sales-overview
dataviz dependencies myworkspace sales-overview --format json
```

输出会列出 Query Parameter 最终需要重跑的节点、受影响的动态 option Control 和 View，并区分 Control 的结构 scope、直接父节点、传递祖先/后代、直接数据 View、Interactive consumer、派生 View与内容绑定。若表格 Output 没有声明足以保证字段存在的 Schema，直接筛选关系会明确标记为 runtime field check，而不是伪装成静态精确关系。

Selection 使用唯一的 `{intent, values}` 状态：`all_available` 会随候选域扩张，`explicit` 保留用户指定子集，`explicit + []` 明确表示不选择任何样本。普通 Control、Repeat、View 筛选、三种 Interactive Runtime、tab 恢复与导出 HTML 不再各自猜测空数组语义。optional Single Select 可声明 `clearable: true`；required Single 始终恰好一个值。

图表点选或表格行选中通过 View 侧的一条 `control_binding` 写回现有 Selection Control，而不是连接两个 View callback：

```yaml
views:
  - id: store-map
    input: source:stores/main
    template: scatter
    x: lng
    y: lat
    control_binding:
      control: section.selected_store
      field: store_id
```

一个 Selection Control 最多有一个可读写 Bound View；其他 View/Transform 可以任意只读消费。Plotly、ECharts、Table 与 Custom Renderer 使用同一类型化 `select / select_many / clear` 出口，旧 frame/render generation 的事件会被拒绝。

页面结构也只有一个 owner：Section/View 顺序、模板、columns 和 `view.span` 写在 `dashboard.yaml`，Compiler 生成 `dataviz/layout-contract/v1`。默认 Renderer、Server、HTML 和 AI context 消费同一份确定性行列结果。`presentation.yaml` 只保留 Theme、容器外观、组件视觉参数和局部资产；旧 `layout`、Section template/columns 与 View span 会被严格拒绝。

`validate` 会在最终 Layout/Dependency/Renderer 配置上继续做 Semantic Validation，并区分阻塞发布的 error/warning 与非阻塞 advice。`inspect-layout` 输出编译后的 rows、span 和来源；`visual-check` 会真正打开 Server 与导出 HTML，保存截图并检查溢出、遮挡、零高度、弹层裁切和永久 Loading：

```bash
dataviz validate myworkspace --dashboard sales-overview --strict
dataviz inspect-layout myworkspace sales-overview --format json
dataviz visual-check myworkspace sales-overview --target both
```

默认画布还会从 `dataviz/state-snapshot/v1` 自动展示当前已提交 Query、applied Selection 和 committed Compute；未提交 Compute 只显示为“待应用”，不会冒充当前结果。Custom Renderer 绘图优先使用 `context.charts.plotly/echarts`，由平台统一 Theme、页面滚轮、Resize、Update 和 Dispose。

Select 必须显式声明候选域来源：`options.mode: static` 表示由 Dashboard 维护封闭 `choices`，`options.mode: infer` 表示从数据推导。`infer` 不写随维度成员漂移的 `default` 值列表；多选默认跟随全部可用项，需要初始为空时使用 `initial: empty`。动态域不会从依赖当前 Selection 的 Derived Output 反推；Runtime 会追溯不可变 Base Output，复杂或多输入场景可显式写 `options.source: source:<id>/<output>`。`dataviz validate` 会提前拒绝未知、非表格、Interactive Output 或无法提供字段的 option domain。

Selection 候选项之间的联动通过 `depends_on` 显式声明直接父节点。作用域前缀不会填写 owner id：`dashboard.province` 指当前 Dashboard，`section.city` 指当前所在 Section，`view.dow` 指当前 View。每项只写直接父节点；Compiler 计算传递闭包与拓扑顺序，因此 `dates → dow → city → province` 不需要把所有祖先重复写在 `dates` 上：

```yaml
controls:
  - id: dow
    kind: selection
    field: dow
    type: single_select
    options: {mode: infer, source: source:hourly_sales/main}
  - id: dates
    kind: selection
    field: job_date
    type: multiple_select
    depends_on: [view.dow]
    options: {mode: infer, source: source:hourly_sales/main}
```

Dashboard Control 只能依赖 `dashboard.*`；Section Control 可依赖 `dashboard.*` 和本 Section 的 `section.*`；View Control 还可依赖本 View 的 `view.*`。不能跨兄弟 Section/View。`validate` 会在查询前拒绝未知引用、依赖 Compute、越界、环和可静态确认的候选关系字段缺失；Server 与导出 HTML 按同一 `control_order` 原子协调全部候选项，再只渲染真正受影响的 View。

Query Run 的可达 Base Output 会写入 Workspace 的 `.dataviz/runs/<run-id>/artifacts/`，不会写进 Dashboard 文件夹。Runtime 会额外标记被 `server-python` Interactive Transform 消费的 canonical Output；后续交互按 `browser tab session + dashboard + query run + output reference` 读取同一份不可变快照，刷新当前 tab 可以继续使用，其他 tab 或用户不能访问，也不会暗中重新执行 Source。Run 与缓存受 Workspace 保留策略统一清理，因此分享 Dashboard ZIP 不会夹带运行数据。

简单逻辑默认按 `browser-js → browser-python → server-python` 选择：前两者可让导出报告继续交互，后者适合原生 Python 包、大模型、运筹求解和大规模计算。这个顺序强调可移植性和启动成本，不是绝对性能排名。

未显式填写 `trigger` 时，`browser-js`/`browser-python` 默认 `auto`，`server-python` 默认 `apply`。CLI 的 `query`、`output`、`compute` 默认返回紧凑摘要；排错时再加 `--detail debug`，只有确实需要完整执行信封时才使用 `--detail full`。

当前契约是 `dataviz/dashboard/v8`、`dataviz/dependency-contract/v5` 与 `dataviz/runtime/v5`。项目处于 `0.x` 阶段，不兼容更早的实验性 Dashboard/Transform 字段，也不在 Runtime 中保留迁移分支。

## Query Parameter 与日期范围

Query Parameter 在 Dashboard 中只定义一次 canonical 值；每个 SQL、Python Source、Dataset Transform 或 Interactive Transform 再通过 `query_inputs` 映射成自己的本地输入名。这样 RangePicker 可以保持一个 `[start, end]` 值，而 SQL 仍得到两个普通标量：

```yaml
# workspace.yaml
context:
  timezone: Asia/Shanghai

# dashboard.yaml
query_parameters:
  - id: job_date_range
    type: range_input
    value_type: date
    label: 日期范围
    required: true
    default:
      - {mode: relative, anchor: today, offset: -3d}
      - {mode: relative, anchor: today, offset: -1d}

# sources/sales.yaml
schema: dataviz/source/v2
kind: source
id: sales
type: sql
adapter: warehouse
code: sales.sql
query_inputs:
  start_date: {parameter: job_date_range, part: start}
  end_date: {parameter: job_date_range, part: end}
outputs: {main: {kind: table}}
```

```sql
select *
from sales
where job_date between :start_date and :end_date
```

`query_inputs` 的 key 是节点私有 alias，也是 SQL placeholder 或 `context.query_inputs` 的 key。字符串值可简写直接绑定，例如 `warehouse_id: warehouse_id`；`part: start | end` 只允许用于 `range_input/date`。

相对日期只允许用于 Query Parameter 的 `single_input/date` 与 `range_input/date` 默认值。`today` 按 `workspace.context.timezone` 解析；页面首次载入或 CLI Run 创建时会转换为具体 ISO 日期，之后 Run、缓存和 HTML 都保存该具体值。不同浏览器 tab 各自初始化并记忆自己的值，不会在报告打开时重新计算“今天”。

## 快速开始

要求 Python 3.11–3.14，推荐 Python 3.12。

从源码安装：

```bash
git clone https://github.com/AdolHong/dataviz.git
cd dataviz
uv sync --python 3.12 --extra dev --no-editable \
  --reinstall-package ai-dataviz
uv run --no-editable dataviz version
```

创建 Workspace 并启动网页：

```bash
uv run --no-editable dataviz init myworkspace
uv run --no-editable dataviz serve myworkspace --port 8080
```

然后打开 <http://127.0.0.1:8080>。

进入看板后，地址会规范化为 `/dashboards/{dashboard_id}?参数=值`。该链接同时定位 Dashboard 与 Query Parameter 草稿，可以直接复制到新标签页或发给同事；Selection、Compute、Run ID 和凭据不会写入 URL。

Server 不提供账号体系或 HTTP 鉴权，默认只监听本机回环地址。只有已经放在可信网络边界后时，才可显式使用 `--host 0.0.0.0 --allow-remote`；`session_id` 只隔离浏览器 tab 状态，不是访问凭证。

`dataviz serve` 默认监听 Workspace 文件并热更新已经打开的页面。Title、Presentation、CSS 和 View 改动只重载 Canvas；Browser/Server Interactive Transform 改动会基于当前 Base Output 重算；SQL、Source、Dataset Transform、Adapter 或 Query Parameter 改动只把当前结果标记为 `Query outdated`，不会自动执行昂贵查询。连续保存会先防抖并合并为一个 revision，配置无效时保留当前 Canvas 并展示诊断；Workspace Runtime 等进程级配置则明确提示重启。需要人工确认的重载通过 Workspace update 提示执行；`--no-watch` 可关闭主动文件通知。

这个源码流程故意使用 non-editable 安装，避免部分 macOS/Python 组合跳过带 `UF_HIDDEN` 标记的 editable `.pth`。修改 Dataviz 自身的 `src/` 后需要重新执行上面的 `uv sync ... --reinstall-package`；只修改 Workspace/Dashboard 不需要重装。若出现 `ModuleNotFoundError: dataviz`，也执行同一条命令修复入口。

```bash
uv sync --python 3.12 --extra dev --no-editable \
  --reinstall-package ai-dataviz
```

从发行 ZIP 安装时：

```bash
python -m pip install ./ai-dataviz-0.9.1.zip
dataviz version
dataviz serve /path/to/workspace --port 8080
```

## AI / CLI 工作流

每次修改 Dashboard 后，先做不执行查询的静态检查：

```bash
dataviz validate myworkspace --dashboard sales-overview --format json
dataviz dependencies myworkspace sales-overview --format json
```

再按需要查询、检查 Named Output、运行服务端交互计算或导出报告：

```bash
dataviz query myworkspace sales-overview --source sales --format json
dataviz output myworkspace sales-overview source:sales/main
dataviz compute myworkspace sales-overview simulation \
  --run-id run_xxx \
  --compute-param dashboard:sales-overview/seed=42 --format json
dataviz report myworkspace sales-overview --output report.html
dataviz benchmark myworkspace sales-overview --browser-runtime \
  --browser chromium --repeat 3 --query-param row_count=100000 --format json
```

`benchmark --browser-runtime` 可选择 Chromium、Firefox 或 WebKit，重复装载并释放页面，分别报告 Query、HTML 构建、页面就绪、Arrow、Renderer、View 终态和可用内存口径。固定 10K/100K/1M 方法与结果见 [Runtime 性能基线](docs/runtime-performance.md)；它用于规模回归，不代替真实 AI Token 成对评测。

HTML 固定 Query Parameter。`browser-js` 可以直接保留交互；`browser-python` 可使用 Pyodide CDN，或把本地 Pyodide 作为 `HTML + assets` 文件包/ZIP 一起分发。`server-python` 在导出的 HTML 中不能重新运行，只能固化为 snapshot 或明确显示 unavailable。没有活动的 `browser-python` 分支时，报告不会携带或加载 Pyodide。

内网分发 `browser-python` 时，可以把版本匹配的官方完整 Pyodide 分发解压到 Workspace，并让目录直接包含 `pyodide.mjs`、WASM、标准库、`package.json`、lockfile 和所需 wheels：

```yaml
# workspace.yaml
runtime:
  pyodide_bundle_path: runtime/pyodide

# browser-python Interactive Transform
export: {mode: interactive, assets: bundle}
```

`dataviz validate` 会检查核心文件、依赖闭包与 wheel 校验和。导出结果是可压缩分享的 HTML 文件包，不是单个 HTML；解压后应通过 HTTP 静态服务打开。若使用 `assets: cdn`，则无需本地 bundle，但打开报告时必须能访问配置的 Pyodide index URL。

Pyodide bundle 只解决 Python Runtime 资产，不自动打包所有前端库。Plotly 随报告内嵌；ECharts 与 Arrow 只有配置为 Workspace 本地文件时才可离线；Perspective 当前仍依赖 CDN。每次导出的 `*.manifest.json` 会列出已声明 Runtime/View 的网络依赖。自定义 Canvas/JS 自己发起的请求不在静态可移植性判断范围内。

新的 AI 会话应从安装包自带文档开始，而不是读取 Runtime 源码：

```bash
dataviz docs quickstart
dataviz docs pipeline --format json
dataviz docs data-entry-components --format json
dataviz docs design-language --format json
dataviz schemas dashboard --full --format json
dataviz components --format json
dataviz gallery --output component-gallery.html
dataviz context myworkspace sales-overview --focus view:revenue --format json
```

Component Registry 当前包含 21 个 package-owned Package，其中 14 个 `control.*` Data Entry Package 分别对齐 Ant Design 的 Input、InputNumber、AutoComplete、Checkbox、Switch、Radio.Group、Select、Checkbox.Group、Cascader、TreeSelect、DatePicker、RangePicker、Slider 与 Form.List + Input 语义。每个 Package 都有独立 controller、Runtime Adapter、功能 CSS、Story 与测试声明；详见 [Data Entry Component 语义契约](docs/data-entry-components.md)。内置 Gallery 还提供 Control、View、Section 的 `ready / loading / stale / empty / error / cancelled / unavailable` 状态矩阵，以及真实 10、100、1,000 选项的 Select Story。

项目也内置了 Dataviz 与 standalone HTML 的成对 AI 开发评测协议；它只记录客户端提供的真实 Token，不按文本大小估算：

```bash
dataviz authoring tasks --format json
dataviz authoring protocol --format json
dataviz authoring prepare default-dashboard /tmp/trial-dataviz \
  --approach dataviz --trial-id trial-001
dataviz authoring verify /tmp/trial-dataviz --format json
dataviz authoring start myworkspace --trial-dir /tmp/trial-dataviz \
  --model MODEL_NAME --tool CLIENT_NAME
dataviz authoring assess /tmp/trial-dataviz CHECK_ID \
  --status passed --assessor automation --evidence "TEST_OR_REVIEW_EVIDENCE"
dataviz authoring finish myworkspace SESSION_ID --trial-dir /tmp/trial-dataviz \
  --outcome success --first-attempt success --correction-rounds 0 \
  --input-tokens ACTUAL_INPUT --output-tokens ACTUAL_OUTPUT
dataviz authoring compare myworkspace --format json
```

每项固定验收条件必须通过 `authoring assess` 记录 assessor 和证据；只写 `outcome=success` 不能绕过质量门禁。真实试验仍需分别使用新的 AI 会话，并从客户端记录实际 Token。

## Workspace

```text
myworkspace/
├── workspace.yaml
├── auth/
│   ├── adapters.yaml
│   └── adapters.local.yaml
└── dashboards/
    └── 业务分析##销售概览/
        ├── dashboard.yaml
        ├── presentation.yaml       # 可选
        ├── sources/
        ├── transforms/
        ├── data/
        └── assets/
```

Dashboard 文件夹末级名称就是导航显示名；`##` 表达逻辑目录，`__TRASH__##` 表示回收站。回收站显示删除前的完整物理名称；空目录直接删除，Dashboard 只有在回收站右键并再次确认后才会从磁盘永久删除。`dashboard.id` 是 CLI/DAG 使用的稳定机器 ID，使用可跨 Windows/Linux/macOS 的 ASCII 字母、数字、点、下划线和连字符；中文等展示内容放在文件夹名、`title`、`subtitle` 和 `description`。

Header 用一个 split control 合并 Query 操作：主按钮执行 `Run query`，右侧箭头显式展开或收起 Query Parameters。参数区默认展开，是 Header 的内联第二行，会在正常文档流中把 Canvas 向下推；它不是浮层，因此点击其他区域或按 `Esc` 都不会收起。没有 Query Parameter 时自动退化为普通 Run 按钮。`Controls` 负责 Query 后的选择与计算；托盘只展示业务字段标签和组件，不重复显示 DATA/LOGIC、Selection/Compute、作用域或受影响 View 数量。参数多时自动分栏，面板过高时在内部滚动，不会击穿屏幕。各 Dashboard 可在可选的 `presentation.yaml` 中只改视觉编排，而不复制交互逻辑：

```yaml
control_panels:
  query: {columns: 6, column_width: 280, density: compact}
  dashboard: {template: stack}
```

Query Panel 的 `columns` 是 1–6 的最大列数，`column_width` 是每轨目标宽度（160–600 px，默认 280）。Runtime 依据面板自身可用宽度计算实际列数，因此同一份配置会自然降为 1、2、3……列；参数较少时轨道不会用 `1fr` 拉满整行，而是在右侧保留空白，窄屏才降为单列满宽。每个控件默认 `span: 1`，确有需要时可在 `control_components.<key>.span` 显式设为 `2`。Dashboard/Section/View Controls 默认单列；只有明确需要并排时才显式选择 `template: grid` 与 `columns`，暂不把 Query 的自适应密度规则扩散到局部 Controls。值、校验、级联、tab 状态和 Query/Interactive 执行仍由共享 Runtime 管理；导出 HTML 中 Query 变为固定快照，Controls 继续可交互。

`auth/adapters.yaml` 保存可提交的非敏感连接定义，`auth/adapters.local.yaml` 以同名 Adapter 覆盖本地凭证且必须被 Git 忽略。只有这两个位置会被加载，避免根目录旧文件或“示例文件”意外覆盖实际配置。Dashboard 只引用 Workspace Adapter 的逻辑名称，不保存账号密码。内置数据入口包括本地文件、DuckDB、MySQL、StarRocks 和可信 Python Source。

当前 `dataviz serve` 的受支持部署方式是：一个 Workspace 对应一个 Dataviz Server 进程。Server 没有账号体系或 HTTP 鉴权，默认只允许回环地址；远程监听必须显式传入 `--allow-remote`，并由可信网络、反向代理或其他外部边界负责访问控制。Run、Navigation 和持久缓存的协调锁是进程内锁；不要让多个 Server 进程同时写同一个 Workspace 或同一个报告路径。修改 Runtime 并发上限后需重启 Server。

需要生成配置时，先运行 `dataviz scaffold --list --format json` 获取当前安装版本真正支持的 Recipe；Component ID 与 Scaffold Recipe 不是同一套名字。生成或修改后始终运行 `dataviz validate <workspace>`。Custom Renderer 若直接调用 Plotly，必须默认传入 `scrollZoom: false`，避免图表截获 Dashboard 页面滚轮；只有用户明确要求图内滚轮缩放时才设为 `true`。

## 文档

- [设计与架构不变量](DESIGN.md)
- [Dashboard 视觉语言](docs/design-language.md)
- [Data Entry Component 语义契约](docs/data-entry-components.md)
- [当前计划与验收状态](plan.md)
- [代码实现索引](docs/product-architecture.md)
- [版本与发布流程](docs/versioning-and-release.md)
- [AI 开发效率评测协议](docs/authoring-evaluation.md)
- [Runtime 性能基线](docs/runtime-performance.md)
- [变更记录](CHANGELOG.md)

项目尚未添加正式 `LICENSE` 文件；在许可证补齐前，公开可见不等于已经授予再分发或商用权利。

# Dataviz 产品架构与文件契约

更新时间：2026-08-23

本文是 Dataviz 当前产品边界的权威说明。字段细节以严格 Schema、`dataviz docs`、`dataviz templates` 和 `dataviz components` 为准。

## 1. 产品定位

Dataviz 是 workspace-first 的分析工具：Server 面向人提供交互页面，CLI 面向 AI 和自动化提供查询、诊断和 HTML 导出。

普通看板不应该要求大量前端代码。AI 的主要工作是选择模板、绑定数据、填写业务表达式；Runtime 负责执行 DAG、状态、Selection、组件生命周期、默认布局和导出。高级需求再逐级使用 Python Transform、Browser Transform、自定义 Renderer、CSS 或完整 Canvas。

支持 Python 3.11–3.14，推荐 3.12。

## 2. 核心执行链

```text
Adapter ──────────┐
Query Parameter ──┼→ Source
                  │      ↓
                  │  Server Transform（可选）
                  │      ↓
                  └→ OutputBundle / Named Output
                              ↓
Selection ─────────→ Browser Transform（可选）
                              ↓
                         Named Output
                              ↓
                         View Renderer
                              ↓
                         Presentation
```

### Adapter

Workspace 本地连接、凭证和文件访问边界。可分享 Dashboard 只绑定 Adapter 名称，不保存账号密码。

File/SQL Source 由内置 Runner 使用 Adapter；特殊外部系统由可信 Python Source 通过 `context.adapter` 使用。`config` 保存可提交的非敏感配置，`secrets` 把运行时键映射到环境变量。Adapter 不进入 Server Transform、浏览器数据、Artifact 或导出 HTML。

### Source

从外部世界读取数据。支持 File、SQL 和 Python 入口。Source 可以接收 Query Parameter，但不能消费另一个 Source；跨 Dataset 计算属于 Server Transform。Python Source 可绑定一个 Workspace Adapter，通过 `context.adapter` 获得已解析连接信息。

### Server Transform

消费显式上游 Named Output 的 Python 计算节点，适合多表逻辑、模型、复杂 pandas/NumPy 计算和不能暴露到浏览器的数据处理。

### OutputBundle / Named Output

Source、Server Transform 和 Browser Transform 共用的结果协议。一个节点可产生多个稳定名称的 `table`、`scalar`、`object`、`text`、`html`、`chart`、`image` 或 `file`。

### Browser Transform

无 DOM 的纯 JavaScript 计算，运行在独立 Web Worker 中。它只处理已经加载的数据、固定 Query Parameter 和显式 Selection，并产生新的 Named Output，不访问 Adapter、不重新查询。入口可以同步返回，也可以返回 Promise；新状态会取消旧 Worker，`timeout_seconds` 提供硬截止时间。

### View Renderer

把 Named Output 转成 UI。内置 Plotly、ECharts、Table、Perspective、Markdown/Text 和 Image；自定义 Renderer 使用 `validate/mount/update/dispose` 生命周期。

### Presentation

按稳定 ID 调整 Theme、Layout、Section/View 容器、Selector、CSS/JS 和 Canvas。Presentation 不拥有查询、授权、聚合口径或 Selection 作用域。

### 架构不变量

以下约束高于某个具体前端框架或实现版本：

1. View 的 Ready 只依赖它所引用 Output 的传递闭包。一个独立分支完成后必须能够先展示，不能等待整个 Dashboard Run。
2. Node 并发、Output 渐进提交和 View 增量渲染是三个独立层次；只实现线程并发不等于实现渐进式 Dashboard。
3. 默认 Canvas 使用单列文档流。`grid`、`split`、`chart-and-table` 等是可选语义模板，不存在 Mosaic、拖拽坐标或固定画布协议。
4. 自定义 Canvas 可以任意编排 View Host，但不应为换布局而重写 Selection、Cascader、滚动边界或 Renderer 生命周期。
5. Component Package 同时拥有 Schema、默认值、无 DOM 行为、框架 Adapter、功能样式、Gallery Story 和自动测试。
6. Server 只发布 Manifest、Runtime Event 和 Output；前端框架只消费稳定协议。更换 Vanilla JS/React/Vue 不得要求重写 DAG、Output 或 Selection 语义。
7. 产品质量只有两个长期维度：模板功能和交互足够可靠；AI 开发所需上下文、输出与试错轮次足够少。

## 3. 简单路径与复杂路径

最简单的看板只需要：

```text
Adapter → Source/main → View → 默认 Presentation
```

`input: sales` 是 `source:sales/main` 的正式简写。业务确实需要时才加入：

```text
source:orders/main
  → transform:sales-model/trend
  → browser:visible-series/main
  → view:revenue-trend
```

复杂度由业务需求引入，不能成为普通图表的必经之路。

## 4. Parameter 与 Selection

这两类状态必须彻底分离：

| 状态 | 执行位置 | 修改结果 | 生命周期 |
| --- | --- | --- | --- |
| Query Parameter | Server | 重新执行 Source/Server Transform，生成新 Dataset | 当前 Dashboard run |
| Selection | Browser | 筛选现有数据、重算 Browser Transform、局部重绘 | 当前 tab 的当前 Dashboard |

Selection 只有 include 语义；空值表示当前上游约束下的全集。三级作用域是：

```text
Dashboard Selection → 所有绑定 View
Section Selection   → 所属 Section 的绑定 View
View Selection      → 单个 View
```

上游 Selection 更新后，Runtime 逐级重算下游可用域，并清除已经失效的值。View Selection 不得重绘兄弟 View，Section Selection 不得重绘其他 Section，无变化不得重绘。

需要父级上下文的一个 Selector 使用 `path_fields` 表达完整路径，例如省/市/区县；Presentation 选择 `cascader`。作用域级联与路径级联是两个独立概念。

Server 中不同 Dashboard 的查询彼此独立。一个 Dashboard 查询不能中断或触发另一个 Dashboard；不同 tab、浏览器和用户不能共享 Selection 状态。

## 5. Dashboard 与 Presentation

```text
dashboards/sales/
├── dashboard.yaml          # 必需：分析逻辑与最小阅读顺序
├── presentation.yaml       # 可选：按 ID 视觉覆盖
├── sources/
├── transforms/
├── data/
├── assets/
└── canvas/                 # 可选：完整 Canvas 逃生口
```

删除 `presentation.yaml`、assets 和 canvas 后，`dashboard.yaml` 必须仍能形成一个朴素但完整的看板。

### dashboard.yaml 负责

- 稳定 ID、标题与业务说明。
- Adapter 逻辑绑定。
- Query Parameter。
- Source、Server Transform、Browser Transform 与 Named Output 引用。
- Dashboard / Section / View Selection 语义。
- View 模板、字段编码、聚合和最小 Section 顺序。

### presentation.yaml 负责

- Theme、密度、颜色和 token。
- 语义化 Layout、Section/View 容器和视觉密度。
- Selector 模板与文案。
- CSS/JS 资源和 Canvas 模板。
- 不改变数据语义的 Renderer options/config。

Presentation 是稀疏覆盖。不存在的 Section/View/Selection ID 或损坏的 Presentation 给出结构化 warning 并忽略，不阻止逻辑看板运行；逻辑 Schema 错误则直接失败。

推荐扩展顺序：

```text
声明式默认 Renderer
  → 模板参数
  → Theme token / css_class
  → 单 View 自定义 Renderer
  → 完整 Canvas HTML/CSS/JS
```

## 6. 稳定 ID 与名称

Dashboard 同时有三类名称：

| 名称 | 来源 | 用途 |
| --- | --- | --- |
| Canvas Name | 文件夹末级名称 | 导航、移动、复制、打包和分享 |
| `dashboard.id` | dashboard.yaml | CLI、API、DAG、缓存和状态 |
| `title/subtitle/description` | dashboard.yaml | 页面内容 |

Canvas Name 是文件系统事实且不存在额外显示别名；`dashboard.id` 是持久程序身份；内容标题可以自由变化。标题为空时回退到 Canvas Name。

跨层引用使用带类型的稳定形式：

```text
source:sales/main
transform:sales-model/trend
browser:derive/summary
dashboard:sales/region
section:overview/channel
view:detail/product
```

目录和标题变化不应该修改这些业务 ID。

## 7. Workspace 导航

Dashboard 文件系统是导航事实来源，`##` 编码逻辑目录：

```text
sales                         → /sales
Adol##sales                   → /Adol/sales
Adol##周报##sales             → /Adol/周报/sales
__TRASH__##sales              → 回收站/sales
```

移入回收站只是目录重命名，不删除 Dashboard 文件。`workspace.yaml` 只保存空目录、排序、回收元数据和 Runtime 配置。人工复制、移动、改名或删除 Dashboard 后，Server 按磁盘重建树；单个损坏或悬空条目不能让整个 Workspace 崩溃。

目录协议跨 Windows、Linux 和 macOS，因此 UI 禁止 `##`、`__TRASH__`、平台非法字符、尾随空格/句点和 Windows 保留设备名。

## 8. Output Contract

每个执行节点唯一权威结果是 `NodeResult.outputs`。引用格式：

```text
<node-kind>:<node-id>/<output-name>
```

未声明 `outputs` 时只产生 `main`；声明后返回名称必须完全一致。Table 边界可声明：

```yaml
outputs:
  trend:
    kind: table
    schema:
      - {name: date, required: true, nullable: false}
      - {name: revenue, dtype: float64}
```

Schema 在节点边界验证，错误归属当前节点并生成可供 AI 诊断的日志 Artifact。Renderer 不应该隐式猜测另一个输出或执行隐藏业务聚合。

## 9. 服务端节点运行治理

Python Source 与 Server Transform 使用 fresh spawn 子进程：

- `timeout_seconds` 到期硬终止。
- 入口抛错保留远端完整 traceback。
- 失败创建 execution-log Artifact。
- `code_dependencies` 文件或目录参与缓存哈希。
- `python_dependencies` 在 validate 中检查，包版本参与缓存指纹。
- 输入 Artifact、Query Parameter、Runtime/包版本和 Adapter 指纹参与缓存键。
- Python Source 的 Adapter secret 只通过父子进程参数进入内存，不写入运行结果；可信入口代码仍必须避免主动打印或返回 secret。

SQL Source 同样在独立查询进程中执行。每次尝试默认超时 120 秒，默认在明确超时后立即额外重试一次；Source 可用 `timeout_seconds` 和 `timeout_retries` 覆盖，后者表示首次尝试之外的重试次数。每次重试都创建新进程和新连接，不复用可能已经异常的 Session。重试只响应 `query_timeout`；连接、权限、语法和其他执行错误立即失败。`timeout_seconds` 到期后 Runtime 终止查询进程并由操作系统释放连接；MySQL 与 StarRocks 还会设置 Session 级查询超时。数据库主动返回的超时也归一为 `query_timeout`，并与 `query_connection_error`、`query_execution_error` 保持稳定区分，只失败对应 DAG 分支。Runtime 通过 `node_retrying` 事件公开当前尝试次数。

这是可信单机工具，不在当前 DSL 中设计多租户 CPU/内存配额。Workspace Python 不能用来运行不可信脚本。

## 10. Browser Runtime

Server 页面和导出 HTML 使用同一份 `canvas-runtime.js`。每份 Canvas 先发布版本化 `dataviz/runtime/v1` Manifest，其中包含 Component Registry 版本、View/Repeat Descriptor、Selection Contract、Output Store 与 live Run 信息。当前 Vanilla Runtime 是生产 Adapter；零依赖 Web Component 参考 Adapter 已作为第二实现消费同一 Manifest，并且不引用 `window.datavizRuntime` 或 Python Renderer 私有结构。未来 React/Vue 实现也必须遵守这条边界。Runtime 负责：

1. 从可达 server outputs 与延迟传输描述符建立 Browser Output Store。
2. 按依赖拓扑在 Web Worker 中执行可达 Browser Transform。
3. 根据声明的 Selection key 和变更 Output 计算受影响 View。
4. 调用 Renderer Registry 的生命周期。
5. 让单个 Transform/Renderer 失败停留在自己的下游分支。

每次 Browser Transform 使用 fresh Worker。父 Runtime 负责 supersede cancellation、`timeout_seconds`、拓扑顺序和稳定错误对象；Worker 只获得结构化克隆后的 inputs、parameters、selections 与无 DOM Frame helper。错误至少包含 `code/name/message/stack/transform_id/worker`，超时和取消分别使用 `browser_transform_timeout`、`browser_transform_cancelled`。

页面只发布 View、Repeat 和 Canvas 明确可达的服务端 Output，并受 `max_embedded_rows`、`max_embedded_bytes` 限制。小 Table 直接使用 JSON；`browser_table_transport: auto` 在 `arrow_min_rows` 后切换 Arrow IPC：

- Server Canvas 只嵌入 URL/Schema/row_count/content_hash 描述符，Output API 返回 Arrow Stream，并由 HTTP gzip 压缩。
- HTML 导出把 Arrow Stream gzip 后按 `arrow_chunk_bytes` 分成独立 base64 块。
- 浏览器异步获取/拼接、解压和解码后才向 Output Store 发布数据，因此不先在 Python 和 HTML 中创建整表 records JSON。
- generic Selection、图表和 Browser Transform 首次实际读取该 Output 时仍会物化 JavaScript 行对象；Arrow 当前是传输/初始解析协议，不是浏览器列式查询引擎。

Selection Contract 的继承范围与数据字段适用性是两个层次。Dashboard/Section Selection 会进入其作用域内 View 的契约，但 Runtime 只在输入表实际包含绑定字段时应用 include 条件；缺少字段表示该 View 不属于此 Selection 的数据域，不得被误筛为空，也不应触发无意义重绘。异名字段必须通过 View 的 `selection_bindings` 显式映射。

### Server 渐进式运行协议

Server Canvas 先加载只有 View Host 的 Shell。每个服务端节点完成并提交 `NodeResult` 后，Run 发布 `output_ready`；事件只携带 canonical Output Reference 和 Artifact 描述，数据由浏览器按需获取。Browser Output Store 收到 Output 后：

1. 运行刚刚满足依赖的 Browser Transform。
2. 只查找直接或间接受影响的 View。
3. 原子替换这些 View 的 Loading、旧数据或错误状态。
4. 保持其他 View 的 Renderer 实例不变。

新 Run 必须通过 `run_id` 与旧 Run 隔离。页面可以明确保留带 `stale` 标识的旧 View，或者显示 Loading，但不能把不同 Run 的 Output 静默混用。分支失败只影响该分支下游；HTML 导出默认等待终态并生成确定快照。

公开浏览器事件是 `dataviz:ready`、`dataviz:selectionchange` 和 `dataviz:outputschange`。第二 Adapter 通过 Manifest 与这些事件更新，不调用默认 Canvas 的 View Registry。可用 `dataviz frontend-adapters web-component --output adapter.js` 导出参考实现。

## 11. Renderer 与 Component Registry

Renderer 只读 Named Output，不访问 Adapter。Registry 生命周期：

```text
validate → mount → update → dispose
```

组件 Registry 必须描述用途、适用条件、逻辑契约、Presentation 契约、行为、语义 DOM、token 和示例。AI 通过以下命令发现能力：

```bash
dataviz templates
dataviz schemas view --format json
dataviz components --format json
dataviz components --check
dataviz components selector.cascader --format json
dataviz components renderer.custom --format json
```

普通 Table 与 Perspective 是两个独立模板。前者便于 CSS 定制，后者提供排序、筛选、分组和透视。两者的内部滚动只在能消费滚轮时拦截，到边界或内容不足时交还页面。

Perspective Adapter 明确拥有 `create → update/replace → flush → dispose` 生命周期。v5 Runtime 使用命名 Table、`viewer.load(client)` 与 `viewer.restore({table})`；更新复用同一个 Viewer/Table，先 `table.replace()` 再 `viewer.flush()`。释放时必须断开 ResizeObserver，先 `viewer.delete()` 再 `table.delete()`，否则会泄漏 WASM 内存。Runtime 校验配置版本主版本和必要 API，并在不兼容时降级普通 Table。

Registry 不是只读文档字典。每个 Component 都必须由物理 Component Package 拥有；生命周期相同的严格模板可以共享一个实现包。目标上，Package 是以下内容的唯一来源：

- version、status、data shape 与配置 Schema；
- headless controller/state machine；
- Vanilla 或其他框架 Adapter；
- 必需功能样式、可覆盖 token 和稳定 Parts；
- Gallery Story；Loading/Empty/Error/边界数据状态会按 `plan.md` 继续补全；
- 键盘、级联、滚动、响应式和视觉回归的契约用例清单；
- CLI 可复制的最小 recipe。

物理结构固定为：

```text
components/packages/<package>/
├── manifest.yaml
├── controller.js
├── adapter.js
├── style.css
├── story.yaml
└── test.yaml
```

Registry v3 扫描这些包，拒绝缺文件、重复 owner、未知依赖、无 Test 或错误 Story 引用；`gallery.available` 直接由 Story 推导，不再维护第二份手写名单。内置 Gallery 使用真实 Dashboard DSL、Selection Controller 和 Renderer Registry，不能复制一份仅供展示的实现。CLI 把只读 Gallery 复制到临时 Workspace，根据所有 `story.yaml` 生成索引后运行，缓存与 Artifact 不得写入 `site-packages`。`chart-gallery` 一类业务示例不能替代组件 Gallery。

Registry、Package 文档格式、Component 文档格式、浏览器 Runtime 和单个 Package 各自独立版本化。当前 Registry 是 `3.0.0`；代码中的 `dataviz/component-package/v1`、`dataviz/component/v1`、`dataviz/runtime/v1` 和 Package `version: 1.0.0` 不表示 Registry v1。Registry v3 只扫描当前物理 Package，不包含 v1/v2 Package、别名或兼容迁移。

当前物理实现边界是明确的：Overlay、Selector 和 Custom Renderer 已完全从页面脚本抽出；声明式 View/Section、Data Pipeline 和 Presentation Package 仍通过桥接 Adapter 调用 `canvas-runtime.js`、`declarative-runtime.js` 或 Python `CanvasRenderer` 中的既有实现。它们已经有 owner 和稳定契约，但尚不是最终的代码归属。后续搬迁只改变 Package 内部，不改变 Dashboard DSL。

`runtime.overlay` 是 Header、Selection 和 Selector 的共同基础组件。它统一同组互斥、外部点击、Esc/焦点返回、视口安全区、滚动与 resize 重定位。Selector 仍以原生 form control 为 canonical state；`select`、`segmented`、`checkbox-group`、`cascader`、`date-range` 和 `tree-select` 只是可替换 Adapter，因此 Server 与导出 HTML 不会产生两套状态语义。搜索、虚拟滚动和标签折叠属于 `select` 能力，不是额外 Selection 类型。

AI 作者入口：

```bash
dataviz components view.line --format json
dataviz components --check
dataviz scaffold view.line --id revenue
dataviz scaffold renderer.custom --id team.spark --output ./team-spark
dataviz renderer-test ./team-spark/assets/team.spark.js --renderer-id team.spark --contract ./team-spark/assets/team.spark.contract.json
dataviz gallery --output component-gallery.html
dataviz context WORKSPACE DASHBOARD --focus view:revenue --format json
dataviz benchmark WORKSPACE DASHBOARD --format json
dataviz benchmark WORKSPACE DASHBOARD --browser-runtime --format json
dataviz authoring start WORKSPACE --dashboard DASHBOARD --task "<task>"
```

## 12. Repeat Section

大量相同实体不能复制查询或 View 配置。Section 用一个 View 蓝图和 `repeat.by` 从共享 Dataset 创建动态实例：

- `small-multiples` 展示全部分组。
- `selection-gallery` 只展示搜索或级联选择的分组。

Repeat 不复制 Source 或 View 定义。规模控制分成三层：

1. `searchable` 在全部分组元数据上搜索，默认开启。
2. `page_size` 只创建首批卡片 DOM，“Load more”逐批增加；它不截断 Dataset。
3. `render: lazy` 用 IntersectionObserver 只挂载视口缓冲区内 Renderer；`recycle_offscreen` 默认释放离屏图表并在滚回时重建。

Runtime 暴露 `data-repeat-count/filtered-count/rendered-cards/build-ms/reconcile-ms` 与只读 metrics。`dataviz benchmark --browser-runtime` 在真实 Chromium 中记录 Arrow rows、Repeat 总组数/DOM 卡片/挂载峰值、分组和 reconcile 时间、页面 Navigation Timing 与控制台错误。导出 HTML 保留完整 Dataset，初始 Selection 不截断报告能力。

## 13. 强制迁移与严格 Schema

Dataviz 是全新项目，不需要旧 DSL 兼容：

1. 所有 Pydantic 模型 `extra=forbid`。
2. 只使用 View；Widget 目录、字段和 helper 已删除。
3. 只使用 Selection；旧 Filter 字段和 exclude mode 已删除。
4. 只使用 Adapter；connections 文件读取已删除。
5. View 使用 `input/inputs`；`source` 字段已删除。
6. Layout 不接受 item 坐标；`items/x/y/height/row_height/widget` 字段已删除。
7. Source 不使用 `depends_on`；多输入计算进入 Server Transform。
8. `workspace.yaml` 只保存 `folders`，不接受 `navigation/trash` 旧树结构。
9. Dashboard 必须是 `dashboards/` 的直接子目录；逻辑层级只用 `##` 编码。
10. 自定义 Renderer 显式注册，不覆盖全局 Canvas renderer。
11. Standalone definition 必须显式携带 `schema`；版本字段是 Literal，未知 URI 不能进入 Loader/Runtime。

当前 `dataviz-tool` 示例和 Workspace 直接迁移到新 Schema。`dataviz migrate WORKSPACE` 默认只预览；`--apply` 执行已注册的离线文件迁移。当前可以为可无歧义识别的 standalone definition 补版本头，未知历史 URI 则阻断。不要增加 alias、deprecated 字段、静默 Runtime 转换或双写协议。旧 `dashboard2` 只读，永远不参与兼容判断。

Workspace Loader 的 fail-soft 只用于隔离损坏 Dashboard 和非关键 Presentation；它不是 Schema 兼容层。

## 14. 当前实现与已知边界

已实现：

- Adapter、Source、Server Transform、OutputBundle、Browser Transform、Renderer、Presentation 全链路。
- 多 Named Output 与 table/scalar/object/text/html/chart/image/file Artifact。
- Python 进程隔离、timeout、traceback/log、缓存依赖指纹。
- SQL 查询进程隔离、硬 timeout/cancel 与结构化错误分类。
- Browser Transform Worker 拓扑、异步入口、取消、硬超时、可序列化错误、局部失效和分支失败隔离。
- Renderer Registry 和内置 Renderer。
- 可达 Output payload、嵌入上限，以及 JSON/Arrow IPC 自动传输、HTTP gzip、导出 gzip 分片与异步解码。
- CLI 内置机器可读文档、Context、query/run/output/report/serve。
- 服务端 DAG 的依赖就绪节点并发执行。
- 默认 Run 从 View、Repeat 和 Canvas inputs 反推最小服务端目标闭包。
- NodeResult/Named Output 运行中提交，`output_ready` + Output API 驱动 View 分支级提前展示。
- Output Store 增量注入后只运行刚满足的 Browser Transform 并重绘受影响 View。
- Layout 已删除坐标 item；默认单列文档流，Presentation 使用语义 Section 模板与 `span/min_height`。
- 功能 CSS 与默认视觉 CSS 分层，自定义 Canvas 可完全替换默认布局。
- 完整 Component Registry、真实内置 Gallery、`context --focus`、`scaffold` 和确定性 authoring benchmark。
- Canvas Manifest 使用 `dataviz/runtime/v1`，将 Python 发布层与当前 Vanilla JS Adapter 解耦。
- RunRecord、Run Artifact 和缓存的数量/时间保留策略，以及 dry-run 优先的 `dataviz clean`。
- Perspective 显式 create/update/flush/dispose 和 v5 主版本/API 检查。
- Repeat 搜索、分页式 DOM 上限、视口懒挂载、离屏回收和真实浏览器规模 Benchmark。
- Component Package 的 Manifest/Controller/Adapter/Style/Story/Test 物理共置和 Registry v3 完整性检查。
- Story 驱动 Gallery 索引、统一 Overlay，以及 select、segmented、checkbox-group、date-range、cascader、tree-select Selector。
- 自定义 Renderer 的 JS/CSS/Contract 脚手架、异步生命周期错误边界和 Chromium 契约测试。
- 真实 Chromium E2E 覆盖弹层收起、三级级联、Cascader 多分支、View 隔离、Selector 键盘/焦点/视口几何、大列表 DOM 上限、Table/Perspective 滚动、渐进失败、Worker 取消/超时、Arrow 和 1,000 分组 Repeat。
- `dataviz schemas` 从当前 Pydantic 模型生成紧凑字段契约或完整 JSON Schema；Component 文档继续从 Registry/Package 生成。
- append-only `dataviz-authoring.jsonl` 与 start/note/finish/show CLI，记录真实首次成功、修正、耗时、Token 和文档/设计 friction，不估算缺失 Token。
- 严格 Schema URI、dry-run 优先的离线 migration、可读 Changelog 和独立版本说明。
- 第二 Web Component Frontend Adapter、公共 Output 变更事件，以及不加载默认 Canvas Runtime 的真实浏览器契约测试。
- Python 3.11–3.14、Chromium/Firefox/WebKit、wheel/sdist/pip ZIP 干净安装的 CI 定义；ZIP 固定排序/时间戳并生成 SHA-256。

尚未实现：

- 声明式 View Renderer、Arrow Output Store、Worker Controller、Perspective Adapter、Repeat Controller 和剩余 Section/Presentation 桥接代码仍需从 `canvas-runtime.js`、`declarative-runtime.js` 与 Python `CanvasRenderer` 迁入对应物理 Package；它们已有 Component owner，但实现代码尚未完全迁出旧位置。
- Gallery 当前由 Story 自动生成清单、锚点和导航，真实 specimen 仍由生产 Dashboard DSL 编排；后续可增加完全由 Story fixture 生成的独立边界状态画布和跨浏览器像素基线。
- 真实 authoring 记录机制已经可用，但尚未积累足够任务样本来设定 Token、首次成功率或完成时间目标；benchmark 继续记录文件/Context bytes 与可重复页面指标。
- Arrow 上的浏览器列式筛选/聚合、服务端分页和只取可见 Record Batch；当前实现会传输完整可达 Output，并在实际消费时物化行对象。
- 命名多套 Presentation。
- 更细粒度的 CLI focus/inspect。

这些是明确的后续路线，不用“兼容占位接口”提前污染当前 Schema。

## 15. 面向 AI 的长期 DSL

Dataviz 长期是一套看板 DSL，而不是前端代码脚手架。模板减少重复 output token；结构化 Context、精确诊断和机器可读 Registry 减少 input token 与试错次数。两者必须一起优化。

模板体系需要同时满足：

1. 常见需求必填字段少，默认值可交付。
2. 一个需求尽量只有一条明显正确的表达路径。
3. 错误指向具体节点、Output、字段和修复方向。
4. 从模板参数到完整 Canvas 渐进扩展。
5. 样式不能偷偷改变数据口径。
6. AI 不读 Runtime 源码也能发现并组合组件。

当前优先级：

```text
正确可用
  → 默认体验稳定
  → 模板覆盖常见需求
  → 诊断减少试错
  → Compact Context 与 Token 基准
```

现在不设置理想化 Token 数字。待产品稳定并积累真实开发样本后，再建立 Context 切片和 Token 基准。

基准任务至少覆盖：默认 KPI+图+表、三级 Selection、复杂 Server/Browser Transform、多 Named Output、自定义 Canvas 和自定义 Renderer。每项记录输入 Context 大小、生成文件大小、首次 validate/运行成功率、修正轮次和完成时间。LOC 只是其中一个指标。

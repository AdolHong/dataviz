# Dataviz 当前实现索引

更新时间：2026-08-24

本页帮助开发者和 AI 从产品契约定位到代码。设计语义以 [DESIGN](../DESIGN.md) 为准；字段以当前安装环境的 `dataviz schemas` 为准。

## 1. 版本边界

```text
Workspace              dataviz/workspace/v1
Dashboard              dataviz/dashboard/v2
Presentation           dataviz/presentation/v1
Source                 dataviz/source/v1
Dataset Transform      dataviz/dataset-transform/v1
Interactive Transform  dataviz/interactive-transform/v1
Browser Runtime        dataviz/runtime/v2
Component Registry     3.0.0
```

这些契约独立版本化。Loader 只接受当前严格模型，不包含旧字段 alias、自动迁移或双协议执行分支。

关键入口：

- 领域模型：`src/dataviz/workspace/models.py`
- Workspace 加载与跨文件校验：`src/dataviz/workspace/loader.py`
- 机器可读 Schema：`src/dataviz/schema_docs.py`
- CLI 内置手册：`src/dataviz/documentation.py`

## 2. Query DAG

```text
Query Parameter → Source → Dataset Transform → Base Named Output
```

- 编排：`src/dataviz/execution/plan.py`
- 执行：`src/dataviz/execution/executor.py`
- Source Runner：`src/dataviz/sources/`
- Python 子进程：`src/dataviz/execution/python_process.py`
- Artifact 与 Named Output：`src/dataviz/artifacts/`、`src/dataviz/execution/outputs.py`
- 缓存：`src/dataviz/execution/cache.py`

Query Run 固化 Query Parameter 和 Base Output。Selection/Compute Parameter 不进入这张 DAG。节点按依赖闭包并发，Output 完成后立即发布；无关分支不互相等待。

File、SQL、Python 是 Source 的三种入口。SQL 默认单次超时 120 秒，明确超时后立即额外重试一次；Source 可以覆盖 `timeout_seconds` 与 `timeout_retries`。SQL 面板保存参数化 statement、Resolved SQL、bound parameters、Adapter、耗时、重试和 hash 证据，但不公开凭证。

Python Source 与 Dataset Transform 使用 fresh spawn 子进程，支持硬 timeout、cancel、progress、完整 traceback、声明依赖指纹、多输入和多 Named Output。`context.log(...)` 产生实时 `node_log`，并保存 `dataviz/execution-log/v1` Artifact；Artifact 受 tab session 隔离，Query 节点可在 Sources 证据面板直接检查。

## 3. Interactive DAG

```text
Base/Derived Output + committed Query snapshot + Selection + Compute Parameter
                                      ↓
                           Interactive Transform
                                      ↓
                            Derived Named Output
```

- 服务端计划与执行：`src/dataviz/execution/interactive.py`
- Browser 控制器：`src/dataviz/server/static/canvas-runtime.js`
- browser-js Worker：`src/dataviz/server/static/interactive-js-worker.js`
- browser-python Worker：`src/dataviz/server/static/interactive-python-worker.mjs`
- Server Run/generation 隔离：`src/dataviz/server/manager.py`

公共 Runtime Adapter 生命周期是：

```text
validate → prepare → execute → cancel → dispose
```

三种 Runtime 都只返回声明的 Named Output，不访问 Renderer DOM，也没有 Adapter：

- `server-python`：独立进程，适合本机原生依赖；HTML 只能 snapshot/unavailable。
- `browser-python`：Pyodide module Worker；HTML 可继续计算。
- `browser-js`：Web Worker；默认的轻量浏览器计算路径。

能等价实现且输入适合浏览器时，默认选择 `browser-js → browser-python → server-python`。这是可移植性、启动成本与部署复杂度的建议顺序；原生依赖、求解器或大规模计算仍直接使用 server-python。

每次交互以 `tab + dashboard + query run + transform + generation` 隔离。较新的 generation 只 supersede 相同分支的旧任务；迟到请求会收到 `interaction_generation_stale`，不能覆盖新结果。

`trigger` 支持 `apply`、`auto` 和 `manual`。Compute Control 区分 draft/committed；内容绑定和 provenance 只描述真正产生当前结果的 committed state。

## 4. Output、状态和证据

Canonical Output Reference：

```text
source:<id>/<name>
dataset:<id>/<name>
interactive:<id>/<name>
```

所有节点共用 `NodeResult.outputs` 和 `ArtifactDescriptor`。Output 类型包括 table、scalar、object、text、html、chart、image 和 file；声明名称与实际返回必须完全一致。

节点状态统一为：

```text
not_run → queued → loading → ready | empty | error | cancelled | unavailable
                         ↘ stale（交互结果等待重新提交）
```

运行证据包括输入 content hash、代码与依赖指纹、参数快照、缓存来源、耗时、progress、结构化日志和错误 traceback。缓存命中复用 Output，但不会冒充一次新的 Python 执行日志。

## 5. Browser Runtime 与局部更新

Server 与 HTML 共享 `canvas-runtime.js`、Renderer Registry、Selection/Compute Control 和 Overlay 行为。公开边界是 `dataviz/runtime/v2` Manifest、Named Output Store 和 Runtime Event。

Runtime 根据显式依赖建立反向索引：

- Query Output 就绪时只启动刚满足依赖的 Interactive Transform 和 View。
- Selection 只筛选字段适用且位于其作用域内的 View。
- View Selection 不重绘兄弟 View。
- Compute Parameter 只失效声明消费它的 Interactive Transform 下游。
- 新 Run 可以显示 stale 旧结果，但不会把两个 Run 的 Output 静默混合。

大 Table 的传输可使用 Arrow IPC/columnar envelope；浏览器按需解码。部分通用 Selector 和 Renderer 首次消费时仍会物化 JavaScript 行对象，当前不承诺完整的浏览器列式查询引擎。

Renderer 生命周期：

```text
validate → mount → update → dispose
```

Plotly、ECharts、普通 Table、Perspective、文本、图片和自定义 Renderer 都通过这个边界工作。Perspective 自己拥有内部滚动和 WASM/Table 生命周期；只有内部确实能继续滚动时才拦截滚轮。

## 6. HTML Export

Interactive Transform 必须声明：

- `interactive`：导出后继续计算，只适用于浏览器 Runtime。
- `snapshot`：固化当前 Derived Output 与状态，相关控件只读。
- `unavailable`：明确展示离线缺失能力和原因。

Server 页面导出时会向 Canvas 请求 canonical snapshot；请求按当前 Dashboard contract 清除 sessionStorage 中可能遗留的未知 key。server-python 在独立 HTML 中没有执行端，只能 snapshot/unavailable，不会被伪造成离线 Runtime。

browser-python 的 interactive export 支持：

- `cdn`：HTML 保存 Pyodide index URL，首次交互时按需加载；
- `bundle`：CLI 生成 HTML、`<stem>.assets/pyodide/` 和 manifest，Server 返回包含它们的 ZIP；解压后通过 HTTP 打开。

Pyodide Worker、URL 和资产按可执行分支裁剪。没有 browser-python，或分支已经 snapshot/unavailable 时，不携带无用 Python Runtime。

本地 bundle 必须是完整 Pyodide 分发根目录。静态预检检查核心 loader/WASM/stdlib/lockfile，并从 `micropip` 与声明依赖出发验证 lockfile 传递闭包、wheel 文件和 SHA-256；这保证 `bundle` 表示无需外网的运行包，而不只是把 `pyodide.mjs` 复制进报告。

CLI 无浏览器上下文时不会替用户伪造 browser snapshot。需要当前页面交互状态的报告由 Server 页面导出；确定性的默认状态报告可以使用 `dataviz report`。

## 7. Workspace、Adapter 和隔离

- Dashboard 文件夹末级名称是导航显示名。
- `dashboard.id` 是 API、DAG、缓存和状态的稳定身份。
- `##` 编码逻辑目录，`__TRASH__##` 编码回收站。
- `workspace.yaml` 只补充空目录、顺序和 Runtime 等磁盘命名无法表达的状态。
- Dashboard 只引用 Adapter 别名；凭证留在 `auth/adapters.local.yaml` 或环境变量。

Server 状态以浏览器 tab 的 `session_id` 为边界。不同 tab、Dashboard、用户、Query Run 和 Interaction generation 不共享草稿、取消信号或运行证据。内容寻址缓存可以复用相同输入的结果，但不会共享交互状态。

## 8. Component 与 Presentation

默认 Presentation 使用文档流；删除 `presentation.yaml` 后 Dashboard 仍必须可读、可交互。样式扩展顺序是：

```text
默认组件 → 模板参数 → Theme token/css_class → 自定义 Renderer → 完整 Canvas
```

Component Registry v3 从 `src/dataviz/components/packages/` 扫描 Package。每个 Package 声明 owner、Schema、controller、adapter、功能 CSS、Story 和测试。Overlay、Selector 和 Custom Renderer 已具有独立物理实现；声明式 View/Section、Data Pipeline 与 Presentation 仍有桥接代码，后续归属整理见 [plan](../plan.md)。

## 9. 静态校验与 AI 开发入口

`dataviz validate` 不查询数据，覆盖：

- 严格 Schema、重复 ID、路径与 Adapter。
- SQL 参数、Python/Pyodide 依赖。
- Query/Interactive DAG、Output 引用与环。
- 三类状态的 namespace 和作用域。
- trigger/export/Runtime 组合。
- Presentation、Component 和内容绑定。

主要 AI 入口：

```bash
dataviz docs quickstart
dataviz schemas dashboard --full --format json
dataviz components --check --format json
dataviz context WORKSPACE DASHBOARD --focus interactive:<id> --format json
dataviz validate WORKSPACE --dashboard DASHBOARD --format json
dataviz authoring tasks --format json
dataviz authoring protocol --format json
dataviz authoring prepare TASK DIRECTORY --approach dataviz|standalone-html --trial-id TRIAL
dataviz authoring assess DIRECTORY CHECK --status passed --assessor automation --evidence "..."
dataviz authoring verify DIRECTORY --format json
dataviz authoring compare MEASUREMENT_WORKSPACE --format json
```

固定 trial 使用任务契约与输入 SHA-256；逐项验收必须留下 assessor 和证据，只有两种方案均保持输入完整并通过全部验收时才进入效率聚合。

错误应包含稳定 code、文件、字段、节点/依赖细节和修复建议。AI 不需要读取整个 Browser Runtime 才能新增普通看板。

## 10. 当前明确限制

- 这是可信单机执行环境，不是不可信代码沙箱，也不提供多租户 CPU/内存额度。
- 通用服务端分页、按需 Record Batch 和完整浏览器列式执行尚未实现。
- 部分 Component 已有 owner contract，但物理实现仍位于大型 Runtime 中。
- Gallery 的完整状态、键盘和超大数据矩阵仍需扩展。
- Token 节省是待真实任务评测的产品假设，不承诺固定数字。
- 成对评测工具已经实现；真实重复 trial 与结果发布尚待积累。

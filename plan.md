# Dataviz 当前计划

更新时间：2026-08-24

稳定架构见 [DESIGN](DESIGN.md)，代码入口见 [当前实现索引](docs/product-architecture.md)，发布历史见 [CHANGELOG](CHANGELOG.md)。安装版本实际接受的字段始终以 `dataviz version`、`dataviz schemas`、`dataviz components` 和 `dataviz docs` 为准。

## 1. 当前基线

- Package：`0.1.4`
- Python：3.11–3.14
- Dashboard：`dataviz/dashboard/v2`
- Browser Runtime：`dataviz/runtime/v2`
- Dataset Transform：`dataviz/dataset-transform/v1`
- Interactive Transform：`dataviz/interactive-transform/v1`
- Component Registry：`3.0.0`

项目尚未投入生产，因此 Loader 只接受当前严格契约；不存在旧字段 alias、自动迁移、deprecated 双写或第二套 Runtime。

## 2. P0：Data Execution Architecture — 已完成

### 状态与执行边界

- [x] Query Parameter、Selection、Compute Parameter 使用独立 namespace、提交周期和失效路径。
- [x] Query DAG 只包含 Source/Dataset Transform；Interactive DAG 只在不可变 Base Output 上产生 Derived Output。
- [x] Source、Dataset Transform、Interactive Transform 共用显式 Named Output、Schema Contract、错误与 provenance。
- [x] Query/Interactive DAG 按依赖闭包并发，完成的独立分支立即发布；局部失败不阻塞无关 View。
- [x] server-python Interactive 链可复用同一 Query Run、相同状态下已经完成的上游 generation，不因分别请求下游而重复执行无缓存上游。

### 严格 Value 与 Output Contract

- [x] Python Server、CLI、父页面表单与 Canvas Runtime 共用 string/number/integer/boolean/date/date-range/select 语义。
- [x] required、min/max/step、静态 choice、typed choice 和日期范围采用稳定错误码；空日期范围 canonical 为 `[]`。
- [x] Selection 只接受 canonical key，不再保留短名或歧义 alias。
- [x] Output 的 kind、required/optional Named Output、Table schema、strict JSON 与 Input schema 在 Server/Browser 边界校验。
- [x] 直接返回已有 Artifact 也不能绕过声明的 kind/schema 契约。
- [x] Python 子进程保留稳定错误 details、完整 traceback、结构化日志和运行 Artifact。

### Runtime、缓存与生命周期

- [x] Python/SQL 节点有硬 timeout、cancel 和进程隔离；SQL 默认 120 秒，明确超时后立即用新连接额外重试一次。
- [x] browser-js/browser-python 使用 Worker、timeout、supersede cancellation、generation last-write-wins 和 dispose。
- [x] Browser Runtime cache 只允许 `none/session + tab`；Server 节点只有显式 `ttl/persistent + workspace` 才能跨 tab 复用 Artifact。
- [x] 同一 tab 可恢复状态；不同 tab、Dashboard、用户、Query Run、Interaction generation 的状态、取消与证据互不干扰。
- [x] 内存 Run/Interaction/event/cache 有数量与时间上限；事件截断保留单调 offset，磁盘 Artifact 随 Run retention/clean 清理。
- [x] 大 Table 支持 Arrow/columnar 传输，消费方按需物化行。

### HTML Export 与 Pyodide

- [x] Interactive Transform 强制声明 `interactive | snapshot | unavailable`。
- [x] browser-js/browser-python 可在 HTML 中继续计算；server-python 只能 snapshot/unavailable，并冻结不会离线重算的控件。
- [x] browser-python 支持 `cdn` 与 `bundle`；bundle 产生 HTML + assets + manifest，Server 下载 ZIP。
- [x] `validate` 检查固定 Pyodide 版本、精确依赖、WASM/pure wheel 与 bundle 完整性。
- [x] bundle 完整性覆盖核心 Runtime、lockfile、`micropip`、声明依赖的传递 wheel 闭包与 SHA-256，不把单独 loader 误判为离线包。
- [x] 无活动 browser-python，或分支已 snapshot/unavailable 时，报告不携带 Python Worker、Pyodide URL 或 bundle 资产。
- [x] 导出采集 canonical Canvas snapshot，并剔除 sessionStorage 遗留的未知 Selection key。

### CLI 与可审查性

- [x] `validate` 是零查询静态门禁，覆盖严格 Schema、两个 DAG、状态 namespace、Runtime/export、依赖、Output、内容绑定和作用域引用。
- [x] `compute` 对已有 Query Run 执行 server-python Interactive Transform，不重新取数。
- [x] Sources 面板公开参数化 statement、Resolved SQL、bound parameters、Adapter 类型、timeout/retry 与 hash，但不泄露凭证。
- [x] `docs`、`schemas`、`components`、`context` 和 `scaffold` 可由全新 AI 会话机器读取。

P0 的 Definition of Done 是完整 unit/contract、Chromium Runtime E2E、四个示例 Workspace validate/report smoke、以及 wheel/sdist/ZIP 干净安装 smoke 均通过；2026-08-24 已用 editable 源码 CLI 和三个独立安装环境完成本地门禁。具体测试数量以当次测试输出和发布记录为准，避免计划文档长期保存失真的计数。

## 3. P1：Component 与实际交互能力 — 已实现当前范围

- [x] Component Registry v3 提供 13 个物理 Package，覆盖 Pipeline、Presentation、View/Section、Custom Renderer、Overlay 与六类 Selector。
- [x] Package 带 manifest、controller、adapter、功能 CSS、真实 Story 和 contract tests；`components --check` 可验证。
- [x] Select、Segmented、Checkbox Group、Date Range、Cascader、Tree Select 支持搜索、级联 reconciliation、全选/反选、弹层关闭和键盘/焦点基础行为。
- [x] 普通 Table 与 Perspective 是独立模板；Perspective 管理内部滚动边界与生命周期。
- [x] Small Multiples / Selection Gallery 共用一个 Named Output，支持搜索、分页、懒挂载和离屏回收；真实浏览器覆盖 1,000 个实体。
- [x] 默认文档流、语义 Section/Layout、Theme token、自定义 Renderer 和完整 Canvas 构成逐级逃生路径。

当前范围不要求把所有大型 Runtime 文件机械拆小。物理 owner 仍有桥接代码，但公开契约已经固定；只有下一次框架替换或 owner 冲突证明成本时，才进行内部搬迁。

## 4. P1：验证 AI 开发效率 — 工具完成，真实采样待进行

- [x] 固定五类对照任务：默认看板、三级 Selection、复杂多输出 Dataset Transform、三 Runtime Interactive Transform、自定义 Renderer。
- [x] `authoring prepare` 为两种 approach 生成相同、带 SHA-256 的中性输入包、固定任务契约和逐项 assessment，并拒绝覆盖非空目录。
- [x] `dataviz authoring tasks/protocol` 发布机器可读任务、统一验收和成对试验方法。
- [x] `authoring verify/assess` 校验任务/输入哈希，并要求每条验收项记录 human/automation/mixed assessor 与证据。
- [x] `authoring-event/v3` 记录 benchmark task、approach、契约/输入 identity、逐项验收、模型、客户端、真实 Token、首次成功、修正轮次、耗时和 friction。
- [x] `dataviz authoring compare` 区分 complete、identity-matched 和 quality-passed pairs；只有两边输入完整且逐项通过验收的可比 pair 进入聚合，不能仅靠自报 `outcome=success` 绕过。
- [x] 缺失 Token 保持 unmeasured，不按字符数、文件大小或经验值估算。
- [ ] 使用相同模型/客户端，对每类任务执行多次随机顺序 trial，发布原始 JSONL、环境说明和结果。
- [ ] 根据真实 friction 与结果压缩 focused context、CLI docs 和 Scaffold；不预设固定 Token 上限或节省比例。

最后两项需要真实 AI 客户端的计费/usage 数据和独立会话，不能由仓库测试伪造。评测方法见 [AI Authoring 成对评测协议](docs/authoring-evaluation.md)。

## 5. P2：规模、组件归属与浏览器矩阵

以下是已经有现实基础、但尚未完成的工程工作：

- [ ] 建立 10K、100K、1M 行 Query → Arrow → Interactive → Renderer 分段基准，记录传输、解码、物化、计算、渲染和内存回落。
- [ ] 由基准决定是否实现服务端分页、按需 Record Batch、浏览器列式 Selection 或更严格的大输入降级；不预先扩张 DSL。
- [ ] 补齐 Selector、Compute、View、Section 的 Ready/Loading/Stale/Empty/Error/Cancelled/Unavailable 状态矩阵与 10/100/1,000 选项 Story。
- [ ] 扩展 Chromium/Firefox/WebKit 的窄视口、弹层几何、滚动、键盘、ARIA、Perspective 恢复与重复 dispose 测试。
- [ ] 当桥接代码真正阻碍新框架接入时，把 data.pipeline、view.declarative、section.declarative、presentation.shell 的实现完全迁入 owner Package，并用公开 Runtime v2 contract tests 防回归。

当前仍是可信单机工具，不把多租户 CPU/内存额度列入近期工作。

## 6. 开源发布

- [ ] 维护者决定许可证并添加正式 `LICENSE`。当前没有擅自选择；公开可见不等于已经授予再分发或商用权利。
- [ ] 增加 `CONTRIBUTING.md`，说明安装、validate/test、Runtime/Component 变更和 PR 验收。
- [x] 示例验收集改名为 `feature-showcase / 功能示例`，不再把当前 v2 看板描述成旧系统迁移层。
- [x] GitHub Actions 已定义 Python 3.11–3.14、Chromium/Firefox/WebKit、JavaScript 语法与三类发行包矩阵；正式发布仍需保留远端 workflow 成功记录。
- [x] wheel、sdist 和 pip ZIP 已分别做本地干净安装 smoke；ZIP 构建固定排序/时间戳、输出 SHA-256，并支持 `--output-dir` 在临时目录验收。
- [ ] 正式 GitHub Release 发布对应产物、SHA-256 与远端 CI 记录。

许可证决策独立于 P0/P1 功能，不阻塞当前开发；正式对外发布前必须完成。

## 7. 按需求触发的候选

| 候选 | 触发条件 |
| --- | --- |
| `number-range`（Slider + InputNumber） | 多个真实 Dashboard 需要连续区间，且现有输入体验不足。 |
| month/quarter/year 日期控件 | 真实时间分析需要原生粒度。 |
| Transfer / Entity Picker / Drawer | 大量实体还需展示状态、负责人等辅助列。 |
| 单文件内联 Pyodide 实验 | 用户明确必须只有一个 HTML，并接受显著体积、启动与浏览器兼容成本；当前 bundle 已满足离线文件包。 |
| 多套命名 Presentation | 同一逻辑 Dashboard 出现稳定、重复的多品牌/渠道发布需求。 |

新 Component 或 Runtime 必须由真实需求触发，并说明数据语义、与现有能力的差异、AI 选择规则、Gallery Story 和测试成本。

## 8. 非目标

- 已移除实验契约的兼容层或自动迁移执行路径。
- 可视化编辑器、Mosaic/坐标布局和旧 Widget 协议。
- 让 Pyodide/Python 直接操作 DOM、渲染图表或成为第二套 View 系统。
- Interactive Transform 隐式访问 Adapter 或重新查询 Source。
- 默认多租户资源配额与不可信代码沙箱。
- 在缺少真实场景前增加更多 Runtime、空接口或 UI 组件副本。

## 9. Definition of Done

每项公开能力必须同时满足：

1. 严格 Schema、稳定错误码和 `dataviz validate` 的静态提前发现。
2. CLI docs/schemas/components/context 可被全新 AI 会话直接发现。
3. 默认样式、可覆盖 token/hook 和无 Presentation 的朴素退化路径。
4. Gallery Story、契约测试和至少一个真实浏览器行为测试。
5. Server 与导出 HTML 共用实现，局部状态变化不误重绘无关 View。
6. 正确的 timeout、cancel、error、dispose、状态隔离和 provenance。
7. README/DESIGN/CHANGELOG 只陈述真实能力，计划与当前实现明确区分。

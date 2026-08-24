# Dataviz

Dataviz 是一套 **workspace-first、AI-friendly** 的 Python 看板工具。

它不把分析锁在中心服务或可视化编辑器里。一个 Dashboard 就是一个普通文件夹，可以进入 Git、复制给同事并接受代码审查；数据连接和凭证留在每个人自己的 Workspace 中。

- 人使用 `dataviz serve` 浏览、查询和交互。
- AI 与自动化使用 CLI 校验、查数、计算、调试和导出 HTML。
- 普通看板只写声明式 YAML、SQL/Python/JavaScript 逻辑和简单布局。
- 特殊页面可以逐级覆盖 Theme、Component、Renderer、CSS/JS，完整 Canvas 是最后的逃生口。

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

Select 型 Selection 可以写静态 `choices`，也可以从数据生成选项。动态选项不会从“当前 View 已筛选后的 Derived Output”反推，否则会形成“先有 Selection 还是先运行 Transform”的循环；Runtime 会追溯该 View 的不可变 Base Output，复杂或多输入场景可显式写 `options_from: source:<id>/<output>`。`dataviz validate` 会提前拒绝未知、非表格、Interactive Output 或无法提供字段的 option domain。

Query Run 的可达 Base Output 会写入 Workspace 的 `.dataviz/runs/<run-id>/artifacts/`，不会写进 Dashboard 文件夹。Runtime 会额外标记被 `server-python` Interactive Transform 消费的 canonical Output；后续交互按 `browser tab session + dashboard + query run + output reference` 读取同一份不可变快照，刷新当前 tab 可以继续使用，其他 tab 或用户不能访问，也不会暗中重新执行 Source。Run 与缓存受 Workspace 保留策略统一清理，因此分享 Dashboard ZIP 不会夹带运行数据。

简单逻辑默认按 `browser-js → browser-python → server-python` 选择：前两者可让导出报告继续交互，后者适合原生 Python 包、大模型、运筹求解和大规模计算。这个顺序强调可移植性和启动成本，不是绝对性能排名。

当前契约是 `dataviz/dashboard/v3` 与 `dataviz/runtime/v2`。项目处于 `0.x` 阶段，不兼容更早的实验性 Dashboard/Transform 字段，也不在 Runtime 中保留迁移分支。

## 快速开始

要求 Python 3.11–3.14，推荐 Python 3.12。

从源码安装：

```bash
git clone https://github.com/AdolHong/dataviz.git
cd dataviz
uv sync --python 3.12 --extra dev --no-editable \
  --reinstall-package workspace-dataviz
uv run --no-editable dataviz version
```

创建 Workspace 并启动网页：

```bash
uv run --no-editable dataviz init myworkspace
uv run --no-editable dataviz serve myworkspace --port 8080
```

然后打开 <http://127.0.0.1:8080>。

Server 不提供账号体系或 HTTP 鉴权，默认只监听本机回环地址。只有已经放在可信网络边界后时，才可显式使用 `--host 0.0.0.0 --allow-remote`；`session_id` 只隔离浏览器 tab 状态，不是访问凭证。

这个源码流程故意使用 non-editable 安装，避免部分 macOS/Python 组合跳过带 `UF_HIDDEN` 标记的 editable `.pth`。修改 Dataviz 自身的 `src/` 后需要重新执行上面的 `uv sync ... --reinstall-package`；只修改 Workspace/Dashboard 不需要重装。若出现 `ModuleNotFoundError: dataviz`，也执行同一条命令修复入口。

```bash
uv sync --python 3.12 --extra dev --no-editable \
  --reinstall-package workspace-dataviz
```

从发行 ZIP 安装时：

```bash
python -m pip install ./workspace-dataviz-0.3.1.zip
dataviz version
dataviz serve /path/to/workspace --port 8080
```

## AI / CLI 工作流

每次修改 Dashboard 后，先做不执行查询的静态检查：

```bash
dataviz validate myworkspace --dashboard sales-overview --format json
```

再按需要查询、检查 Named Output、运行服务端交互计算或导出报告：

```bash
dataviz query myworkspace sales-overview --source sales --format json
dataviz output myworkspace sales-overview source:sales/main
dataviz compute myworkspace sales-overview simulation \
  --run-id run_xxx \
  --compute-param dashboard:sales-overview/seed=42 --format json
dataviz report myworkspace sales-overview --output report.html
dataviz benchmark myworkspace sales-overview --browser-runtime --format json
```

`benchmark --browser-runtime` 会在 Chromium 中等待页面达到稳定状态，并分别报告 Query、HTML 构建、页面就绪、Arrow 传输、Renderer 生命周期和 View 终态；它用于规模回归，不代替真实 AI Token 成对评测。

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
dataviz schemas dashboard --full --format json
dataviz components --format json
dataviz gallery --output component-gallery.html
dataviz context myworkspace sales-overview --focus view:revenue --format json
```

Component Registry 的 13 个 Package 都物理拥有自己的 controller、Runtime Adapter、功能 CSS、Story 与测试声明。内置 Gallery 还提供 Selector、Control、View、Section 的 `ready / loading / stale / empty / error / cancelled / unavailable` 状态矩阵，以及真实 10、100、1,000 选项的 Select Story；AI 可以先复用这些已验证组件，再决定是否写局部 CSS/JS。

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

Dashboard 文件夹末级名称就是导航显示名；`##` 表达逻辑目录，`__TRASH__##` 表示回收站。`dashboard.id` 是 CLI/DAG 使用的稳定机器 ID，使用可跨 Windows/Linux/macOS 的 ASCII 字母、数字、点、下划线和连字符；中文等展示内容放在文件夹名、`title`、`subtitle` 和 `description`。

页面只有两个一级入口：`Parameters` 负责重新查询，`Controls` 负责 Query 后的选择与计算。Controls 在同一托盘内按 DATA（selection）和 LOGIC（compute）分组；参数多时自动分栏，面板过高时在内部滚动，不会击穿屏幕。各 Dashboard 可在可选的 `presentation.yaml` 中只改视觉编排，而不复制交互逻辑：

```yaml
controls:
  query: {template: grid, width: wide, columns: 3, density: compact}
  dashboard: {template: grid, width: regular, columns: 2}
```

`template` 支持 `auto | stack | grid`，`columns` 支持 1–4；Section/View 还可通过各自 Presentation 条目的 `controls` 覆盖局部托盘。值、校验、级联、tab 状态和 Query/Interactive 执行仍由共享 Runtime 管理；导出 HTML 中 Query 变为固定快照，Controls 继续可交互。

`auth/adapters.yaml` 保存可提交的非敏感连接定义，`auth/adapters.local.yaml` 以同名 Adapter 覆盖本地凭证且必须被 Git 忽略。只有这两个位置会被加载，避免根目录旧文件或“示例文件”意外覆盖实际配置。Dashboard 只引用 Workspace Adapter 的逻辑名称，不保存账号密码。内置数据入口包括本地文件、DuckDB、MySQL、StarRocks 和可信 Python Source。

当前 `dataviz serve` 的受支持部署方式是：一个 Workspace 对应一个 Dataviz Server 进程。Server 没有账号体系或 HTTP 鉴权，默认只允许回环地址；远程监听必须显式传入 `--allow-remote`，并由可信网络、反向代理或其他外部边界负责访问控制。Run、Navigation 和持久缓存的协调锁是进程内锁；不要让多个 Server 进程同时写同一个 Workspace 或同一个报告路径。修改 Runtime 并发上限后需重启 Server。

需要生成配置时，先运行 `dataviz scaffold --list --format json` 获取当前安装版本真正支持的 Recipe；Component ID 与 Scaffold Recipe 不是同一套名字。生成或修改后始终运行 `dataviz validate <workspace>`。

## 文档

- [设计与架构不变量](DESIGN.md)
- [当前计划与验收状态](plan.md)
- [代码实现索引](docs/product-architecture.md)
- [版本与发布流程](docs/versioning-and-release.md)
- [AI 开发效率评测协议](docs/authoring-evaluation.md)
- [变更记录](CHANGELOG.md)

项目尚未添加正式 `LICENSE` 文件；在许可证补齐前，公开可见不等于已经授予再分发或商用权利。

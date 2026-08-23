# Dataviz

Dataviz 是一套 **workspace-first、AI-friendly** 的 Python 看板工具。

它不把分析锁在中心服务或可视化编辑器里。一个 Dashboard 就是一个普通文件夹，可以进入 Git、复制给同事并接受代码审查；数据连接和凭证留在每个人自己的 Workspace 中。

- 人使用 `dataviz serve` 浏览、查询和交互。
- AI 与自动化使用 CLI 校验、查数、计算、调试和导出 HTML。
- 普通看板只写声明式 YAML、SQL/Python/JavaScript 逻辑和简单布局。
- 特殊页面可以逐级覆盖 Theme、Component、Renderer、CSS/JS，完整 Canvas 是最后的逃生口。

## 核心模型

```text
Query Parameter
       ↓
Adapter → Source → Dataset Transform（可选）
                              ↓
                       Base Named Output
                              ↓
Selection + Compute Parameter
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
- Selection 只表达“包含哪些已有样本”，不重新取数。
- Compute Parameter 决定如何计算已有数据，只重算声明依赖它的交互分支。
- 三种 Interactive Runtime 使用相同 Named Output 契约；图、表和文本统一由 JavaScript Renderer 呈现。

简单逻辑默认按 `browser-js → browser-python → server-python` 选择：前两者可让导出报告继续交互，后者适合原生 Python 包、大模型、运筹求解和大规模计算。这个顺序强调可移植性和启动成本，不是绝对性能排名。

当前契约是 `dataviz/dashboard/v2` 与 `dataviz/runtime/v2`。项目处于 `0.x` 阶段，不兼容更早的实验性 Dashboard/Transform 字段，也不在 Runtime 中保留迁移分支。

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

这个源码流程故意使用 non-editable 安装，避免部分 macOS/Python 组合跳过带 `UF_HIDDEN` 标记的 editable `.pth`。修改 Dataviz 自身的 `src/` 后需要重新执行上面的 `uv sync ... --reinstall-package`；只修改 Workspace/Dashboard 不需要重装。若出现 `ModuleNotFoundError: dataviz`，也执行同一条命令修复入口。

```bash
uv sync --python 3.12 --extra dev --no-editable \
  --reinstall-package workspace-dataviz
```

从发行 ZIP 安装时：

```bash
python -m pip install ./workspace-dataviz-0.1.4.zip
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
  --run-id run_xxx --compute-param seed=42 --format json
dataviz report myworkspace sales-overview --output report.html
```

HTML 固定 Query Parameter。`browser-js` 可以直接保留交互；`browser-python` 可使用 Pyodide CDN，或把本地 Pyodide 作为 `HTML + assets` 文件包/ZIP 一起分发。`server-python` 在导出的 HTML 中不能重新运行，只能固化为 snapshot 或明确显示 unavailable。没有活动的 `browser-python` 分支时，报告不会携带或加载 Pyodide。

内网/离线分发时，把官方完整 Pyodide 分发解压到 Workspace，并让目录直接包含 `pyodide.mjs`、WASM、标准库、lockfile 和所需 wheels：

```yaml
# workspace.yaml
runtime:
  pyodide_bundle_path: runtime/pyodide

# browser-python Interactive Transform
export: {mode: interactive, assets: bundle}
```

`dataviz validate` 会检查核心文件、依赖闭包与 wheel 校验和。导出结果是可压缩分享的 HTML 文件包，不是单个 HTML；解压后应通过 HTTP 静态服务打开。若使用 `assets: cdn`，则无需本地 bundle，但打开报告时必须能访问配置的 Pyodide index URL。

新的 AI 会话应从安装包自带文档开始，而不是读取 Runtime 源码：

```bash
dataviz docs quickstart
dataviz docs pipeline --format json
dataviz schemas dashboard --full --format json
dataviz components --format json
dataviz context myworkspace sales-overview --focus view:revenue --format json
```

项目也内置了 Dataviz 与 standalone HTML 的成对 AI 开发评测协议；它只记录客户端提供的真实 Token，不按文本大小估算：

```bash
dataviz authoring tasks --format json
dataviz authoring protocol --format json
dataviz authoring prepare default-dashboard /tmp/trial-dataviz \
  --approach dataviz --trial-id trial-001
dataviz authoring verify /tmp/trial-dataviz --format json
dataviz authoring start myworkspace --trial-dir /tmp/trial-dataviz \
  --model MODEL_NAME --tool CLIENT_NAME
dataviz authoring compare myworkspace --format json
```

每项固定验收条件必须通过 `authoring assess` 记录 assessor 和证据；只写 `outcome=success` 不能绕过质量门禁。真实试验仍需分别使用新的 AI 会话，并从客户端记录实际 Token。

## Workspace

```text
myworkspace/
├── workspace.yaml
├── auth/
│   ├── adapters.example.yaml
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

Dashboard 文件夹末级名称就是导航显示名；`##` 表达逻辑目录，`__TRASH__##` 表示回收站。`dashboard.id` 是 CLI/DAG 使用的稳定 ID，`title`、`subtitle` 和 `description` 是页面内容。

Dashboard 只引用 Workspace Adapter 的逻辑名称，不保存账号密码。内置数据入口包括本地文件、DuckDB、MySQL、StarRocks 和可信 Python Source。

## 文档

- [设计与架构不变量](DESIGN.md)
- [当前计划与验收状态](plan.md)
- [代码实现索引](docs/product-architecture.md)
- [版本与发布流程](docs/versioning-and-release.md)
- [AI 开发效率评测协议](docs/authoring-evaluation.md)
- [变更记录](CHANGELOG.md)

项目尚未添加正式 `LICENSE` 文件；在许可证补齐前，公开可见不等于已经授予再分发或商用权利。

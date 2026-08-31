# Dataviz

**让 AI 快速搭建可靠的 Dashboard，也能直接发现、执行和复用 Dashboard 背后的分析数据。**

Dataviz 是一个 workspace-first、AI-friendly 的本地数据看板工具。Dashboard 以普通文件保存，可以进入 Git、复制和审查；人类在浏览器中查询、交互和阅读，AI 通过 CLI 获取当前版本的最小开发契约、复用已有数据口径并继续分析。

## 它解决什么问题

传统的 AI Dashboard 工作通常止于页面：

```text
AI 写 SQL / Python / HTML → 人类看图 → 数据和分析逻辑被封在页面里
```

Dataviz 将 Dashboard 同时变成人类界面和 AI 分析空间：

```text
Workspace → Query Parameter → Source → Transform → Named Output
                                                    ├─→ View → 人类看图与交互
                                                    └─→ Catalog / CLI → AI 查数与分析
```

它重点解决两件事：

1. **AI 友好地开发 Dashboard**

   AI 不需要先阅读完整 Runtime，也不必每次从零生成网页。它可以按任务获取最小文档和 Scaffold，编写普通文件，再通过静态校验、真实执行和浏览器检查完成闭环。

2. **AI 直接复用 Dashboard 的分析能力**

   Dashboard 不是只能截图识别的交付终点。AI 可以搜索已有数据口径，查看参数和依赖，执行 Source、Output 或 View，并在不可变 Result 上继续分页查看、导出和沉淀 Evidence。

## 设计理念

- **Workspace 是事实来源**：Dashboard、Source、Transform 和 Presentation 都是可审查文件；Catalog 只是可重建索引。
- **人和 AI 共用一套执行语义**：Server、CLI、HTML 和 Browser Runtime 共用 Dependency Contract 与 Named Output。
- **复杂度下沉到框架**：作者关心业务问题、数据口径、Controls、Views 和布局；依赖图、状态事务、缓存和 Renderer 生命周期由 Compiler/Runtime 管理。
- **渐进披露**：简单 Dashboard 只读取最小路径；需要交互计算或 Custom Renderer 时才展开对应契约。
- **结果可复查**：CLI 执行产生不可变 Result；后续查看和导出不重复昂贵查询。
- **分析优先**：Plotly 是统一图表接口，TanStack Table 是默认表格内核；工具选择不应分散作者对数据口径和分析问题的注意力。

## 安装

要求 Python 3.11–3.14，推荐 Python 3.12。

从源码安装：

```bash
git clone https://github.com/AdolHong/dataviz.git
cd dataviz
uv sync --python 3.12 --extra dev --no-editable \
  --reinstall-package ai-dataviz
uv run --no-editable dataviz version
```

从发行 ZIP 安装：

```bash
python -m pip install ./ai-dataviz-<version>.zip
dataviz version
```

源码环境运行下文命令时，可将 `dataviz` 替换为 `uv run --no-editable dataviz`。

需要真实浏览器视觉检查时，安装可选依赖：

```bash
pip install "ai-dataviz[visual-check]"
python -m playwright install chromium
```

## Quickstart：启动 Dashboard

创建 Workspace 并启动 Server：

```bash
dataviz init myworkspace
dataviz serve myworkspace --port 8080
```

打开 <http://127.0.0.1:8080>。

让 AI 新建或修改 Dashboard 时，从安装包自带的最小文档开始：

```bash
dataviz docs --task minimal --format json
dataviz scaffold minimal --id sales-overview --output sales-workspace
dataviz validate sales-workspace --dashboard sales-overview --strict
dataviz report sales-workspace sales-overview --output report.html
dataviz visual-check sales-workspace sales-overview --target both
```

只有任务确实需要 Query 后交互或自定义渲染时，才改用 `interactive` 或 `custom-renderer` 文档与 Scaffold。

## Quickstart：让 AI 查数和分析

先搜索 Workspace 中已有的数据口径：

```bash
dataviz catalog search myworkspace '收入|利润'
dataviz catalog describe myworkspace 'sales::source:orders/main'
```

执行目标并封存不可变 Result：

```bash
dataviz run myworkspace 'sales::source:orders/main' \
  --query-param region=华东
```

之后直接读取 Result，不重新执行查询：

```bash
dataviz result show myworkspace result_... --offset 0 --limit 100
dataviz result inspect myworkspace result_...
dataviz result export myworkspace result_... \
  'sales::source:orders/main' --to ./exported-output
```

`result export` 复制 Result 中的原生 Artifact，不重新执行查询，也不转换文件格式。

典型 AI 工作流是：

```text
docs / scaffold → validate → run → report / visual-check
catalog search → catalog describe → run → result show
```

## 下一步阅读

- [Dataviz AI Skill](dataviz-skill.md)：AI 如何开发、分析、复用和长期维护 Dashboard
- [设计与架构不变量](DESIGN.md)：完整产品设计与 Runtime 契约
- [当前实施计划](plan.md)：尚未完成的工作与发布门禁
- [渐进式作者入口](docs/progressive-authoring.md)：minimal、interactive、custom-renderer
- [AI Analysis Plane](docs/analysis-plane.md)：Catalog、Target、Result、Overlay、Evidence
- [Dashboard 视觉语言](docs/design-language.md)：默认视觉与 Presentation 边界
- [版本与发布流程](docs/versioning-and-release.md)
- [变更记录](CHANGELOG.md)

当前项目处于 `0.x` 阶段，只接受现行严格 Schema。Server 默认仅监听本机且不提供内建账号体系；远程使用需要放在可信网络或外部访问控制之后。

项目尚未添加正式 `LICENSE` 文件；公开可见不等于已经授予再分发或商用权利。

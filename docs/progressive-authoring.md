# 渐进式作者入口

Dataviz 不再把完整 Runtime 架构作为每次开发的起点。CLI 先根据任务返回最小概念闭包；只有需求越过当前层级时，作者或 AI 才继续读取下一层契约。

## 分层任务路径

| 路径 | 何时使用 | 当前层级披露的主链 |
| --- | --- | --- |
| `minimal` | 普通声明式看板 | Adapter → Source → View → Layout |
| `interactive` | Query 后需要选择、计算或局部失效 | minimal + Control → Interactive Transform → Named Output |
| `custom-renderer` | 内置 View 无法表达所需视觉 | minimal + Renderer Contract 与生命周期 |
| `cascading-selection` | 父选择改变下游候选域 | minimal + Option Domain + `depends_on` |
| `view-filter` | 一个 Selection 直接筛选一个 View | minimal + View-scoped Selection |
| `browser-compute` | 控件驱动浏览器端派生计算 | minimal + Compute + browser-js + Named Output |

`minimal` 是默认入口。它不会把 Control、Interactive Transform 或 Custom Renderer 的内部概念混入简单看板文档。`interactive` 与 `custom-renderer` 都从 minimal 继承，但彼此不强制继承：写一个 Custom Renderer 不代表必须同时理解 Controls。

## 机器可读路由

按任务读取：

```bash
dataviz docs --task minimal --format json
dataviz docs --task interactive --format json
dataviz docs --task custom-renderer --format json
dataviz docs --task cascading-selection --format json
dataviz docs --task view-filter --format json
dataviz docs --task browser-compute --format json
```

已经知道组件时，可以让 CLI 自动选择最小路径：

```bash
dataviz docs --component view.table --format json
dataviz docs --component control.select --format json
dataviz docs --component view.custom --format json
```

返回的 `dataviz/authoring-route/v1` 包含 `closure`、`concepts`、`documents`、`scaffolds`、`commands` 与 `excluded_concepts`。调用方不需要解析自然语言来判断下一份文档。

## 完整 Scaffold profiles

三个 profile 都会生成一个可直接运行的 Workspace，而不是等待人工拼接的 YAML 片段：

```bash
dataviz scaffold minimal --id sales --output ./sales-workspace
dataviz scaffold interactive --id explorer --output ./explorer-workspace
dataviz scaffold custom-renderer --id special-view --output ./renderer-workspace
```

`dataviz scaffold --list --format json` 返回 `dataviz/scaffold-catalog/v2`。每个 recipe 都声明：

- `route`：它属于哪一层作者能力；
- `scope`：完整 `workspace` 或可组合的 `fragment`；
- profile 清单和默认 profile。

单个 Scaffold payload 还提供固定验证链：

```text
validate → report → visual-check
```

三条 profile 路径分别执行这条链。文档回归同时检查每份文档的 `requires` 都属于当前路由闭包，避免 minimal 文档悄悄引用未披露的高级概念。

`visual-check` 是可选的真实浏览器能力，首次使用前安装独立 extra 和 Chromium：

```bash
pip install "ai-dataviz[visual-check]"
python -m playwright install chromium
```

Linux 精简环境可使用 `python -m playwright install --with-deps chromium` 一并安装系统库。

## 与 focused context 的分工

任务路由回答“这类工作最少需要理解什么”；`dataviz inspect context --focus` 回答“这个既有 Dashboard 的目标组件真实依赖什么”。新建任务先选 route，修改既有看板再读取具体 focus。两者不会用估算 Token 代替真实评测。

真实 Dataviz / standalone HTML 成对试验仍按独立评测计划执行。在相同模型、客户端、权限和时间预算下积累重复 trial 之前，不发布 Token 节省、首次成功率或耗时结论。

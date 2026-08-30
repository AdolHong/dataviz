# Dataviz 视觉语言

这份规范面向人和 AI。它约束普通 Dashboard 的默认气质，也说明何时可以偏离默认样式。

机器可读版本始终随安装包发布：

```bash
dataviz docs design-language --format json
dataviz components show theme.business --format json
dataviz components gallery --output component-gallery.html
```

## 1. 默认方向

Dataviz 的默认方向是 **Quiet white shell + clean analytical canvas**：稳定的产品外壳与默认画布使用连续白色表面，不再把 Header、Sidebar、Workbench 和 Canvas 各自做成一张强调卡片。Dashboard 先帮助用户理解分析对象和结论，再暴露参数、计算和诊断细节。

- Server 与导出 HTML Header、Sidebar 和 Workbench 默认使用白色；只有极浅分割线表达导航与内容边界，它们不跟随 Dashboard Theme 染色。导出 HTML 的 Header 保留紧凑 Dataviz 标识以说明报告来源，但不复制 Server 导航、Reload 和诊断操作。
- Dashboard 默认使用 `business` 的白色画布、白色分析面板和靛蓝分析强调，也可以独立选择 `plain`、`editorial` 或 `terminal`。
- Shell 中只有主操作与活动导航使用靛蓝强调；绿色只表达 Ready、成功或正向语义，不能同时承担普通选中态。
- 黄色表达 Stale/Warning，红色表达 Error/破坏性操作。
- 留白是主要层级手段；边框只做结构提示，阴影近乎不可见，不靠大面积色块、渐变或粗边框制造重点。
- Sidebar 默认 250px，可拖拽调整；目录和 Dashboard 名称保持单行，截断后才显示完整名称 Tooltip，不能用换行扰乱导航节奏。

默认使用 `theme.preset: business`。`plain`、`editorial` 和 `terminal` 是完整的替代语法，不应在同一页面中随意混搭。

## 2. 信息先于装饰

页面层级应回答四个问题：

| 层级 | 应回答的问题 | 不应该出现的内容 |
| --- | --- | --- |
| Dashboard | 正在分析什么、什么范围、为了什么决策 | Run ID、Source ID、框架说明 |
| Section | 这一组 View 回答哪个问题 | 与 Dashboard 重复的大标题 |
| View | 这里展示什么、应该怎样阅读 | 无上下文的“趋势图”“明细表” |
| Header / View 状态灯 | Header 看取数层；View 只在活动或失败时显示自身依赖与 Renderer；悬停看名称，点击依赖节点看证据 | 一个长期占位的 Pipeline 大按钮，或每个 View 常驻一排绿色灯 |

标题、subtitle 和 description 是分析内容，不是装饰。Query Parameter 或 Control 决定当前分析对象时，应通过内容插值让上下文可见，而不是要求用户重新打开参数面板确认。

Server Header 横跨整个屏幕：左侧的 Dataviz Logo/品牌名同时是 Sidebar disclosure，后接 Source/Dataset 状态灯；右侧依次放 SHARE、Dashboard Controls，最右侧是“查询 + ▼”分段按钮。SHARE 的临时菜单只显示“分享链接”和“导出 HTML”，不附加解释小字；包含 Server Python Interactive Transform 时“导出 HTML”禁用。Sidebar 与 Workbench 都从 Header 下方开始，不再显示独立 Navigation 按钮或重复的 Dashboards 标题。查询主按钮执行 Query，箭头整体显示或隐藏 Workbench 顶部、正常文档流中的圆角 Query Card；不新增独立 Parameters 按钮。Card 首行只写“查询参数”，不放运行按钮；字段按“标题在上、输入在下”排列，不补参数数量或说明文案。Query Card 与 Canvas 共用 `clamp(22px, 3vw, 48px)` 水平 gutter。Server 默认展开，导出 HTML 默认折叠；展开推动 Canvas，不覆盖内容。Dashboard/Section/View Controls 使用临时浮层，并遵循外部点击与 `Esc` 关闭语义。Controls 托盘只呈现业务字段标签与组件；DATA/LOGIC、Selection/Compute、作用域和影响 View 数量属于 Runtime 诊断信息，不作为默认视觉层级。Query Pipeline 不再占用操作位：Source/Dataset 节点在 Dataviz 品牌右侧对应状态灯，悬停只显示任务名，点击进入完整证据。View 的依赖节点和 Renderer 灯位于 `PLOTLY / TABLE / PERSPECTIVE` 标签左侧，仅在运行、过期或失败时出现，完成后消失；导出 HTML 不重复展示已固化为 Ready 的 Source 灯。

一个 Section 应回答一个问题，并且至多有一个主要 View。其余 View 是解释、比较或明细，应降低视觉重量。

## 3. 语义 Token

自定义样式应先覆盖 Token，再覆盖组件内部结构。

Shell 与 Dashboard 使用两组边界明确的 Token：`--dv-shell-*` 只控制固定导航、Header、Query/Controls 工具区；`--dv-*` 控制 Dashboard、Section、View、图表与表格。Dashboard CSS 不应重写 Shell Token，避免不同画布切换时导航和操作位置忽明忽暗。

### Stable shell

- `--dv-shell-bg`：白色 Header、工具栏与 Query 托盘背景。
- `--dv-shell-surface`：按钮、弹层与字段表面。
- `--dv-shell-line`：低对比边框。
- `--dv-shell-ink` / `--dv-shell-muted`：Shell 主次文字。
- `--dv-shell-accent` / `--dv-shell-soft`：活动导航、Control 类型与轻强调。
- `--dv-shell-shadow`：工具栏的低阴影。

### Surface

- `--dv-paper`：页面背景。
- `--dv-panel`：卡片、表格与图表表面。
- `--dv-overlay-surface`：弹层表面，必须不透明。
- `--dv-soft`：弱强调背景。
- `--dv-soft-blue`：信息或上下文背景。

### Content

- `--dv-ink`：主要文字。
- `--dv-muted`：说明、元数据和次要文字。
- `--dv-line`：边框、分隔线和图表网格基线。

### Semantic color

- `--dv-accent`：主要操作、活动状态和第一图表序列。
- `--dv-accent-strong`：高层标题和强强调。
- `--dv-green`：Ready、Selection 和正向语义。
- `--dv-amber`：Stale、Warning 和 Cancelled。
- `--dv-red`：Error 和破坏性操作。
- `--dv-blue`：信息状态。
- `--dv-chart-1` 至 `--dv-chart-8`：默认图表序列。

状态色不能作为无意义的装饰色，否则用户会误解页面状态。同一业务维度跨 View 应保持同色。

### Shape, depth and type

- `--dv-radius`、`--dv-radius-sm`：面板与控件圆角。
- `--dv-shadow`：静态面板的低阴影。
- `--dv-shadow-float`：弹层的浮动阴影。
- `--dv-font-sans`：标题、正文和数据阅读。
- `--dv-font-mono`：短标签、状态、技术元数据；不要用于长正文。

## 4. 空间与布局

- 以 4px 为最小节奏，常用间距为 8/12/18/24/32px。
- 优先使用 12 列语义布局：`12`、`8+4`、`6+6`、`4+4+4`。
- 默认密度为 `comfortable`；监控页面可用 `compact`，叙事报告可用 `spacious`。
- 不通过缩小字体容纳更多内容；先折叠次要信息或改变 Section 结构。
- 图表设置可读的 `min_height`；Table/Perspective 随容器增长，不固定整个页面高度。
- 窄屏必须回落为单列，不能产生页面级横向滚动。

默认布局是文档流。Dataviz 不使用 Mosaic 或固定坐标作为通用布局协议；特殊构图可以使用局部 CSS 或完整 Canvas，但必须保留稳定 View host 和 Runtime 行为。

## 5. 组件规则

### Chart

- 先选择正确的数据编码，再选择视觉样式。
- 保持主题字体、网格和 palette，除非颜色本身承载稳定业务语义。
- 优先使用位置、长度、直接标签和小倍图完成比较。
- 避免 3D、彩虹色、厚重阴影和多个同时争夺注意力的图表风格。
- Plotly 是唯一的作者图表接口。普通图表先用声明式模板，通过 `options.trace`、`options.layout` 与 `config` 覆盖；涉及自定义 trace、函数、事件或命令式交互时使用 Custom Renderer，不为了留在模板层而牺牲表达能力。
- 视觉选型先明确要回答的分析问题，再参考 [Plotly JavaScript 官方文档](https://plotly.com/javascript/) 与 [Chart Studio Gallery](https://plotly.com/graphing-libraries/)。Dataviz Recipe 只是经过验证的起步代码，不是独立图表目录，也不限制作者使用官方 API。
- 页面滚动优先于图表滚轮手势。Custom Renderer 默认使用 `context.charts.plotly`，由平台统一 Theme、Resize、Update 与 Dispose；需要完整底层能力时可以直接调用页面内嵌的 Plotly API，但必须自行承担这些策略。

### Table 与 Perspective

- Table 是默认的数据表达组件，应优先完成明细、排行、对账、分组展示、格式化输出和行选择；不要仅因为默认 Table 能力不足就切换到分析工作台。
- Table 使用本地固定的 `@tanstack/table-core` 作为 headless 行为内核；声明式 View 自动获得默认 Dataviz DOM/CSS，可信 Custom Renderer 可通过 `context.tables.tanstack` 使用托管生命周期或完整 Core 自定义任意 header、cell、footer、feature 与样式。
- Perspective 只用于明确需要赋予终端用户临时分组、聚合、透视和多维探索能力的场景，不作为普通数据表的升级版或默认替代品。
- 数字右对齐，文本左对齐；表头、条纹和 hover 使用低对比。
- 默认 Table 保持克制的 Dataviz DOM/CSS；高级作者必须能替换 header、cell、footer、交互与样式，而不是被默认外观封死。
- Perspective 拥有自己的内部 UI。只调整外层容器和语义 Token，不覆盖其 Shadow DOM 或交互结构。
- 内部滚动只在容器仍可滚动时消费滚轮；到达边界后必须把滚轮交还页面。

### Data Entry Component 与 Control

- 最多四个短单选可使用 `radio-group`；它只包含真实选项，不生成 All/Clear。
- 更多选项使用支持搜索/虚拟列表的 `select`。
- 层级数据使用 `cascader` 或 `tree-select`，让叶子保留父级上下文。
- 单个日期使用 `date-picker`；日期范围使用一个弹层协同编辑起止日期的 `range-picker`。
- `checkbox` 表示随外层流程提交的布尔值；`switch` 表示立即反馈的布尔切换。
- 弹层必须不透明、保持在视口内，并支持点击外部和 Escape 关闭。
- Presentation 可以改变 Component 与密度，不能改变 Query/Selection/Compute 语义、级联或 canonical value。

## 6. 自定义顺序

始终从成本最低、边界最稳定的一层开始：

```text
默认声明式页面
  → Layout / Section / View / Data Entry Component
  → Theme 字段
  → Token + 稳定 css_class
  → 单个自定义 Renderer
  → 完整 Canvas
```

示例 `presentation.yaml`：

```yaml
schema: dataviz/presentation/v2
kind: presentation
dashboard: sales-overview

theme:
  preset: business
  accent: "#3451b2"
  density: comfortable

layout:
  template: overview
  gap: 18

sections:
  performance:
    template: chart-and-table

views:
  revenue-trend:
    span: 8
    min_height: 380
    container: chart
    css_class: insight-primary
  sales-detail:
    span: 4
    container: table

assets:
  css: [assets/presentation.css]
```

Dashboard 自有 CSS：

```css
/* 先改变语义 Token。 */
.dv-canvas {
  --dv-accent: #3451b2;
  --dv-accent-strong: #1f2f78;
  --dv-chart-1: #3451b2;
  --dv-chart-2: #23867b;
}

/* 再通过稳定 css_class 做局部强调。 */
.dv-view.insight-primary {
  border-top: 3px solid var(--dv-accent);
}
```

不要在每个 View 中复制一套字体、卡片、颜色和弹层 CSS；不要用全局 `*`、任意高 `z-index`、透明弹层、固定页面高度或嵌套滚动锁覆盖 Runtime 行为。

## 7. AI 工作流

1. 读取 `dataviz inspect context` 和相关 Component contract。
2. 选择一个清晰方向；没有明确品牌需求时沿用 `business`。
3. 先写 Presentation YAML，再写最少量 Dashboard 自有 CSS。
4. 运行 `dataviz validate`。
5. 在 Gallery、真实数据和窄视口下检查 Ready/Empty/Error、弹层和滚动。
6. 确认 Server 与导出 HTML 一致，Plotly/Table/Perspective 都继承 Token。

## 8. 完成标准

- 首屏只通过状态灯了解 Pipeline 健康度；需要时点击具体节点查看证据。
- 页面只有一个主要强调色，状态色保持语义。
- Dashboard、Section、View 标题不重复，脱离上下文仍能理解。
- 弹层不透明、不越过视口，点击外部与 Escape 可以关闭。
- 窄屏没有页面级水平溢出。
- Table/Perspective 不无条件截获页面滚轮。
- 删除自定义 CSS 后，Dashboard 仍能回退为完整可用的声明式页面。

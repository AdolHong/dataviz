# Dataviz 视觉语言

这份规范面向人和 AI。它约束普通 Dashboard 的默认气质，也说明何时可以偏离默认样式。

机器可读版本始终随安装包发布：

```bash
dataviz docs design-language --format json
dataviz components theme.business --format json
dataviz gallery --output component-gallery.html
```

## 1. 默认方向

Dataviz 的默认方向是 **Modern indigo analytical workbench**：冷静、清晰、可信，先帮助用户理解分析对象和结论，再暴露参数、计算和诊断细节。

- 冷灰页面承载白色分析面板。
- 靛蓝建立品牌、标题和主要操作层级。
- 绿色表达数据选择、Ready 或正向语义。
- 黄色表达 Stale/Warning，红色表达 Error/破坏性操作。
- 低阴影、清晰边框和留白承担层级，不靠大面积渐变或装饰制造重点。

默认使用 `theme.preset: business`。`plain`、`editorial` 和 `terminal` 是完整的替代语法，不应在同一页面中随意混搭。

## 2. 信息先于装饰

页面层级应回答四个问题：

| 层级 | 应回答的问题 | 不应该出现的内容 |
| --- | --- | --- |
| Dashboard | 正在分析什么、什么范围、为了什么决策 | Run ID、Source ID、框架说明 |
| Section | 这一组 View 回答哪个问题 | 与 Dashboard 重复的大标题 |
| View | 这里展示什么、应该怎样阅读 | 无上下文的“趋势图”“明细表” |
| Pipeline/Details | 数据从哪里来、SQL 如何解析、哪里失败 | 抢占主画布的诊断细节 |

标题、subtitle 和 description 是分析内容，不是装饰。Query Parameter 或 Control 决定当前分析对象时，应通过内容插值让上下文可见，而不是要求用户重新打开参数面板确认。

Query Parameters 默认作为 Header 的内联第二行展开，让首次进入页面的用户先确认取数范围；`Run query` 旁的箭头是唯一的开合入口。展开会推动 Canvas，而不是覆盖内容。Dashboard/Section/View Controls 和 Pipeline 才使用临时浮层，并遵循外部点击与 `Esc` 关闭语义。

一个 Section 应回答一个问题，并且至多有一个主要 View。其余 View 是解释、比较或明细，应降低视觉重量。

## 3. 语义 Token

自定义样式应先覆盖 Token，再覆盖组件内部结构。

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
- 页面滚动优先于图表滚轮手势。内置 Plotly 模板默认 `scrollZoom: false`；Custom Renderer 直接调用 `Plotly.newPlot`/`Plotly.react` 时也必须传入该默认值。只有用户明确要求图内滚轮缩放时才能设为 `true`。

### Table 与 Perspective

- 普通 Table 用于可定制阅读；Perspective 用于排序、筛选和透视探索。
- 数字右对齐，文本左对齐；表头、条纹和 hover 使用低对比。
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
schema: dataviz/presentation/v1
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

1. 读取 `dataviz context` 和相关 Component contract。
2. 选择一个清晰方向；没有明确品牌需求时沿用 `business`。
3. 先写 Presentation YAML，再写最少量 Dashboard 自有 CSS。
4. 运行 `dataviz validate`。
5. 在 Gallery、真实数据和窄视口下检查 Ready/Empty/Error、弹层和滚动。
6. 确认 Server 与导出 HTML 一致，Plotly/ECharts/Table/Perspective 都继承 Token。

## 8. 完成标准

- 首屏无需打开 Pipeline 即可知道分析对象、范围和主要结论。
- 页面只有一个主要强调色，状态色保持语义。
- Dashboard、Section、View 标题不重复，脱离上下文仍能理解。
- 弹层不透明、不越过视口，点击外部与 Escape 可以关闭。
- 窄屏没有页面级水平溢出。
- Table/Perspective 不无条件截获页面滚轮。
- 删除自定义 CSS 后，Dashboard 仍能回退为完整可用的声明式页面。

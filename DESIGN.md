---
name: Dataviz
description: A quiet analytical workbench for building, operating, and reviewing reliable dashboards.
colors:
  paper: "#ffffff"
  ink: "#1f2521"
  shell-ink: "#27322d"
  action-ink: "#25282d"
  line: "#e6e9e5"
  muted: "#747a74"
  instrument-indigo: "#4451a3"
  instrument-indigo-strong: "#26306f"
  indigo-mist: "#eef0f8"
  canvas-haze: "#f5f6fb"
  verified-green: "#2f8f64"
  warning-amber: "#b8872f"
  diagnostic-red: "#c94f43"
  information-blue: "#4d78a8"
  chart-teal: "#2f8f83"
  chart-gold: "#d29a3a"
  chart-coral: "#cf6658"
  chart-violet: "#7464a8"
typography:
  display:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", Roboto, Helvetica, Arial, sans-serif'
    fontSize: "clamp(34px, 4.8vw, 64px)"
    fontWeight: 720
    lineHeight: 1.02
    letterSpacing: "-0.035em"
  title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", Roboto, Helvetica, Arial, sans-serif'
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", Roboto, Helvetica, Arial, sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: '"SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace'
    fontSize: "10px"
    fontWeight: 650
    lineHeight: 1.4
    letterSpacing: "0.09em"
rounded:
  xs: "5px"
  control: "7px"
  sm: "8px"
  surface: "12px"
  query: "16px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
  canvas: "48px"
components:
  button-primary:
    backgroundColor: "{colors.action-ink}"
    textColor: "{colors.paper}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "42px"
    width: "122px"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.shell-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "0 14px"
    height: "40px"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 11px"
    height: "42px"
  chip-selected:
    backgroundColor: "{colors.indigo-mist}"
    textColor: "{colors.instrument-indigo-strong}"
    typography: "{typography.body}"
    rounded: "{rounded.xs}"
    padding: "6px 9px"
  card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
    padding: "16px"
  query-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.shell-ink}"
    rounded: "{rounded.query}"
    padding: "18px"
---

# Design System: Dataviz

## Overview

**Creative North Star: “安静的分析工作台”**

Dataviz 应该像一张经过整理的专业分析桌面：工具随手可取，状态清楚可辨，但数据和分析问题始终占据视觉中心。它不通过装饰制造“高级感”，而通过稳定的层级、精确的间距、清楚的状态和克制的反馈建立可信度。

这套系统采用低噪声白色工作区、炭黑文本、有限的靛蓝交互强调，以及只承担状态语义的绿色。页面在静止时近乎平坦；只有下拉框、对话框、Inspector 和拖动预览等临时层明显离开画布。等宽字体用于微标签、技术状态和可复制标识，正文与业务数据保持高可读性的系统无衬线字体。

视觉工作台必须忠实反映 canonical 分析路径。Draft、运行中状态和预览不得伪装成 immutable Result；Server 与导出 HTML 可以拥有不同外层操作，但同一 Dashboard 的字体、Controls、View 和状态语义必须一致。作者工作台固定文案使用英文，Dashboard 内容语言由作者决定。

**Key Characteristics:**

- 安静、精确、内容优先；
- 白色连续工作区配合极细分隔线；
- 靛蓝表示交互与选择，绿色表示确认与健康状态；
- 常驻表面平坦，临时浮层才产生明显纵深；
- 系统无衬线负责阅读，等宽字体负责机器感和元信息。

## Colors

色彩是一套受控的功能语言：中性色建立工作区，靛蓝指示操作焦点，绿色与暖色只报告状态，图表色用于区分数据系列而不接管界面层级。主题变体可以改变具体色值，但必须保持这些语义角色。

### Primary

- **仪器靛蓝 Instrument Indigo** (`#4451a3`)：活动选择、焦点、交互提示和默认第一图表系列。它是稀缺的操作信号，不是大面积品牌底色。
- **深仪器靛蓝 Deep Instrument Indigo** (`#26306f`)：强调态、深色标识和需要更高对比度的靛蓝状态。
- **靛蓝薄雾 Indigo Mist** (`#eef0f8`)：活动导航、选择 Chip 和轻量交互区域。

### Secondary and Status

- **验证绿 Verified Green** (`#2f8f64`)：成功、已同步、可用、确认和健康状态；不承担页面主操作。
- **信息蓝 Information Blue** (`#4d78a8`)：中性信息状态和次级数据语义。
- **警示琥珀 Warning Amber** (`#b8872f`)：stale、outdated、需要注意但仍可继续的状态。
- **诊断红 Diagnostic Red** (`#c94f43`)：失败、危险或明确错误。
- **图表青绿、金色、珊瑚和紫色** (`#2f8f83`, `#d29a3a`, `#cf6658`, `#7464a8`)：只用于系列区分和数据编码。

### Neutral

- **工作纸 Paper** (`#ffffff`)：页面、面板、卡片和输入的默认背景。
- **分析墨 Ink** (`#1f2521`)：Dashboard 主文字和标题。
- **工作台炭灰 Shell Ink** (`#27322d`)：应用 Shell 文字和图标。
- **操作炭黑 Action Ink** (`#25282d`)：主要执行按钮。
- **发丝线 Hairline** (`#e6e9e5`)：边框、分隔线和结构界面。
- **静音灰 Muted** (`#747a74`)：说明、次级标签和低优先级信息。
- **画布薄雾 Canvas Haze** (`#f5f6fb`)：轻量状态背景和局部层级分区。

**The Assigned Color Rule.** 靛蓝只负责交互与选择，绿色只负责确认与状态，炭黑只负责主要执行。不要让三者在同一层级竞争主导权。

**The Quiet Canvas Rule.** 大部分屏幕必须保持中性；强调色应通过稀缺性产生意义，而不是通过面积产生声量。

## Typography

**Display and Body:** 系统无衬线字体栈，优先 Apple system、Segoe UI 与 PingFang SC。
**Label and Mono:** SFMono-Regular、Consolas、Liberation Mono、Menlo。

无衬线字体让中英文业务内容保持自然、快速和稳定；等宽字体提供轻微的仪器感，用于坐标、状态、微标签和技术证据。两者分工明确，不追求装饰性字体搭配。

- **Display**（720，`clamp(34px, 4.8vw, 64px)`，1.02）：完整报告或 Dashboard 的唯一主标题。
- **Headline**（720，28–34px，约 1.08）：Inspector、Dialog 或高层功能标题。
- **Title**（700，16px，1.3）：View、卡片和局部分析模块标题。
- **Body**（400，14px，1.45）：说明、字段值与常规操作内容；长说明控制在约 68ch。
- **Label**（650，10px，0.09em，常为大写）：Eyebrow、状态、类型、来源和机器标识。
- **Metric**（720，`clamp(42px, 6vw, 78px)`，0.95）：主指标值；Band 布局缩为 `clamp(34px, 4vw, 58px)`。

**The Two Voices Rule.** 人读的内容使用系统无衬线；机器状态和元信息使用等宽字体。不要用等宽字体书写长句，也不要把正文全部大写。

## Layout

Server 使用可调整并可折叠的导航 Rail、58px 粘性 Topbar 和可伸展工作区组成作者工作台。桌面端 Rail 基准宽度为 250px；Dashboard Canvas 使用 `clamp(22px, 3vw, 48px)` 的响应式内边距。内容按声明式网格排列，常规间隙只从 4/8/12/16/24/32/48px 节奏中选择。

页面层级从 Shell 到 Dashboard 再到 Section/View 逐级收敛。Shell 导航保持紧凑，Dashboard 标题和分析叙事拥有更宽松的呼吸空间，View 内部恢复高密度读取。不要用额外嵌套卡片表达本可由间距或 Hairline 说明的关系。

Query Parameters 在首次运行前作为正文中的全宽卡片展开；成功运行后折叠，由 Header 的 Run/Query 组合重新打开。Controls 布局必须尊重每个子组件的最小可用宽度，并在可用空间内形成有界网格；不能为了填满容器而把每个字段无限拉长。

宽 Table 的横向位置是用户上下文。排序或局部刷新必须保留 `scrollLeft`、焦点和当前排序列，不能在数据更新后跳回第一列。长明细默认留在正常文档流；当产品提供折叠或临时查看入口时，关闭后必须释放占位，并保留清楚、可恢复的标题入口。

1180px 以下允许 Topbar 操作换行；980px 以下 Rail 转为移动布局；800px 以下 Section 网格改为单列；720px 以下 Controls 与 Inspector 收敛；520px 以下进一步压缩操作密度。移动端优先保持顺序和可操作性，不机械缩小桌面界面。

## Elevation & Depth

系统以平坦表面和发丝线作为默认结构。View Card 使用近乎不可见的环境阴影（`0 1px 2px rgba(26,35,29,.035), 0 5px 16px rgba(26,35,29,.03)`）；Query Card 使用略宽但仍克制的阴影；Popover、Dialog 和 Inspector 使用 `0 18px 48px rgba(26,35,29,.12)` 的 Operational Float。

拖动预览属于直接操纵层：使用白色表面、1px 边框与 `0 14px 34px rgba(32,36,43,.18)`，但不使用过渡或追随动画。它必须紧跟指针；源位置改为虚线占位，让“正在移动什么”和“原来在哪里”同时可见。

**The Flat-at-Rest Rule.** 常驻内容平坦，临时交互抬升。不要给每个容器增加相同强度的阴影。

## Shapes

Dataviz 使用温和但精确的圆角：微元素 5px，输入与按钮 7px，紧凑容器和导航项 8px，主要 View 与 Popover 12px，Query Card 16px。圆角表达可操作边界和层级连续性，不用于制造柔软、玩具化的气质。

状态点、计数和小型胶囊可以使用 `999px`；主要操作、卡片和面板不能变成胶囊。边框通常为 1px Hairline，活动态优先改变背景和窄指示线，不使用厚重的单侧 Accent Border。

## Components

### Buttons and Header Actions

- **Run:** 炭黑底、白字、42px 高；主文字区域固定为 122px 并居中。是否带折叠箭头只增加独立尾部区域，不能挤压或改变 RUN 的宽度。
- **Secondary/Ghost:** 白色或透明背景、炭灰文字；Hover 进入轻中性背景。
- **Focus:** 所有键盘入口使用靛蓝半透明 Focus Ring，不能只依赖颜色变暗。
- **Language:** 作者 Shell 使用 `RUN`、`DASHBOARD CONTROLS` 等固定英文；业务按钮由 Dashboard 作者决定。

### Inputs and Selection Controls

- 单行 Input、Input Number、Select、Date Picker 与 Date Range 共用 42px 外框高度。复合控件由外框拥有边框和圆角，内部原生 Input 不再绘制第二层矩形。
- Date Range 的两端日期必须使用可收缩但不截断的布局；日历按钮是独立的尾部区域。
- Multiple Select 默认提供 Select all 与 Revert。摘要表达有效选择而非内部存储模式：不超过 `max_tag_count`（默认 2）时显示具体值，不超过 20 项时显示“已选 N 项”，更大集合只在排除侧更短时显示“全部，排除 N 项”。具体值使用轻靛蓝 Chip，过长文本省略并通过展开列表或 Tooltip 查看全文。
- 字符计数不默认显示；只有作者明确设置长度约束且计数能帮助完成输入时才出现。
- Remote Select 必须区分搜索词、当前候选、已选值、unavailable 状态和 generation。Lookup 返回后，打开的列表必须立即更新；旧请求不得覆盖新请求。

### Query Parameters

- 首次进入且尚无成功 Result 时在正文展开；成功查询后自动折叠，不复制第二份常驻参数摘要。
- 状态 Chip 必须准确显示 `Not applied`、`Applied`、`Unsaved changes`、`Outdated` 或失败；编辑中的 Draft 不能伪装成 Result 已采用的参数。
- 动态候选使用 Dashboard-owned 候选物化；查询、级联、搜索与分页共享同一 immutable generation，不在每次交互时重新执行远端 SQL。
- 多选只保存 `all/include/exclude/none` 和必要 operands，不展开完整候选池。搜索与分页使用 generation-bound opaque cursor，generation 变化后不得复用旧 cursor。
- Revert 恢复 committed snapshot；Clear 与 None/All 的业务含义由 canonical state 和查询映射决定，不能从空数组猜测。

### Navigation and Direct Manipulation

- Sidebar Dashboard 行的任意非交互区域都可拖动；不显示六点拖动手柄。按下后超过小阈值才进入拖动，普通点击仍负责导航。
- 拖动中使用紧跟指针、零过渡的浮动预览；源行变为虚线占位。Folder 目标显示 `DROP HERE`，底部根目录目标显示 `MOVE TO TOP LEVEL`；导航空白区域也可作为根目录投放区。
- 参数编辑器属于高密度排序界面，Parameter Card 和 Choice Row 保留显式六点句柄。拖动与上下箭头是互补的鼠标/键盘路径；默认项复选框不兼任拖动入口。
- Active Navigation 使用 Indigo Mist、深靛蓝文字和 3px 窄指示线，不使用强阴影。

### View, Table, and Metric

- View Header 由业务标题、可选说明和右侧类型/状态微标签组成。图表、Table、Metric 和空状态共享同一 12px 容器语言。
- Table 排序在原位更新，保留横向滚动、焦点和排序状态。列多时优先横向浏览，不压缩到不可读宽度。
- Metric 主值与单位在同一基线上；一个必要的比例、变化或辅助量使用 `secondary` 行。单位不得孤立在卡片左下角，Secondary 不得与主值争夺层级。
- Plotly `options.layout` 只允许完整的 `{{ parameters.<id> }}` token 读取最近一次 RUN 的 typed Query Parameter。未解析 token 必须在 validate 阶段以精确路径失败，不能原样泄漏给 Plotly。

### Cards, Popovers, and Inspector

- 常驻 Card 使用白底、1px Hairline、12px 圆角和 Ambient Surface；嵌套结构优先使用留白与分隔线。
- Query Card 使用 16px 圆角，但内部 Controls 仍遵循统一 42px 几何。
- Popover 使用白色工作台语言与 Operational Float；点击宿主外部（包括 Dashboard 正文）应关闭。
- 深色 Inspector 是作者诊断面的例外：深墨背景、绿色技术标签和等宽代码区明确表示“进入系统内部”，但仍沿用同一间距、圆角和状态语义。

## Do's and Don'ts

### Do

- **Do** 让分析问题、指标和异常首先被看见，操作控件退居其后。
- **Do** 使用既有间距、圆角和 42px 控件几何组织密度。
- **Do** 为键盘操作保留清楚的 `:focus-visible` 状态和等价操作路径。
- **Do** 让 Server 与导出 HTML 复用相同的 Dashboard 字体、颜色、Controls 和 View 容器语言。
- **Do** 区分空数据、等待、失败、stale 和未应用 Draft，并说明发生了什么。
- **Do** 让拖动、排序、折叠和异步搜索保留用户当前的视觉上下文。

### Don't

- **Don't** 在同一操作层级同时使用靛蓝、绿色和炭黑作为主按钮色。
- **Don't** 用大面积渐变、装饰性网格、光晕、厚重阴影或粗单侧边框掩盖信息层级。
- **Don't** 把每个 Section、View 和字段都包进新的 Card。
- **Don't** 用等宽字体书写长段业务说明或把所有标签强制全大写。
- **Don't** 依赖颜色独自表达错误、选择或可用性。
- **Don't** 把 Draft、Preview 或 Runtime 临时状态描述成已封存 Result。
- **Don't** 为某个 Dashboard 的局部风格破坏 Shell、Controls 和导出页之间的一致性。

---
name: Dataviz
description: A quiet analytical workbench for building, operating, and reviewing reliable dashboards.
protocolBaseline:
  - dataviz/dashboard/v20
  - dataviz/parameter-domain/v2
  - dataviz/parameter-domain-contract/v3
  - dataviz/parameter-lookup/v1
  - dataviz/parameter-materialization/v1
  - dataviz/presentation/v2
  - dataviz/source/v6
  - dataviz/dataset-transform/v3
  - dataviz/interactive-transform/v4
  - dataviz/dependency-contract/v13
  - dataviz/layout-contract/v1
  - dataviz/state-snapshot/v6
  - dataviz/runtime/v15
  - dataviz/analysis-result/v5
  - dataviz/analysis-evidence/v5
  - dataviz/dashboard-bundle/v2
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
    padding: "11px 16px"
    height: "36px"
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
    height: "36px"
  chip-selected:
    backgroundColor: "{colors.instrument-indigo}"
    textColor: "{colors.paper}"
    typography: "{typography.body}"
    rounded: "{rounded.xs}"
    padding: "6px 9px"
  card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
    padding: "16px"
---

# Design System: Dataviz

## Overview

**Creative North Star: "安静的分析工作台"**

Dataviz 应该像一张经过整理的专业分析桌面：工具随手可取，状态清楚可辨，但数据和分析问题始终占据视觉中心。它不通过装饰制造“高级感”，而通过稳定的层级、精确的间距、清楚的状态和克制的反馈建立可信度。

这套系统采用低噪声白色工作区、炭黑文本、有限的靛蓝交互强调，以及只承担状态语义的绿色。页面在静止时近乎平坦；只有下拉框、对话框、Inspector 等临时浮层明显离开画布。等宽字体用于微标签、技术状态和可复制标识，正文与业务数据保持高可读性的系统无衬线字体。

**Key Characteristics:**

- 安静、精确、内容优先；
- 白色连续工作区配合极细分隔线；
- 靛蓝表示交互与选择，绿色表示确认与健康状态；
- 常驻表面平坦，临时浮层才产生明显纵深；
- 系统无衬线负责阅读，等宽字体负责机器感和元信息。

## Colors

色彩是一套受控的功能语言：中性色建立工作区，靛蓝指示操作焦点，绿色与暖色只报告状态，图表色用于区分数据系列而不接管界面层级。

### Primary

- **仪器靛蓝 Instrument Indigo** (`#4451a3`)：活动选择、焦点、交互提示和默认第一图表系列。它是稀缺的操作信号，不是大面积品牌底色。
- **深仪器靛蓝 Deep Instrument Indigo** (`#26306f`)：强调态、深色标识和需要更高对比度的靛蓝状态。
- **靛蓝薄雾 Indigo Mist** (`#eef0f8`)：活动导航、轻量选择区域和靛蓝内容的低对比背景。

### Secondary

- **验证绿 Verified Green** (`#2f8f64`)：成功、已同步、可用、确认和健康状态。它不承担页面主操作。
- **信息蓝 Information Blue** (`#4d78a8`)：中性信息状态和次级数据语义。

### Tertiary

- **警示琥珀 Warning Amber** (`#b8872f`)：stale、需要注意但仍可继续的状态。
- **诊断红 Diagnostic Red** (`#c94f43`)：失败、危险或明确错误。
- **图表青绿、金色、珊瑚和紫色** (`#2f8f83`, `#d29a3a`, `#cf6658`, `#7464a8`)：仅用于系列区分和数据编码。

### Neutral

- **工作纸 Paper** (`#ffffff`)：页面、面板、卡片和输入的默认背景。
- **分析墨 Ink** (`#1f2521`)：Dashboard 主文字和标题。
- **工作台炭灰 Shell Ink** (`#27322d`)：应用 Shell 文字和图标。
- **操作炭黑 Action Ink** (`#25282d`)：主要执行按钮。
- **发丝线 Hairline** (`#e6e9e5`)：边框、分隔线和结构界面。
- **静音灰 Muted** (`#747a74`)：说明、次级标签和低优先级信息。
- **画布薄雾 Canvas Haze** (`#f5f6fb`)：轻量状态背景和局部层级分区。

### Named Rules

**The Assigned Color Rule.** 靛蓝只负责交互与选择，绿色只负责确认与状态，炭黑只负责主要执行。不要让三者在同一层级竞争主导权。

**The Quiet Canvas Rule.** 大部分屏幕必须保持中性；强调色应通过稀缺性产生意义，而不是通过面积产生声量。

## Typography

**Display Font:** 系统无衬线字体栈（优先使用 Apple system / Segoe UI / PingFang SC）  
**Body Font:** 同一系统无衬线字体栈  
**Label/Mono Font:** SFMono-Regular、Consolas、Liberation Mono、Menlo

**Character:** 无衬线字体让中英文业务内容保持自然、快速和稳定；等宽字体提供轻微的仪器感，用于坐标、状态、微标签和技术证据。二者分工明确，不追求装饰性字体搭配。

### Hierarchy

- **Display**（720，`clamp(34px, 4.8vw, 64px)`，1.02）：完整报告或 Dashboard 的主标题；仅一处成为页面锚点。
- **Headline**（720，约 28–34px，约 1.08）：Inspector、对话框或高层功能标题。
- **Title**（700，16px，1.3）：View、卡片和局部分析模块标题。
- **Body**（400，14px，1.45）：说明、字段值与常规操作内容；长说明控制在约 68ch。
- **Label**（650，10px，0.09em，通常大写）：Eyebrow、状态、类型、来源和机器标识。

### Named Rules

**The Two Voices Rule.** 人读的内容使用系统无衬线；机器状态和元信息使用等宽字体。不要用等宽字体书写长句，也不要把正文全大写。

## Layout

Server 使用固定导航 Rail、粘性 Topbar 和可伸展工作区组成 Operate 模式的应用 Shell。桌面端 Rail 基准宽度为 250px，Topbar 高度约 58px；Dashboard Canvas 使用 `clamp(22px, 3vw, 48px)` 的响应式内边距。内容按声明式网格排列，常规间隙以 12、16、24px 为主，不用任意像素制造局部节奏。

页面层级从 Shell 到 Dashboard 再到 Section/View 逐级收敛。Shell 导航保持紧凑，Dashboard 标题和分析叙事拥有更宽松的呼吸空间，View 内部再恢复高密度读取。不要用额外嵌套卡片表达本可由间距或分隔线说明的关系。

1180px 以下允许 Topbar 操作换行；980px 以下 Rail 转为移动布局；720px 以下 Controls、Inspector 和网格收为单列或双列；520px 以下进一步压缩操作密度。移动端优先保持可操作性和内容顺序，不机械缩小桌面界面。

## Elevation & Depth

系统以平坦表面和发丝线作为默认结构。View Card 只使用近乎不可见的环境阴影（`0 1px 2px rgba(26,35,29,.035), 0 5px 16px rgba(26,35,29,.03)`）；它不应看起来悬浮。Popover、Dialog、Inspector 和临时菜单使用更明确的浮层阴影（`0 18px 48px rgba(26,35,29,.12)`），让遮挡关系无需额外装饰即可理解。

### Shadow Vocabulary

- **Ambient Surface**：极轻的双层阴影，仅帮助白色 View 与白色 Canvas 分离。
- **Operational Float**：18px–48px 的柔和阴影，用于短暂覆盖工作区的交互层。

### Named Rules

**The Flat-at-Rest Rule.** 常驻内容平坦，临时交互抬升。不要给每个容器增加相同强度的阴影。

## Shapes

Dataviz 使用温和但精确的圆角：小图标和微元素约 5px，输入与按钮 7px，局部容器 8px，主要 View 与 Popover 12px。圆角用于表达可操作边界和层级连续性，不用于制造柔软、玩具化的气质。

状态点、计数和小型胶囊可以使用 `999px`；主要操作、卡片和面板不能变成胶囊。边框通常为 1px 的 Hairline，活动态优先改变背景与局部指示线，而不是全面加粗边框。

## Components

### Buttons

- **Shape:** 7px 圆角，紧凑高度约 36px；文字保持清楚而非夸张。
- **Primary:** 操作炭黑背景、白字、`11px 16px` 内边距，用于 Run/Query 等明确执行动作。
- **Hover / Focus:** Hover 变为更深炭黑；键盘 Focus 使用靛蓝半透明环，不能只依赖颜色变暗。
- **Secondary / Ghost:** 白色或透明背景、炭灰文字；Hover 进入 `#f4f5f4`，不与 Primary 争夺注意力。

### Chips

- **Style:** 默认白底 Hairline 边框；选中后使用仪器靛蓝背景和白字。
- **State:** “全部”作为集合语义时可使用浅绿确认样式；普通选择不要借用绿色。

### Cards / Containers

- **Corner Style:** 主要 View 12px，紧凑配置容器 8px。
- **Background:** 默认工作纸白，不使用渐变。
- **Shadow Strategy:** 常驻 Card 使用 Ambient Surface；嵌套结构优先用分隔线和留白。
- **Border:** 1px Hairline。
- **Internal Padding:** 通常 16–24px；图表绘图区可由 Renderer 单独控制。

### Inputs / Fields

- **Style:** 白底、1px Hairline、7px 圆角、约 36px 高；标签位于字段上方。
- **Focus:** 边框切换为仪器靛蓝，并出现低透明度 Focus Ring。
- **Error / Disabled:** 错误使用诊断红并给出文字原因；禁用态降低对比度但仍保持内容可读。
- **Remote Select:** 搜索、分页、当前选择和 unavailable 状态必须视觉可分；打开状态中的候选变化应即时重绘。

### Query Parameters

- **First Run:** 有 Query Parameters 且尚无成功 Result 时，参数区在正文流中展开，不藏入临时浮层。
- **After Run:** 成功查询后自动折叠；Header 中的 Run/Query 控件负责重新展开，不额外复制一份常驻参数摘要。
- **Evidence:** 参数区始终投影 canonical draft/commit 关系：`Not applied`、`Applied`、`Unsaved changes`、`Outdated` 或失败状态。编辑后的 draft 不能伪装成当前 Result 已使用的参数；Revert 恢复 committed snapshot。
- **Domain Ownership:** 动态候选使用 Dashboard-owned 候选物化；同一 Dashboard 的查询、级联与分页共享 immutable generation，不在每次交互时重新执行远端 SQL。
- **Compact State:** 多选只保存 `all/include/exclude/none` 与必要 operands，不展开“全选”的完整候选池。搜索和 cursor 分页使用 generation-bound opaque cursor，刷新或 generation 变化后不得继续复用旧 cursor。
- **Field Geometry:** Query Panel 中的单行 Input、Input Number、Select、Date Picker 与 Date Range 共用 42px 外框高度；复合控件由外框拥有尺寸，内部 input 只填满容器，不得用自身 min-height 撑高同行。
- **Language:** Server 作者工作台的固定 Shell、诊断和编辑器文案使用英文；Dashboard 标题、说明、字段和业务标签由作者决定语言。

### Navigation

Rail 使用紧凑纵向列表和等宽分组标签。默认项为静音灰文字；Hover 进入浅中性背景；Active 使用 Indigo Mist、深靛蓝文字和一条窄靛蓝指示线。活动项不使用强阴影或大面积饱和色。

### View / Analysis Card

View Header 由业务标题、可选说明和右侧类型/状态微标签组成。标题负责回答“这是什么”，状态标签只表达实现或运行事实。图表、Table 和空状态共享相同容器语言，避免不同 Renderer 看起来属于不同产品。

Metric 的主值和短单位必须在同一基线上成为一个阅读单元，不把“件”“%”孤立到卡片角落。`label` 只承担可选说明；一个必要的比例、变化或辅助量使用克制的 `secondary` 行，不能与主值争夺层级。Band Section 自动采用较紧凑的数值尺度；作者不通过尺寸 DSL 逐卡修补几何。

Plotly 的 `options.layout` 只允许完整的 `{{ parameters.<id> }}` token 读取最近一次 RUN 的 typed Query Parameter，用于参考线、参考区间和轴范围。它不是通用模板环境：不得拼接文本、执行表达式、读取 Control，或扩张到 trace/config；无法解析的嵌套值必须在 validate 阶段以精确路径失败，不能原样泄漏给 Plotly。

### Popover / Inspector

Popover 保持白色工作台语言并使用 Operational Float。深色 Inspector 是作者诊断面的例外：它通过深墨背景、绿色技术标签和等宽代码区明确表示“进入系统内部”，但仍沿用同一间距、圆角和状态语义。

## Do's and Don'ts

### Do:

- **Do** 让分析问题、指标和异常首先被看见，操作控件退居其后。
- **Do** 使用 4/8/12/16/24/32/48px 的既有节奏组织密度。
- **Do** 为键盘操作保留清楚的 `:focus-visible` 状态。
- **Do** 让 Server 与导出 HTML 复用相同的 Dashboard 字体、颜色、Controls 和 View 容器语言。
- **Do** 用靛蓝表示选择，用绿色表示确认，用琥珀和红色表示风险等级。
- **Do** 在空数据、等待和失败之间给出明确而不同的状态说明。

### Don't:

- **Don't** 在同一操作层级同时使用靛蓝、绿色和炭黑作为主按钮色。
- **Don't** 用大面积渐变、装饰性光晕或厚重阴影掩盖信息层级。
- **Don't** 把每个 Section、View 和字段都包进新的 Card。
- **Don't** 用等宽字体书写长段业务说明或把所有标签强制全大写。
- **Don't** 依赖颜色独自表达错误、选择或可用性。
- **Don't** 为某个 Dashboard 的局部风格破坏 Shell、Controls 和导出页之间的一致性。

## Product Interaction Contract

Dataviz 的视觉工作台服务于同一条 canonical 分析路径，不能在界面中发明第二套执行语义：AI 或作者先用 `catalog search` 找到可能的 Target，再用 `catalog describe` 确认输入、输出和依赖，最后执行 Run。执行中的状态可以被观察，但只有 immutable Result 才是可引用的分析事实；成功完成以 `run_succeeded` 事件进入证据链。

编辑器、Inspector 和空状态应使用这组既有术语，不展示已删除的 CLI alias，也不把预览、草稿或 Runtime 临时状态描述成已封存 Result。

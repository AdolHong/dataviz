---
name: Dataviz
description: A quiet analytical workbench for building, operating, and reviewing reliable dashboards.
currentProtocolBaseline: "dataviz/dashboard/v20; dataviz/parameter-domain/v2; dataviz/parameter-domain-contract/v3; dataviz/parameter-lookup/v1; dataviz/parameter-materialization/v1; dataviz/presentation/v2; dataviz/source/v6; dataviz/dataset-transform/v3; dataviz/interactive-transform/v4; dataviz/dependency-contract/v13; dataviz/layout-contract/v1; dataviz/state-snapshot/v6; dataviz/runtime/v15; dataviz/analysis-result/v5; dataviz/analysis-evidence/v5; dataviz/dashboard-bundle/v2"
currentCliContract: "catalog search → catalog describe → run → run_succeeded → result/evidence"
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

2026-09-10 局部记录：多 Page 的截图暴露了导航名、Dashboard 标题、Page 名与 Page 大标题重复竞争的问题。下文将现状与待实现方向分开记录；这次文档合并不代表界面已修复，也不改变现有颜色、字体和组件 token。

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

多 Page 是 Dashboard 内可选的分析入口，不要求把内部数据结构的每一层都变成可见标题。当前重复层级与拟议的收敛方式见 Components 下的「Multi-Page Navigation and Titles」；不要据此为普通单页看板增加 Page 包装或导航。

工作树已将 Query Parameters 与 Dashboard Controls 接入可开关、可切换内容的右侧操作面板，详见下方组件约定。原来的正文展开、成功后自动折叠是旧布局，不再作为 Server 工作台行为。颜色、字体与控件 token 不变，不新增 DSL；独立报告不受此次迁移影响。

右侧面板展开时，宽屏工作区为它让出空间；窄屏采用覆盖式抽屉，不把图表挤成不可读的窄列。关闭后归还占位。面板内部单列组织表单，标题与关闭入口固定，表单独立滚动；不要再嵌套一张 Query Card。面板宽度与切换断点在实现时按 Date Range、长选项和最小可读图表宽度验证，暂不编造固定数值。Controls 仍尊重每个子组件的最小可用宽度，不能为填满容器无限拉长。

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
- Multiple Select 与多选 Cascader 不提供 Revert。未搜索时提供 Select all / Clear；搜索时改为 Select results / Clear results，仅修改匹配项，保留搜索外选择；Clear 遵守允许空值策略。摘要表达有效选择而非内部存储模式：不超过 `max_tag_count`（默认 2）时显示具体值，不超过 20 项时显示“已选 N 项”，更大集合只在排除侧更短时显示“全部，排除 N 项”。具体值使用轻靛蓝 Chip，过长文本省略并通过展开列表或 Tooltip 查看全文。
- 字符计数不默认显示；只有作者明确设置长度约束且计数能帮助完成输入时才出现。
- Remote Select 必须区分搜索词、当前候选、已选值、unavailable 状态和 generation。Lookup 返回后，打开的列表必须立即更新；旧请求不得覆盖新请求。

### Query Parameters

- Server 使用右侧面板，行为见下一节；不复制第二份常驻参数摘要或独立表单状态。
- 状态 Chip 必须准确显示 `Not applied`、`Applied`、`Unsaved changes`、`Outdated` 或失败；编辑中的 Draft 不能伪装成 Result 已采用的参数。
- 动态候选使用 Dashboard-owned 候选物化；查询、级联、搜索与分页共享同一 immutable generation，不在每次交互时重新执行远端 SQL。
- 多选只保存 `all/include/exclude/none` 和必要 operands，不展开完整候选池。搜索与分页使用 generation-bound opaque cursor，generation 变化后不得复用旧 cursor。
- Revert 恢复 committed snapshot；Clear 与 None/All 的业务含义由 canonical state 和查询映射决定，不能从空数组猜测。

### Right-Side Query / Control Panel

- Header 的 Shortcuts、Share、Controls、Parameters、Run 统一 12px / 600 无衬线字体与正常字间距，不强制全大写。Run 仅通过主按钮底色突出；禁用态不改变字体规格。

**当前约束（0.24.5）：** 复用现有表单，支持 W/E 切换与关闭、Esc、宽屏停靠与窄屏覆盖。验证结果与发行状态以 plan.md 为准。

- 同一右侧区域只有 `closed`、`query`、`controls` 三种展示状态。W 打开 Parameters，再按 W 关闭；E 打开 Controls，再按 E 关闭。从另一种内容切入时直接替换，不并排打开两个面板。
- Header 始终保留 `Parameters` / `Controls` 入口和展开状态，不显示字母快捷键徽标；无对应字段时置灰、不可点击，不隐藏按钮或改变排列。按 W/E 遇到无字段时统一显示无参数提示，不打开空面板、不触发查询。单页与多 Page 使用相同操作，不要求作者新增 Page 或布局 DSL。
- 快捷键仅在非编辑场景处理：Input、Textarea、Select、contenteditable、搜索框、代码编辑器、中文组合输入期间不拦截；仅响应明确列出的组合键，不抢占其他 Ctrl/Meta/Alt 组合键，不响应按住键产生的重复事件。单字符快捷键需可关闭或限定到工作台焦点范围，不能只为鼠标用户设计。
- Esc 优先关闭当前下拉框、日历或更上层对话框；没有内层浮层时才关闭面板。面板有显式关闭按钮，关闭后焦点回到发起入口。宽屏面板非模态，不锁住正文焦点；窄屏覆盖抽屉管理焦点并阻止背景误操作。
- Parameters 保持 Draft / Applied 证据，修改后需 Run；仅保留 Header Run 与快捷键，不在面板底部重复按钮或分割线。Controls 即时生效，不提供 Run 或冗余说明文案。所有查询入口复用同一提交动作，不能产生第二套状态。
- 独立 HTML 报告不提供 Run 或 Share，也不列出运行查询、切换工作台 Sidebar 的快捷键；查询参数入口只展示已固化的取数证据，不伪装成可重新查库的表单。
- 独立 HTML 的 Header Parameters/Controls 点击与 W/E 共用右侧栏开关：同项关闭、不同项切换、Esc 关闭；不再保留正文参数卡片或 Dashboard Controls 弹窗入口。查询证据只移动展示位置，不复制状态、不执行 Query；显式 Section/View Popover 覆盖继续遵守既有约定。
- 打开、关闭、切换面板不提交查询、不重置控件、不取消正在执行的 Run。保留草稿、已提交参数、Control canonical state；重开可查看查询使用的参数及与当前草稿的区别。
- 首次无已应用结果且存在 Query Parameters 时自动展开 Parameters；查询完成后不强制关闭，由用户决定是否继续调参。此条取代旧布局的“成功后自动折叠”。
- 切换 Dashboard / Page 时展示当前目标的字段与状态；旧请求不得覆盖新面板，不混用各页 Draft / Applied。没有对应面板内容时关闭，不显示上一页字段；导航不能等待候选初始化才能响应。
- Section / View Controls 的入口保留在对应内容附近，默认进入上下文侧栏；显式 popover 覆盖与祖先层级组合见下节。
- 视觉沿用白底、克制的结构分隔、42px 控件几何和既有焦点样式；宽屏停靠面板不使用浮层重阴影。布局改变后通知图表 resize，避免逐帧驱动昂贵重绘；尊重 reduced-motion。

**验收：** W/W、E/E、W/E/Esc；输入与中文组合输入不误触；面板关开不丢草稿、不新增 Query；查询中关闭再打开；Dashboard / Page 快速切换；下拉框内 Esc 只关闭一层；窄屏焦点与关闭入口；Date Range 全日期、长多选摘要及最后一项字段不裁切。首次展开与查询后保留必须分别验证。

#### Unified panel width

**状态：2026-09-11，0.24.3 本地发行。** 同时覆盖 Query Parameters 与 Dashboard / Section / View Controls 的右侧面板，不重新设计已确认的交互或视觉语言。桌面、窄屏与日期范围已核对；三浏览器完整测试及 WebKit 间歇性初始化超时见 plan.md，完整缩放矩阵尚未执行。

**调整依据：** 原面板固定 390px，左右内距各 20px；Controls 字段另受默认约 280px 内容宽度限制，Query 表单也保留组件列宽约束。标题线已延伸至面板内容区右缘，但输入框仍提前结束，留下额外空白。因此协调面板与字段两层宽度，而不是只缩小外壳或只拉长分割线。Checkbox / Radio 选项很少时自然留下空白，不属于必须填满的缺陷。

**统一宽度方案：**

- 0.24.5 收紧至 320px，移除 Parameters 侧栏底部重复 Run 与分割线；仅保留 Header Run 和快捷键。窄屏关闭抽屉后可点击 Header Run，编辑草稿不丢失。
- 以 **320px 外宽、左右各 16px 内距、约 288px 可用内容宽度**作为实现起点，最终需用真实日期范围、长选项和缩放验收。按 CSS 像素定义，不根据截图的物理像素推算；边框与滚动条计入实际可用宽度。
- W/E 及各层 Controls 共用同一宽度来源；标题、字段区域、分割线保持对齐。切换面板、切换 Section/View、候选加载或选中项变化均不改变外宽，不以测量当前文字来自动伸缩面板。
- 右侧面板里的 Input、Input Number、Select、Multiple Select、Date Picker、Date Range 使用整行可用宽度。解除面板内部重复的 280px 字段上限与旧固定列宽；不全局改动原位表单或 Popover 的宽度规则。
- Checkbox / Radio 选项自然排列并按可用宽度换行，不均分拉伸、不扩大点击项之间的空隙。长标签可换行；Select 摘要保留既有省略与查看全文机制，不以标签长度撑宽侧栏。
- 日期范围必须显示两端完整日期及日历入口，不能以缩小字号或隐藏字符换取紧凑。若真实字体、缩放和控件尾部占位证明 288px 内容区不足，应统一修订 W/E 基准宽度，不给 Query 再造一个独立宽度。
- 宽屏继续停靠；窄屏沿用覆盖抽屉，宽度不超过可用视口，手机仍以 320px 为上限，小于 320px 时适应视口。此轮不新增拖动调宽、按控件自动扩宽、双列表单或 DSL 字段。独立 HTML 已有的右侧 Controls 使用相同规则；不因此将只读 Query 证据改造成另一套编辑面板。
- 保留 42px 输入框高度、层级间 56px 留白、现有层级颜色与标题线，以及 E/同入口收起、不同入口切换、显式 Popover 等已确认行为。

**实施验收：** 同时检查 W/E、单层与三层 Controls、桌面/窄屏/手机、浏览器 100%/125%/200% 缩放；覆盖长中英文标题、少量 Checkbox、长多选摘要、日期范围、滚动条与最后一个字段。断言输入外框右缘与标题线右缘对齐，内容不横向溢出、日期不裁切，W/E 切换宽度稳定；正文图表正确 resize，焦点、草稿和 canonical 状态不变，打开或调整展示不新增 Query。此处为待执行验收，不是测试通过记录。

### Contextual Controls

**状态：2026-09-11，0.24.1 本地发行。** 延续现有右侧操作面板；不改变颜色、字体、控件几何、Control 作用域或计算契约。本文使用现有术语 Section（用户描述中的 sector）。Presentation 默认入口为 `control_panels.section/view.placement`，单对象覆盖为 `sections/views.<id>.controls.placement`。

**The Context Path Rule.** 面板只展示当前入口的祖先链，不展示整个 Dashboard 的控件目录；展示在一起不意味着新增依赖、继承值或扩大过滤范围。

| 打开入口 | Sidebar 中从上到下的内容 |
| --- | --- |
| Dashboard Controls | 当前 Page 上下文中的 Dashboard Controls |
| Section A 的 Controls | Dashboard → Section A |
| Section A / View X 的 Controls | Dashboard → Section A → View X |
| Section A / View Y 的 Controls | Dashboard → Section A → View Y；不保留 X 的表单 |

这里 View 入口包含两级局部上下文（Section、View）及公共 Dashboard 层，最多三组。无控件的组不渲染，也不留下空分隔线；当前对象归属仍由标题说明。View 没有所属 Section 时不虚构一层。

#### Visual hierarchy and access

- 面板标题始终使用 `Controls`，包括只显示 Dashboard 的状态；Dashboard 使用与局部层级相同的真实分组标题与间距，不随上下文切换改变位置。Dashboard / Section / View 是同一行上的轻量作用域标识，Section / View 的实际名称使用 14px 正文级标题，避免将技术前缀与名称拼成一整段粗体。业务名称保留作者语言，长名称可换行。
- 2026-09-11 用户追加确认（0.24.1 打包后的工作树调整）：移除组间横线，改为标题后紧接一条 1px 细线，延伸至面板内容区右侧；组内 12px、组间 56px 留白（按用户要求由 28px 翻倍）。三个作用域标识分别使用浅靛蓝、浅绿、浅沙色，深色文字；颜色仅辅助区分作用域，不表示状态，也不铺满整组。各组单列、同一背景，不嵌套卡片、树形缩进或三级 Tab，也不默认增加折叠操作。
- 每层标识文字、后面的实际名称及标题细线使用相同层级前景色：Dashboard `#3f4983`、Section `#365e4a`、View `#77572c`。参数名称、输入值和控件不继承该颜色。
- Section / View 原位保留 Controls 按钮，作为发现入口与关闭后的焦点返回位置。只点击 Controls 入口才切换面板上下文；点击图表、选择数据点、滚动页面不自动抢占面板。
- 切换目标后让被点击的组标题及第一个字段进入面板可视区，必要时只滚动面板，不移动正文；父级组仍可向上滚动查看。数据更新不得反复抢焦点或滚回顶部。

#### Presentation defaults and overrides

- Dashboard 的 Presentation 可分别设置 Section Controls、View Controls 的默认展示方式：`popover` 或 `sidebar`。0.24.2 起未配置默认 sidebar；popover 保留为偶尔需要弹窗时的显式选择。
- 单个 Section / View 可以覆盖自身展示方式；省略即继承对应类型的 Dashboard 默认。解析顺序为「本对象覆盖 → Dashboard 对应类型默认 → sidebar」。不再增加含义重叠的“是否弹窗”布尔字段。
- Section 的展示覆盖不传播给子 View；子 View 仍使用自己的覆盖或 Dashboard 的 View 默认。这样“某个 Section 用弹窗”不会悄悄改变它下面全部 View 的入口。
- 展示方式只作用于被点击入口。View 选择 sidebar 时，其祖先 Controls 一起进入面板，即使祖先自身入口配置为 popover；popover 则只展示被点击对象自身的 Controls，不塞入完整祖先链。
- 控件只有一份 canonical 状态，但允许 Popover 与 Sidebar 同时展示并双向同步；不能把两份表单当成独立状态。用户明确确认：打开局部 Popover 不关闭右侧面板。

#### Switching, focus, and lifecycle

- 右侧已展开时，点击不同 Section/View Controls 更新祖先上下文；若原来显示 Query Parameters，则切换到 Controls 并保留 Query 草稿。同一 Sidebar 入口再次点击收起；“同一”按当前目标对象判断，不按面板内是否包含祖先组判断。
- 右侧隐藏时，Popover 入口只开弹窗，不展开侧栏；Sidebar 入口展开侧栏。Popover 自身仍可再次点击关闭，但这不改变侧栏展开状态。关闭侧栏使用 X/Esc，不逐级“返回”，不新增返回栈。
- C 或 Header Dashboard Controls 在右侧已显示任何 Controls 上下文时直接收起，不先返回 Dashboard 层；从 Query 切换保留其草稿。没有 Dashboard Controls 时，C 仍可收起已打开的局部 Controls；侧栏隐藏时则提示无参数，不猜测打开哪个 Section/View。Popover 入口重复点击只开关弹窗，不收起侧栏。
- Esc 先关闭 Select/日历等内层浮层，再关闭侧栏。宽屏不自动聚焦关闭按钮；键盘打开时将焦点置于目标组标题或首个可操作字段，窄屏沿用模态抽屉的焦点约束。关闭返回当前入口，入口被移除时退回最近有效位置。
- 控件变更按已有依赖图传播；打开、关掉、切换展示位置不提交 Control、不查库、不重置选择，也不重挂载无关 View。共享祖先组更新时不得丢失正在编辑的焦点、搜索文本或未提交输入。
- 切换 Dashboard/Page、目标 View 被移除或不可见时清除失效的局部上下文，不留旧页面字段。异步初始化只更新当前目标，不阻塞其他入口；无候选、加载中、失败分别按既有控件状态呈现。

#### Standalone reports and verification

- 独立 HTML 应复用同一展示方式与上下文规则，但不引入工作台导航 Rail、Run 或 Share；Query Parameters 仍是只读证据。仅导出当前报告实际包含的 Section/View，不引用其他 Page。
- 打印时去掉侧栏、浮层和操作入口，不打印空白占位；沿用报告已有参数证据，不把全部控件表单摊进正文。
- 实施验收：同 Section 两个 View 来回切换、跨 Section 切换、空祖先组、没有 Dashboard Controls、混合 popover/sidebar 默认与覆盖、W/E/Esc、快速点击与迟到响应、控件更新后状态一致、跨 Page 清理、长表单目标组可见、宽窄屏焦点及图表 resize、独立 HTML 同行为。断言无额外 Query、无重复 Control commit、无兄弟 View 表单泄漏。

### Navigation and Direct Manipulation

- Sidebar Dashboard 行的任意非交互区域都可拖动；不显示六点拖动手柄。按下后超过小阈值才进入拖动，普通点击仍负责导航。
- 拖动中使用紧跟指针、零过渡的浮动预览；源行变为虚线占位。Folder 目标显示 `DROP HERE`，底部根目录目标显示 `MOVE TO TOP LEVEL`；导航空白区域也可作为根目录投放区。
- 参数编辑器属于高密度排序界面，Parameter Card 和 Choice Row 保留显式六点句柄。拖动与上下箭头是互补的鼠标/键盘路径；默认项复选框不兼任拖动入口。
- Active Navigation 使用 Indigo Mist、深靛蓝文字和 3px 窄指示线，不使用强阴影。

### Multi-Page Navigation and Titles

**状态：基础层级收敛已在工作树实现，未重新打包。** 原问题依据 0.23.0 多 Page 示例
截图记录。当前已修复被未闭合注释吞掉的页签 CSS；Server 多页保留一个 Dashboard
主标题，隐藏嵌入 Canvas 的重复标题与标识，保留说明；独立报告不受影响。运行前仅保留
操作提示。切入窄屏默认收起 Sidebar，页签更新保留键盘焦点。Chrome 两项专项及相关
非浏览器检查通过；以下方向未被本轮覆盖的长文案、跨引擎等场景仍需后续验收。

**修复前观察：** Sidebar 显示 `holiday`，正文另显示 Dashboard 标题；其下两个 Page 按钮
与 Canvas 内的大号 Page 标题重复。运行前的空状态再次占用大标题区域，导致分析内容
被推远。截图中的 Page 按钮呈浏览器原生外观；虽然源码有导航样式，仍不能仅凭 CSS
存在就视为视觉验收通过。窄屏还观察到 Sidebar 遮挡内容，属于另一个待修复边界。

**设计方向与验收约束：**

- Sidebar 名称用于定位 Dashboard，不必与正文标题使用同等字号，也不自动改写作者命名。
- 多页正文保留一次 Dashboard 主标题；紧接一行轻量 Page 页签，以当前页样式与键盘焦点
  区分选择。示例可用「品类对比」「跨年对比」，这是作者命名建议，不是运行时自动截短规则。
- 页签承担 Page 名称，不在其下方或 Canvas 内再重复一个大号 Page 标题。需要解释分析
  范围时保留一处简短 Page 说明；阅读顺序为标题 → 页签/说明 → 参数 → 图表。
- 首次未运行只显示一条简短操作提示，不为提示重新建一块标题区或大卡片。运行成功后
  仍可展开参数面板查看 applied 参数；不能为了减少重复而删掉参数证据或状态反馈。
- 收敛仅作用于有完整导航上下文的 Server 多页工作台。独立导出的单页报告仍保留 Page
  标题、必要的 Dashboard 归属和说明；不能全局删除 Canvas 标题，导致报告失去身份。
- 普通单页继续只有自己的标题与参数，不显示页签；显式仅一个 Page 也不增加无用导航。
- 长页名应有可访问的完整名称，窄屏允许页签横向浏览；Sidebar 不应遮挡主内容。页签
  重绘或后台状态更新不得吞掉焦点，也不能只靠颜色表达当前页。

**后续验收：** 同时检查运行前/后、两页切换、普通单页、独立报告和窄屏；不仅断言点击
可用，还要检查可见标题是否重复、内容对齐、页签实际样式及键盘焦点。切页不自动查询、
draft/applied 独立、历史恢复等既有行为不能因层级收敛而改变。实施状态以上方记录为准。

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

### Keyboard mapping (0.24.4)

Header 入口与右侧面板标题统一使用 `Parameters` / `Controls`，快捷键帮助和无障碍操作名称同步；Dashboard / Section / View 层级标签保留，内部 Query Parameter / Control 概念及 DSL 不变。

默认启用单键：Q 左侧 Sidebar、W Query Parameters、E Controls、R Run。帮助弹窗可关闭单键；关闭后使用 Cmd+Ctrl+Q/W/E/R。组合键始终可用，运行另支持 Cmd/Ctrl+Enter 与 Ctrl+End。Esc 和 ? 保留，? 不受单键开关影响。输入、组合输入、重复按键不触发单键操作。帮助弹窗按开关显示当前映射，Header 不显示旧字母徽标。导出 HTML 仅提供 W/E、Esc、?，不提供 Run 或左侧工作台 Sidebar。

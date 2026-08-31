# Data Entry Component 语义契约

Dataviz 把三个问题彻底分开：

1. `dashboard.yaml` 定义值是什么；Query Parameter 创建 Query Run，scoped Control 持有查询后的交互状态。
2. Control 所在位置定义作用域：Dashboard、Section 或 View。
3. `presentation.yaml` 只选择如何编辑这个值：`control.input`、`control.select`、`control.cascader` 等。

因此，Control 契约始终由两个正交字段组成：

- `type` 描述输入形态：`single_input | multiple_input | single_select | multiple_select | range_input`。
- `value_type` 描述每个原子值：`text | integer | number | boolean | date`。

例如，单日期是 `single_input/date`，日期范围是 `range_input/date`，整数 Slider 是 `single_input/integer`，双端浮点 Slider 是 `range_input/number`。同一个 `single_input/boolean` 可以显示成 Checkbox 或 Switch，但它的默认值、校验、作用域和依赖关系不会被 CSS 或 Component 改写。

## 为什么不直接依赖 Ant Design

组件边界、值形状、状态和交互语义逐项参考 [Ant Design Data Entry](https://ant.design/components/overview/)；当前 Runtime 不加载 React 或 Ant Design 包。这样 Server 页面、导出的单 HTML、离线报告和自定义 Canvas 可以共用同一套轻量 Runtime，也不会为了一个输入框打包完整 React 运行时。

这不是“看起来像 Ant Design”就算完成。每个 `control.*` Package 都必须在 `manifest.yaml` 中声明：

- 对齐的 Ant Design Component 与官方文档；
- 已采用的语义；
- 有意省略的能力；
- logic fields、presentation options、semantic DOM、tokens、Story 和 Test。

## 已实现组件

| Dataviz | 对齐对象 | Value contract | 关键语义 |
|---|---|---|---|
| `control.input` | [Input](https://ant.design/components/input/) | `single_input/text` | 单行或 TextArea；`max_length` 属于逻辑，prefix/suffix/count 属于展示 |
| `control.multiple-input` | [Form.List + Input](https://ant.design/components/form/) | `multiple_input` + text/integer/number/date | 输入开放的有序值列表；不是 Select 的封闭候选域 |
| `control.input-number` | [InputNumber](https://ant.design/components/input-number/) | `single_input/integer|number` | `min`、`max`、`step` 不由 Presentation 改写 |
| `control.auto-complete` | [AutoComplete](https://ant.design/components/auto-complete/) | `single_input/text + suggestions` | suggestion 只帮助输入；任意合法文本仍可提交，不等同 Select |
| `control.checkbox` | [Checkbox](https://ant.design/components/checkbox/) | `single_input/boolean` | 一个随外层 Query/Apply 工作流提交的布尔字段 |
| `control.switch` | [Switch](https://ant.design/components/switch/) | `single_input/boolean` | 立即发出 input/change；是否触发计算仍由外层工作流决定 |
| `control.radio-group` | [Radio.Group](https://ant.design/components/radio/) | `single_select` + 任一标量类型 | 少量互斥选项；不生成 All、Clear 或虚假空选项 |
| `control.select` | [Select](https://ant.design/components/select/) | `single_select|multiple_select` + 任一标量类型 | 分组、搜索、tag summary、max count、自动虚拟列表；批量操作只属于多选 |
| `control.checkbox-group` | [Checkbox.Group](https://ant.design/components/checkbox/) | `multiple_select` + 任一标量类型 | 2–5 个并列选项的直接多选；不显示冗余的全选、反选或清空工具栏 |
| `control.cascader` | [Cascader](https://ant.design/components/cascader/) | 单/多条完整 path | 用 `path_fields` 逐列保留父级上下文；可搜索完整路径与跨分支选择 |
| `control.tree-select` | [TreeSelect](https://ant.design/components/tree-select/) | 单/多条完整 path | 在窄弹层内搜索、展开和选择层级路径 |
| `control.date-picker` | [DatePicker](https://ant.design/components/date-picker/) | `single_input/date` | 可直接编辑的 `YYYY-MM-DD` 与统一日历；`min_date` / `max_date` 属于逻辑契约 |
| `control.range-picker` | [DatePicker.RangePicker](https://ant.design/components/date-picker/) | `range_input/date` | 两个可编辑 ISO 端点、一个日历触发器和一个协同弹层；支持 preset 与可选空端点 |
| `control.slider` | [Slider](https://ant.design/components/slider/) | `single_input|range_input` + integer/number | 单值或双端范围；有界数值、step、marks、tooltip 与可选同步 InputNumber |

`Form` 不拥有一个新的 value type。Dataviz 用 `control_panels` 组合 label、description、validation、布局和 Query/Apply 行为，对齐 [Ant Design Form](https://ant.design/components/form/) 的组合职责。

## 日期默认值与编辑器

日期默认值由独立的 **Date Atom** 组成。一个 Atom 只能是固定 ISO 日期，或相对 Workspace 时区中“今天”的整数日偏移：

```yaml
# 固定日期
default: "2026-08-20"

# 相对日期
default: {mode: relative, anchor: today, offset: -1d}
```

`range_input/date` 恰好包含两个彼此独立的 Atom，因此开始和结束不必使用同一种模式：

```yaml
default:
  - "2026-08-01"
  - {mode: relative, anchor: today, offset: -1d}
```

Server 默认值编辑器也按 Atom 呈现。单日期只有“类型 + 值”两个控件；日期范围分别为开始、结束各提供一组“类型 + 值”，共四个控件。选择“固定日期”时复用运行界面的可编辑 ISO DatePicker（包括八位数字自动分段、统一图标、浮层和校验），选择“相对今天”时值控件是整数 offset。编辑器不会同时显示两种输入，也不接受旧的 `start_offset/end_offset` 范围对象。

相对表达式只允许用于 Query Parameter；在 Run 创建前解析成具体 `YYYY-MM-DD`，随后 SQL 绑定、缓存和导出 HTML 都使用该不可变日期。Control 的交互状态必须保存具体日期，不能随浏览日期漂移。

运行界面的 DatePicker 与 RangePicker 始终展示 `YYYY-MM-DD`，不采用浏览器原生 `date` 控件的本地化格式。键入或粘贴连续八位数字会自动跨过年/月/日分隔符：`20260809` → `2026-08-09`。这只是输入辅助，不放宽日期契约；`20260231` 仍会被真实日期校验拒绝。Range 的两个端点可以分别文本编辑，也可以在同一双月弹层中依次选择；两个端点共用一个外框，不各自绘制输入边框。单日期、Range 和默认值编辑器的日历都可直接下拉选择年与月；没有声明 preset 时不渲染空工具条，没有 Clear/Apply 时不再用 footer 重复已选日期范围。

## 动态选项域与多选意图

级联多选不能只保存当前可见的 value，还必须保存用户的选择意图：

- `all_available`：原本选中了全部可用项；上级范围扩大时，新出现的可用项继续被选中。
- `explicit`：用户指定了部分项；上级变化时优先保留有效交集，原非空选择完全失效时恢复 `initial`，用户主动空集继续保留。

这项规则由 `runtime.control` 统一实现，适用于 Checkbox Group、Select、Cascader 和 Tree Select。意图会随同一 tab 状态和导出的 HTML 保存，因此父级范围临时缩小后，不会把“显式子集”误判成“全部可用”。Presentation 只能改变组件外观，不能改写这项协调语义。

Select 必须明确候选域由谁拥有：

- `options.mode: static`：Dashboard 维护封闭 `choices`；Source 中未列出的值不会进入控件。
- `options.mode: infer`：Runtime 从 `options.source` 或消费该 Control 的 Base Output 推导完整选项域。

Select 不使用 `default`，而是统一使用 `initial`。多选支持 `all/empty/values`，单选支持 `first/empty/value`；未声明时分别默认 `all` 和 `first`。`all` 编译为 `all_available` 意图，因此 Source 从 4 个城市增加到 10 个时无需修改 Dashboard。

其他输入组件不具有候选池，因此不套用 Select 的恢复策略：

| 逻辑类型 | 初始值 | 后续协调 |
| --- | --- | --- |
| `single_input` | `default` 或空值 | 保留用户输入；按 text / bool / integer / number / date 类型与边界校验 |
| `multiple_input` | `default` 列表或空列表 | 保留完整列表；校验元素类型、去重和 `max_items` |
| `range_input` | `default: [start, end]` 或空范围 | 两个端点作为一个值提交；校验类型、顺序、边界和 `allow_empty` |
| `single_select` | `initial: first | empty | value` | 候选变化时保留有效值；原非空值完全失效才按 `initial` 恢复 |
| `multiple_select` | `initial: all | empty | values` | 候选变化时跟随 intent、保留有效交集；完全失效才按 `initial` 恢复 |

`Slider`、`InputNumber`、`DatePicker`、`Checkbox` 等只是上述逻辑类型的展示组件，不另造初始化语义。`min` 不是默认值，`false` 和“今天”也不会被 Runtime 擅自推断；如果必填输入未声明 `default`，它会保持空值并在提交时提示补充。这样修改候选域只协调 Select，修改展示组件或约束不会悄悄重置用户已经输入的业务值。

候选项依赖属于值/数据契约，不属于 Component。下游 Control 只用 `depends_on` 声明直接父节点：

```yaml
controls:
  - id: dow
    field: dow
    type: single_select
    options: {mode: infer, source: source:hourly/main}
  - id: dates
    field: job_date
    type: multiple_select
    depends_on: [view.dow]
    options: {mode: infer, source: source:hourly/main}
```

`dashboard.<id>` 指当前 Dashboard，`section.<id>` 指当前所在 Section，`view.<id>` 指当前 View；不能跨兄弟 Section/View。链式关系只写直接边，例如 A 依赖 B、B 依赖 C，不在 A 重复列 C。`dataviz validate` 负责作用域、未知父节点、Select 类型、候选关系字段和环；Select、Checkbox Group、Cascader 或 Tree Select 只呈现同一份 canonical 状态。

Control 本身不声明“筛选”或“计算”类别。效果由每个消费者的 `control_inputs` 决定：`mode: filter` 对指定表和字段筛选，`mode: value` 把值、是否存在或候选意图传给 View/Interactive Transform。同一个 Control 可以被不同消费者以不同方式读取。

## 自动选择规则

不写 Presentation 时，默认 Renderer 使用确定性规则：

```text
path_fields                              → cascader
range_input/date                         → range-picker
single_input/date                        → date-picker
range_input/integer|number               → slider
single_input/integer|number              → input-number
single_input/boolean                     → checkbox
multiple_input                           → multiple-input
single_input/text + suggestions / plain  → auto-complete / input
single_select with ≤ 4 choices      → radio-group
multiple_select with 2–5 choices       → checkbox-group
other flat select                   → select
```

Checkbox Group 的意义是“所有少量选项都值得直接看到”。可清空时，用户直接取消最后一个勾选；必选时，Runtime 会阻止取消最后一项。6 个及以上的平面候选项默认使用 Select，由它承担搜索、虚拟列表和多选批量操作；层级候选项使用 Cascader 或 TreeSelect。

自动规则只负责开箱即用。需要特定交互时，显式写 `control_components`。

## 配置示例

逻辑文件只声明值和行为：

```yaml
controls:
  - id: model
    type: single_select
    value_type: text
    label: 模型
    required: true
    initial: {mode: value, value: baseline}
    options:
      mode: static
      choices:
        - {label: 基线, value: baseline}
        - {label: 候选, value: candidate}

  - id: location
    type: multiple_select
    value_type: text
    label: 地区
    field: district
    path_fields: [province, city, district]
    options:
      mode: infer

interactive_transforms:
  - id: forecast
    control_inputs:
      model: {mode: value, control: dashboard.model}

views:
  - id: district-detail
    input: source:districts/main
    control_inputs:
      location: {mode: filter, control: dashboard.location, field: district, inputs: [main], empty: passthrough}
```

Presentation 只选 Component 和视觉选项：

```yaml
schema: dataviz/presentation/v2
kind: presentation
dashboard: forecast

control_components:
  # RangePicker 默认仍是一列；只有确有需要时才显式跨两列。
  query:job_date_range:
    component: range-picker
    span: 2

  dashboard:forecast/model:
    component: radio-group
    option_type: button
    button_style: solid

  dashboard:forecast/location:
    component: cascader
    level_labels: [省, 市, 区县]
    search: always
    show_checked_strategy: parent

control_panels:
  query:
    template: grid
    columns: 6
  dashboard:
    template: grid
    width: wide
    columns: 2
```

Query Parameters 的 `columns` 表示最大列数（默认 6），`column_width` 表示目标轨道宽度（默认 280 px）。Runtime 根据 Query Panel 自身宽度计算实际列数，不会强迫窄容器挤出固定列数；参数较少时也不会把两三个控件拉伸到占满整行。所有控件默认 `span: 1`；`span: 2` 是显式排版选择。Dashboard/Section/View Controls 默认单列，避免把 Query 的密集网格交互扩散到局部操作。

错误组合会在 `dataviz validate` 阶段失败。例如：

- `radio-group` 不能渲染 `multiple_select`；
- `auto-complete` 必须有 `suggestions`；
- `cascader` / `tree-select` 必须有 `path_fields`；
- 其他 Component 不能悄悄忽略 `path_fields`；
- Presentation 不能声明 `min`、`max_selected` 或 `placeholder` 等逻辑字段。

## 暂不吸收的 Ant Design Data Entry

- `TimePicker`：DSL 尚无 `time` / `time_range` value type；不会用普通 string 伪装。
- `Transfer`：适合数百项的候选/已选双栏，但需要先验证真实分析场景、搜索和窄屏体验。
- `ColorPicker`：更适合 Theme/Presentation 编辑器，不是默认分析参数。
- `Mentions`、`Rate`：目前没有稳定、通用的数据分析参数语义。
- `Upload`：属于 Source/Adapter 的数据接入、安全和文件生命周期，不放进浏览器 Control。

## AI 开发入口

```bash
dataviz docs data-entry-components --format json
dataviz components list --category data-entry --format json
dataviz components show control.cascader --format json
dataviz scaffold control.range-picker --id analysis-window --format json
dataviz components gallery --output component-gallery.html
dataviz validate <workspace> --dashboard <dashboard-id> --format json
```

AI 应读取具体 Component contract，而不是阅读整个浏览器 Runtime。若模板缺能力，先扩展对应 `control.*` Package；不要在单个 Dashboard 中复制一套临时选择器。

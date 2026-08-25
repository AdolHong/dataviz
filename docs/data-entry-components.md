# Data Entry Component 语义契约

Dataviz 把三个问题彻底分开：

1. `dashboard.yaml` 定义值是什么，以及它如何影响数据：Query Parameter、Selection 或 Compute。
2. Control 所在位置定义作用域：Dashboard、Section 或 View。
3. `presentation.yaml` 只选择如何编辑这个值：`control.input`、`control.select`、`control.cascader` 等。

因此，同一个 `boolean` 可以显示成 Checkbox 或 Switch，但它的默认值、校验、作用域和依赖关系不会被 CSS 或 Component 改写。

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
| `control.input` | [Input](https://ant.design/components/input/) | `string` | 单行或 TextArea；`max_length` 属于逻辑，prefix/suffix/count 属于展示 |
| `control.input-number` | [InputNumber](https://ant.design/components/input-number/) | `number` / `integer` | `min`、`max`、`step` 不由 Presentation 改写 |
| `control.auto-complete` | [AutoComplete](https://ant.design/components/auto-complete/) | `string + suggestions` | suggestion 只帮助输入；任意合法文本仍可提交，不等同 Select |
| `control.checkbox` | [Checkbox](https://ant.design/components/checkbox/) | `boolean` | 一个随外层 Query/Apply 工作流提交的布尔字段 |
| `control.switch` | [Switch](https://ant.design/components/switch/) | `boolean` | 立即发出 input/change；是否触发计算仍由外层工作流决定 |
| `control.radio-group` | [Radio.Group](https://ant.design/components/radio/) | `single_select` | 少量互斥选项；不生成 All、Clear 或虚假空选项 |
| `control.select` | [Select](https://ant.design/components/select/) | `single_select` / `multi_select` | 分组、搜索、tag summary、max count、自动虚拟列表；批量操作只属于多选 |
| `control.checkbox-group` | [Checkbox.Group](https://ant.design/components/checkbox/) | `multi_select` | 少量显式多选；可配置全选、反选、清空；每个选中项始终可见 |
| `control.cascader` | [Cascader](https://ant.design/components/cascader/) | 单/多条完整 path | 用 `path_fields` 逐列保留父级上下文；可搜索完整路径与跨分支选择 |
| `control.tree-select` | [TreeSelect](https://ant.design/components/tree-select/) | 单/多条完整 path | 在窄弹层内搜索、展开和选择层级路径 |
| `control.date-picker` | [DatePicker](https://ant.design/components/date-picker/) | ISO `date` | 单个日期；`min_date` / `max_date` 属于逻辑契约 |
| `control.range-picker` | [DatePicker.RangePicker](https://ant.design/components/date-picker/) | `[start, end]` | 一个触发器、一个弹层、一次协同选择；支持 preset 与可选空端点 |
| `control.slider` | [Slider](https://ant.design/components/slider/) | `number` / `integer` | 有界数值、step、marks、tooltip 与可选同步 InputNumber |

`Form` 不拥有一个新的 value type。Dataviz 用 `control_panels` 组合 label、description、validation、布局和 Query/Apply 行为，对齐 [Ant Design Form](https://ant.design/components/form/) 的组合职责。

## 动态选项域与多选意图

级联多选不能只保存当前可见的 value，还必须保存用户的选择意图：

- `all_available`：原本选中了全部可用项；上级范围扩大时，新出现的可用项继续被选中。
- `explicit`：用户指定了部分项；上级变化时只保留有效交集，不擅自增加其他项。

这项规则由 `runtime.control` 统一实现，适用于 Checkbox Group、Select、Cascader 和 Tree Select。意图会随同一 tab 状态和导出的 HTML 保存，因此父级范围临时缩小后，不会把“显式子集”误判成“全部可用”。Presentation 只能改变组件外观，不能改写这项协调语义。

Select 必须明确候选域由谁拥有：

- `options.mode: static`：Dashboard 维护封闭 `choices`；Source 中未列出的值不会进入控件。
- `options.mode: infer`：Runtime 从 `options.source` 或消费该 Selection 的 Base Output 推导完整选项域。

`infer` 不允许写具体值列表 `default`。多选默认 `initial: auto`，编译为 `all_available` 意图，因此 Source 从 4 个城市增加到 10 个时无需修改 Dashboard；Selection Gallery 等需要初始不选择的场景使用 `initial: empty`。这不是候选值副本，不会随数据漂移。

## 自动选择规则

不写 Presentation 时，默认 Renderer 使用确定性规则：

```text
path_fields                         → cascader
date_range / date                   → range-picker / date-picker
number or integer                   → input-number
boolean                             → checkbox
string + suggestions / plain string → auto-complete / input
single_select with ≤ 4 choices      → radio-group
multi_select with ≤ 8 choices       → checkbox-group
other flat select                   → select
```

自动规则只负责开箱即用。需要特定交互时，显式写 `control_components`。

## 配置示例

逻辑文件只声明值和行为：

```yaml
controls:
  - id: model
    kind: compute
    type: single_select
    label: 模型
    required: true
    default: baseline
    options:
      mode: static
      choices:
        - {label: 基线, value: baseline}
        - {label: 候选, value: candidate}

  - id: location
    kind: selection
    type: multi_select
    label: 地区
    field: district
    path_fields: [province, city, district]
    options:
      mode: infer
```

Presentation 只选 Component 和视觉选项：

```yaml
schema: dataviz/presentation/v1
kind: presentation
dashboard: forecast

control_components:
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
  dashboard:
    template: grid
    width: wide
    columns: 2
```

错误组合会在 `dataviz validate` 阶段失败。例如：

- `radio-group` 不能渲染 `multi_select`；
- `auto-complete` 必须有 `suggestions`；
- `cascader` / `tree-select` 必须有 `path_fields`；
- 其他 Component 不能悄悄忽略 `path_fields`；
- Presentation 不能声明 `min`、`max_selected` 或 `placeholder` 等逻辑字段。

## 暂不吸收的 Ant Design Data Entry

- `TimePicker`：DSL 尚无 `time` / `time_range` value type；不会用普通 string 伪装。
- `Transfer`：适合数百项的候选/已选双栏，但需要先验证真实分析场景、搜索和窄屏体验。
- `ColorPicker`：更适合 Theme/Presentation 编辑器，不是默认分析参数。
- `Mentions`、`Rate`：目前没有稳定、通用的数据分析参数语义。
- `Upload`：属于 Source/Adapter 的数据接入、安全和文件生命周期，不放进浏览器 Selection/Compute。

## AI 开发入口

```bash
dataviz docs data-entry-components --format json
dataviz components --category data-entry --format json
dataviz components control.cascader --format json
dataviz scaffold control.range-picker --id analysis-window --format json
dataviz gallery --output component-gallery.html
dataviz validate <workspace> --dashboard <dashboard-id> --format json
```

AI 应读取具体 Component contract，而不是阅读整个浏览器 Runtime。若模板缺能力，先扩展对应 `control.*` Package；不要在单个 Dashboard 中复制一套临时选择器。

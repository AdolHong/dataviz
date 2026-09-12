# Server / Share / HTML UI 一致性审查

状态：本轮审查与修复完成（2026-09-12），尚未打包或调整 Dataviz 自身版本。

## 最终结论

Server、真实 Share URL、导出 HTML 的共享 Header、快捷键弹窗、320px 操作侧栏及字段视觉契约已对齐；保留查询、Workspace 导航和服务端执行的环境能力差异。`?` 打开帮助不再突出关闭按钮，标题接收无轮廓的初始焦点，Tab/Shift+Tab 可在弹窗内导航，关闭后返回入口。

验证证据位于 Git 忽略目录 `.test-evidence/three-surface-final/`：

- 三端一致性矩阵每浏览器 26 项：Chromium、Firefox 各 26 通过（`confirmed-chromium.log`、`confirmed-firefox.log`）；最后焦点改动后 WebKit 完整重跑 26 项通过（`final-webkit-matrix.log`）。这是针对本轮范围的矩阵，不是全部 107 项浏览器测试。
- 最后焦点改动后，三个浏览器均重新通过 7 项直接相关测试，覆盖 shell、选择/日期和 Gallery（`final-focus-*.log`）；不把 Chromium/Firefox 先前的 26 项描述为最后改动后的完整重跑。
- 相关非浏览器 224 项通过（`final-nonbrowser.log`），保留 1 条依赖 warning；JS 语法检查与 `git diff --check` 通过。
- 控件清单覆盖 14 个 data-entry 包，跨宽/窄屏比较字段几何与计算样式。`after-{server,share,html}-375.png` 记录修复后的侧栏，已人工检查。
- Perspective 5.4.0、Plotly.js 4.1.0 的真实加载与释放另有实际库断言；生命周期模拟测试仅证明适配器契约，不替代真实库证据。

本轮发现并修复了字段标签/间距/边框不一致、Firefox 重复数字步进、日期 change 递归、数值区间序列化清空、销毁后迟到渲染及浮层延迟聚焦覆盖后续输入等问题。未新增 DSL。

## 范围与边界

- 同一 Result 的共享 Header、Parameters/Controls 侧栏、Dashboard/Section/View 层级、控件浮层、快捷键、焦点、响应式、View 操作和空/错误状态应一致。
- Server 的查询、作者编辑、Workspace 导航为环境能力。Share 可连接服务端交互；离线 HTML 不应伪装成支持服务端执行。
- Parameters 在 Server 中可编辑，在 Share/HTML 中展示已应用查询值；这种能力差异不能成为标题、侧栏、关闭方式不一致的理由。

## 已取得的证据

新增 `test_three_surface_shell_audit`：同一数据生成 Server、真实 Share URL 和导出 HTML；覆盖 1440、894、375px。检查侧栏尺寸、标题/关闭按钮/层级标题计算样式、点击与 W/E 开关、只读参数和禁用查询能力。

初始实测：三端宽度均为 320px；Server 桌面侧栏从 Header 下方开始，Share/HTML 从视口顶部开始；标题字体和颜色不同；Share/HTML 窄屏没有 Server 同款遮罩。层级配色一致。

本轮修改：共享侧栏标题和关闭按钮样式；Share/HTML 桌面起点跟随 Header，窄屏提供遮罩、禁止背景滚动及点击遮罩关闭；Server 非交互层级标题不显示误导性的焦点框。

## 过程记录

下列记录保留排查过程；早期失败和待办不代表最终状态，最终结论以文首汇总为准。

### 第二轮进展

- Share/HTML 新增 Shortcuts 入口，Controls/Parameters 无字段时保持禁用入口；帮助文案和共同条目的样式统一。查询与 Workspace 专属快捷键仍仅在 Server 出现。
- Header 普通/展开/禁用状态、过渡和字体统一；窄屏允许换行并同步布局高度，回归同时断言入口横向可见且完全落在 Header 内。
- 修复 WebKit 点击 Shortcuts 后关闭帮助不返回入口的实际差异，显式保留开启元素。
- 三端同一 Result 测试已参数化有/无字段，比较 Header、帮助弹窗、侧栏、层级标题和关闭按钮的计算样式。不是靠隐藏差异或忽略失败完成比较。
- 相关 Server/上下文非浏览器测试：57 项通过（`/tmp/dataviz-three-server-contract-final.log`）。最终浏览器几何验证：Chromium、Firefox、WebKit 各 2 项通过，分别见 `/tmp/dataviz-three-header-grid.log`、`/tmp/dataviz-three-firefox-grid.log`、`/tmp/dataviz-three-webkit-grid.log`。每项内部覆盖三个页面和三种屏宽，不代表剩余控件矩阵已完成。

### 第三轮进展

- 将 `test_cascader_sidebar_bounds_and_global_all` 扩展为 Server、真实 Share URL、导出 HTML × 1440/894/375px：验证浮层不越界、全局全选/清空、搜索结果全选/清空不影响范围外选择、空结果禁用、canonical `all_available`、Escape 仅关闭菜单而保留侧栏。
- 初始窄屏失败定位为测试导航步骤错误：移出视口的左栏依然被 Playwright 判定 CSS-visible。改为读取导航按钮 `aria-expanded`，通过实际按钮打开/收起，不采用强制点击。
- 上述级联矩阵 Chromium、Firefox、WebKit 各 9 项通过，日志为 `/tmp/dataviz-cascade-three-final.log`、`/tmp/dataviz-cascade-three-firefox.log`、`/tmp/dataviz-cascade-three-webkit.log`。
- 截图发现 Firefox 数字输入同时出现原生 spinner 和组件加减按钮。共享 `control.input-number` 补 `appearance: textfield`，保留原生输入语义与组件步进；矩阵增加计算样式及加减值断言。最终确认 Chromium/Firefox/WebKit 各 9 项通过（`/tmp/dataviz-controls-confirm-{chromium,firefox,webkit}.log`）。截图按浏览器、页面和屏宽分开保存，避免并行覆盖。

### 第四轮进展：普通选择、日期与运行库

- 新增 `test_three_surface_choice_and_date_controls`：同一 Result 的 Server/Share/HTML，宽屏与窄屏均执行单选搜索、多选搜索范围操作、空结果禁用、输入 E 不误触快捷键、日期非法值纠正、范围编辑、浮层边界和关闭；比较实际可见字段的字体、颜色与宽度。
- 修复 Server 从旧弹窗继承的额外 8px 内边距；窄屏 Share/HTML 取消多余边框，三端字段宽度一致。
- 修复 Date Picker 的 change → commit → emitChange → change 递归；原生 change 仅规范化一次，不再次发出相同事件。
- 按用户新要求升级：Perspective 默认及两个示例改为 5.4.0；内置 Plotly.js 改为 4.1.0，同步 CLI 文档、测试、资产校验与来源说明。Plotly 包经过 npm SHA-512 校验，内置 JS SHA-256 为 `03e18091beef5647aaf9e15f526981f325d760bb6b784fe0672a1e20585272cf`；旧 4.0.0 文件移除，Git 可恢复。
- 检查官方固定版本源码确认：Perspective 5.4.0 与 5.2.0 均对专用 Worker 调用不存在的 close。仅通过公开 worker 参数管理 Dataviz 自己创建的实例，提供幂等 close/terminate 和 Blob URL 释放，不修改全局原型、不吞掉释放错误。
- 真实 Worker 释放测试发现销毁后排队的渲染仍可重建 View，已补 Runtime/Adapter 入口及异步阶段的 disposed 检查。新测试不使用 Perspective 模拟包，检查实际 Plotly 版本、Perspective 配置、真实表格 ready，以及 created/disposed 计数和清空的状态表。
- 升级后相关非浏览器 222 项通过（`/tmp/dataviz-libraries-nonbrowser.log`），三浏览器各 5 项通过（`/tmp/dataviz-libraries-{chromium,firefox,webkit}.log`）。随后加入更严格的真实释放断言并修复竞态，最终确认结果另记。原有 `managed_renderer_lifecycle_matrix` 使用 Perspective 契约替身，不能单独用来证明新版真实 Worker 兼容。
- 最终工作树确认：非浏览器 222 项通过（`/tmp/dataviz-libraries-final-nonbrowser.log`）；Chromium、Firefox、WebKit 各 3 项通过（`/tmp/dataviz-libraries-final-{chromium,firefox,webkit}.log`），其中 2 项为宽/窄屏的三端真实库控件与释放回归，1 项为既有适配器生命周期契约。早先并行运行遇到 CDN WASM 下载超时，串行复核未放宽断言或时间门槛。JS 语法检查及 `git diff --check` 通过；尚未打包或调整 Dataviz 自身版本。

### 快捷键弹窗初始焦点

- Server、Share、HTML 的帮助弹窗统一将初始焦点放在标题，不再自动突出右上角关闭按钮。只隐藏静态标题的轮廓，保留交互控件的键盘焦点样式。
- 关闭后快速重开时忽略上一轮延迟到达的 close 事件，避免焦点被旧事件移回 Header。
- 定向三端 shell 测试覆盖点击及 `?` 打开、标题无轮廓、Tab 导航与 Escape 关闭。初期保留原生 Tab 顺序；第八轮根据 WebKit 实测改为弹窗内显式键盘循环。

### 验证清单（结合下方补充证据）

- 已覆盖：Header/帮助/侧栏有无字段、宽中窄屏、共同操作文案与样式、打开与关闭、焦点恢复和输入时不触发热键。
- 已覆盖：全部 14 个已注册 data-entry 包，见第七轮清单；包含搜索范围操作、浮层边界及空候选。
- 已覆盖：Dashboard/Section/View 路径切换、popover 与侧栏共存、相同按钮再次关闭、状态同步及参数只读差异。
- 已覆盖：视图首次加载、更新等待、空状态、错误与恢复、图表 resize 和释放；原生表格排序、搜索、分页与焦点；Share 服务端交互与 HTML 禁用边界。
- 已修复：最终截图发现的字段标签/间距/边框差异，并强化整组字段断言，见第八轮。最后的焦点竞态与复核见第九轮。

测试结果必须以本次工作树运行日志为准；初始采集通过不代表上述所有条目已经达成。

### 第五轮进展：控件路径与 Share 边界

- 扩展 `test_contextual_controls_sibling_switch_and_popover_override`，让同一 Result 实际经过 Server、Share URL、导出 HTML；分别覆盖有/无 Dashboard Controls。验证隐藏侧栏时 popover 不打开侧栏、Query 切换为 Controls、兄弟 View 替换、同一按钮关闭，以及弹窗和侧栏双向选择同步。
- 测试严格区分弹窗仍打开和已 light-dismiss 的状态：点击侧栏会关闭旁边的弹窗；重新打开后按 Escape 只关闭弹窗，E 再关闭侧栏。不会把错误的测试前提改成产品行为。
- 两项路径变体及原有 portable-state 测试，Chromium/Firefox/WebKit 各 3 项通过，日志 `/tmp/dataviz-context-path-current.log`、`/tmp/dataviz-context-path-{firefox,webkit}.log`。WebKit 的 Share/HTML 三级侧栏截图已人工查看，层级、配色、留白、字段宽度一致；截图 `/tmp/dataviz-context-path-webkit-{share,html}-True.png`。
- Share Worker 回归改为在当前可见侧栏中 fill + Tab，避免旧测试定位隐藏模板和侧栏副本导致 strict-mode 冲突。Chromium 的 Share 浏览器计算与 Server-Python/HTML 禁用边界两项通过，日志 `/tmp/dataviz-share-boundary-current.log`。这不是已覆盖所有 View 公共操作的证据。
- 快捷键最终修复的非浏览器 70 项与三浏览器各 2 项通过，日志 `/tmp/dataviz-shortcut-focus-unit.log`、`/tmp/dataviz-shortcut-focus-{chromium,firefox,webkit}.log`。
- Share 执行边界补充确认：Firefox/WebKit 各 2 项通过（`/tmp/dataviz-share-boundary-{firefox,webkit}.log`）；本轮三浏览器路径与边界回归合计 15 项通过。生成运行时代码语法检查和 `git diff --check` 通过。

上述结果补足相应条目，不替代仍待覆盖的其他控件、View 公共操作、加载/错误状态及最终审计。

### 第六轮进展：View 状态与生命周期

- `test_managed_renderer_lifecycle_matrix_in_server_and_export` 现在覆盖 Server、真实 Share、HTML 三端：挂载、保留实例更新、清空、恢复、Plotly 事件、resize 与释放。Perspective 在此测试中是生命周期契约替身；真实 5.4.0 库的验证见第四轮，不混淆两者。
- 新增 `test_three_surface_renderer_pending_error_and_recovery`：单文件看板、相同 Result、实际侧栏下拉选择。控制 Renderer 的首次校验与更新 Promise，验证首次 loading/aria-busy、更新期间保留原数据、可访问的错误提示、错误计算样式一致，以及切回正常选择后的恢复。
- 测试 fixture 显式指定 Select 组件并使用直接 Dashboard URL；不依赖单文件模式中禁用的 Workspace 导航。状态通过真实控件操作提交，不用直接写状态再让 applyControls 读取旧 DOM 的错误测试方式。
- Chromium/Firefox/WebKit 各 2 项通过，共 6 项；日志 `/tmp/dataviz-view-states-{chromium,firefox,webkit}.log`。本轮没有为通过测试而修改产品行为，新增的是三端回归覆盖；`git diff --check` 通过。

### 第七轮进展：完整控件清单与表格操作

对照 `src/dataviz/components/packages/control.*/manifest.yaml` 清点 14 个 data-entry 包，没有把未测控件默认为已覆盖：

| 包 | 三端证据 |
| --- | --- |
| input、input-number、multiple-input、auto-complete | Gallery 同样的编辑、计数、增删、建议选择、数字步进和内边框断言 |
| checkbox、checkbox-group、radio-group、switch | Gallery 勾选、全空/恢复、键盘单选与开关状态 |
| slider | Gallery 标量和区间、数字端点与轨道同步、初始值 |
| select、cascader、tree-select | Gallery 分组搜索、虚拟列表、树分支选择与清空；另有跨宽/中/窄屏多选和级联矩阵 |
| date-picker、range-picker | Gallery 日期校验、Enter 提交、日历选择、预设、清空；另有宽/窄屏日期矩阵 |

- Gallery 原有真实操作测试扩展为 Server/Share/HTML 参数化；并补齐多值输入增删与区间滑块联动。首次运行发现数值区间的隐藏原生 input 错用 number，浏览器把 `0.25,0.75` 清空。Server JS 和共享 Canvas 生成器均改为 text 保存序列化区间；端点组件继续负责数字约束。不改 DSL。
- 增加 number/integer 区间标记回归，防止重新引入单值 number 类型。相关非浏览器 142 项通过（`/tmp/dataviz-range-contracts.log`）。
- 原生表格测试扩展三端，验证行数显隐、输入法组合输入不重建输入节点、搜索、排序、分页和宽表排序后滚动/焦点保留。
- Chromium Gallery 3 项、Table 3 项通过（`/tmp/dataviz-gallery-three-chromium.log`、`/tmp/dataviz-table-three-chromium.log`）；Firefox/WebKit 各 6 项通过（`/tmp/dataviz-gallery-table-{firefox,webkit}.log`）。
- 当前工作树集中复核已启动，日志归档在已被 Git 忽略的 `.test-evidence/three-surface-final/`。在完成前不将上述分批结果等同于最终集成通过。

### 集中复核结果与未完成项

- 非浏览器 224 项通过；Firefox 26 项通过；Chromium 25 通过/1 失败；WebKit 24 通过/2 失败。日志位于 `.test-evidence/three-surface-final/{nonbrowser,chromium,firefox,webkit}.log`，不能称为集成全绿。
- Chromium 窄屏与 WebKit 宽屏 choice/date 用例在真实 Perspective 的 ready 等待失败，证据显示外部 WASM/worker 仍在下载；需要单独复核，不提高超时或把替身算作真实库通过。
- WebKit shell 用例在 Tab 后的焦点位置检查失败，需核对原生对话框的键盘导航行为，不能用删除断言掩盖。
- 最终窄屏截图暴露此前断言未覆盖的差异：Server 标签继承 `.field label` 的大写等宽字；portable 使用 `.dv-control-field > span`，未命中同样的标签样式，整组垂直间距也不同。输入边框色来自不同宿主的 `--dv-line` 默认值。已归档三端截图 `dataviz-choice-date-chromium-{server,share,html}-375.png` 到同一证据目录。**尚未修复，目标不能完成。**
- 下一步限定为上述已证实的样式与焦点问题、对应回归补强及失败项复核，不扩展新的设计功能。

### 第八轮：补齐字段视觉契约与模态键盘循环

- 共享侧栏样式明确中性控件配色，避免 Server 缺少 Canvas 基础变量时落到另一套边框色；`.field > label` 与 `.dv-control-field > span` 使用相同字重、字号、颜色和大小写。字段内间距 6px、字段间距 12px；三级作用域间距仍保留 56px。
- Portable 的实际字段容器为 `.dv-control-fields`，此前未被 Grid 间距规则覆盖，已补齐。不是仅在外层加 padding 来掩盖内部差异。
- choice/date 回归新增整组字段高度、相对位置、标签字体/颜色/大小写、实际入口边框和背景对比。Chromium 宽/窄屏三端严格相等，截图已人工确认；同时 shell 测试通过，共 4 项，日志 `field-parity-chromium.log`。
- WebKit 的 Tab 焦点问题在可重试断言下仍可复现，因此不是单纯采样问题。共享帮助弹窗增加仅限弹窗内部的 Tab/Shift+Tab 循环（跳过禁用/不可聚焦项），初始焦点继续在标题；回归明确检查首个 Tab 到关闭按钮、Shift+Tab 循环到末尾按钮。不再依赖不同平台的默认有限 Tab 模式。
- 最终串行复核在运行，使用 `confirmed-*.log` 与上一轮失败记录区分；当前 `confirmed-nonbrowser.log` 为 224 项通过。浏览器结果未全部结束前，不把分批通过记录当作完成证明。

### 第九轮：延迟聚焦不得覆盖后续输入

- 串行矩阵 Chromium、Firefox 各 26 项通过；WebKit 25 项通过、1 项日期草稿失败。定位为日历和共享浮层打开时排队的 requestAnimationFrame 聚焦，在用户已开始输入之后仍把焦点移走，导致确认状态覆盖非法日期草稿。
- 两处延迟聚焦现在同时检查打开状态、原焦点和输入值；后续用户操作优先。不放宽日期校验，也不删除输入草稿保护。
- Gallery 增加确定性帧时序回归：输入聚焦后打开日历，在待执行聚焦前修改日期，等待两帧，确认焦点、草稿和非法状态保留。
- 最终改动后，Chromium、Firefox、WebKit 各 7 项定向回归通过（`final-focus-{chromium,firefox,webkit}.log`），涵盖三端 shell、choice/date 与 Gallery；非浏览器 224 项通过（`final-nonbrowser.log`）。日志均在 `.test-evidence/three-surface-final/`。

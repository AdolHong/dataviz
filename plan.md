# Dataviz 实施计划

更新时间：2026-09-11

当前协议基线（由 `protocols.py` 与回归检查约束）：`dataviz/workspace/v2`、`dataviz/dashboard/v20`、`dataviz/parameter-domain/v2`、`dataviz/parameter-domain-contract/v3`、`dataviz/parameter-lookup/v1`、`dataviz/parameter-materialization/v1`、`dataviz/dashboard-bundle/v2`、`dataviz/report-manifest/v3`、`dataviz/presentation/v2`、`dataviz/source/v6`、`dataviz/dataset-transform/v3`、`dataviz/interactive-transform/v4`、`dataviz/dependency-contract/v13`、`dataviz/layout-contract/v1`、`dataviz/state-snapshot/v6`、`dataviz/runtime/v15`、`dataviz/analysis-result/v5`、`dataviz/analysis-evidence/v5`。Component Registry 以 `dataviz components` 为准，不在阶段清单重复登记。

当前包版本：`0.24.3`。本文件区分本地发行构建、工作树变更与待验证事项，不以完成过的历史阶段作为未来计划。架构理由见 [ARCHITECTURE](ARCHITECTURE.md)，视觉规范见 [DESIGN](DESIGN.md)，代码见 [实现索引](docs/product-architecture.md)，发行历史见 [CHANGELOG](CHANGELOG.md)。

## 0.24.3 统一 Q/C 面板宽度

- 面板统一 360px，解除侧栏内部重复 280px 字段上限，输入框与标题线对齐；保留日期完整显示、自然选项排列、现有颜色/间距/交互。独立 HTML Controls 同步。
- 全套非浏览器 **731 passed，123.47 秒**；完整 Chromium **96 passed，1092.57 秒**；完整 Firefox **96 passed，1136.24 秒**；完整 WebKit **95 passed、1 failed，1131.22 秒**。
- WebKit 首次失败为 `test_server_compute_waits_for_required_control_domain[error]`：20 秒内初始 Canvas 未出现，停留在运行前页面，尚未验证到错误域状态。单独复跑 **1 passed，15.15 秒**，不改超时或放宽断言；目前原因未确认，保留为间歇性初始化超时，不声称已修复或三浏览器一次全绿。
- 三套均执行全部 E2E；Runtime 用例使用相应浏览器，Analysis/visual-check CLI 中指定 Chromium 的用例仍使用 Chromium。浏览器测试复用摘要校验的本地上游资源缓存，不测试 CDN 可用性。组件元数据检查 21 包通过。
- WebKit 完整就绪/空域/错误域分组复验 **3 passed，37.38 秒**；升版后的发行/版本检查 **23 passed，1.37 秒**。复验通过不替代首次失败记录。
- 本地构建 wheel、sdist、ZIP/SHA256，检查包内版本与前端资源；不上传远端包仓库。本轮未做安装冒烟、多 Python 版本或完整浏览器缩放矩阵。

## 0.24.2 Controls 视觉打磨

- 标题后的细线延伸至内容区右侧，移除组间横线；三个作用域的标识、名称与细线统一使用对应层级色。层级间距 56px，组内间距不变，工作台与导出 HTML 同步。
- 默认 Section/View 使用 sidebar，popover 必须显式配置；C 直接收起任何 Controls 上下文，同一 Sidebar 入口再次点击收起，不同入口切换，Popover 只开关弹窗。
- 标题线调整后 Chromium 专项 **3 passed，38.82 秒**；同色调整后专项 **1 passed，14.20 秒**，包含桌面/窄屏截图及独立 HTML。随后间距翻倍经用户确认，仅做静态检查；不将先前浏览器成绩描述为最终间距版本的复验。
- 本轮按要求升版并本地打包；检查版本与归档完整性，不重跑完整测试或安装冒烟，不上传远端包仓库。
- 最终交互追加回归：Chromium 上下文与快捷键 **5 passed，60.89 秒**，显式 Popover/同 View 依赖专项 **3 passed，39.53 秒**；相关非浏览器与发行检查 **80 passed，11.40 秒**。最终上下文回归包含 56px 间距版本的桌面、窄屏与导出流程；不宣称重新跑过完整浏览器套件。

## 0.24.1 上下文 Controls 面板

- 复用右侧面板显示 Dashboard → 当前 Section → 当前 View；Presentation 默认与单对象覆盖选择 popover/sidebar，未配置保持原行为。已展开时局部入口只更新上下文，不收起；隐藏时只有 sidebar 入口展开。
- 弹窗与侧栏同步 canonical 状态，保留 Query 草稿、层级选择与排队中的提交；统一标题与轻量作用域标识，不改变数据协议。
- 完整非浏览器 **731 passed，112.85 秒**；完整 Chromium **96 passed，1080.37 秒**。本地校验过的上游资源缓存用于浏览器测试，生产加载策略不变。
- 用户在整套浏览器运行期间追加了纯视觉层级调整；调整后另跑上下文面板专项 **3 passed，38.73 秒**，并核对桌面/窄屏截图。全套成绩与追加专项分别记录，不混作最终视觉版本从头跑完的全套。
- 本轮构建本地 wheel、sdist、ZIP/SHA256；未运行 Firefox/WebKit、安装冒烟或多 Python 版本矩阵，不上传远端仓库。

## 0.24.0 右侧操作面板

- Query Parameters 与 Dashboard Controls 共用可切换右侧面板，Q/C 开关，保留草稿与运行状态；查询成功不自动收起。宽屏停靠、窄屏覆盖，保留焦点与快捷键禁用入口。
- 无参数的 Header 入口置灰但不隐藏，Q/C 提示一致；状态紧跟标题靠左，诊断与刷新靠右；左右 Sidebar 共用背景色，不显示冗余操作提示。
- 独立 HTML 移除禁用的查询按钮，仅保留查询参数证据入口；不提供 Run、Share 或工作台专属快捷键提示。
- 最终完整非浏览器 **727 passed，93 deselected，119.05 秒**；发行一致性检查 **23 passed，1.40 秒**。
- Chromium 完整首轮 **81 passed、12 failed，1079.96 秒**。修复普通 Input 被误判为等待候选域的调度问题，并更新右侧面板取代旧浮层/正文网格后的断言；全部 12 个失败项在最终代码上统一复验 **12 passed，97.63 秒**。不声明完整套件一次全绿。
- 追加导出与面板相关分组 **12 passed，175.91 秒**，侧栏输入等高专项 **1 passed，11.88 秒**；导出报告检查包含 Run/Share 缺席、快捷键帮助不含运行查询或 Sidebar、Q 查看参数证据。
- 浏览器测试使用校验摘要匹配的本地上游资源缓存，生产网络策略不变。本轮不运行 Firefox/WebKit 或安装冒烟；本地构建 wheel、sdist 与 ZIP/SHA256，不上传远端包仓库。

## 0.23.3 导航与参数初始化解耦

- Page 详情使用当前 Workspace 快照，只构造目标页，不重扫/校验全 Workspace；文件热更新与显式刷新继续负责目录发现。
- 导航开始即取消上一条 Page 详情与旧 Lookup；初始化和父子候选串行流程在每次 await 后检查导航身份，旧响应/重试不修改新页。
- 目标元数据尚未就绪时 Run 保持禁用，防止旧页回调重新启用；Sidebar/Page 导航不禁用。失败则保留原页并恢复其候选加载。
- 真实浏览器刻意挂起请求，验证连续切 Page、切 Dashboard、请求取消、无多余 Query、无旧子级 Lookup；Chromium 专项 **2 passed，25.26 秒**（含迟到失败），Firefox **1 passed，12.70 秒**，WebKit **1 passed，12.15 秒**。既有多页状态与候选分页 Chromium 两项通过。
- 没有新增 DSL、Worker 或复杂缓存；不承诺取消已在服务端执行的数据库物化，也不以此测试声称所有浏览器主线程卡顿都已消失。本轮不运行完整浏览器套件或安装冒烟。
- 最终相关非浏览器/发行检查 **110 passed，15.77 秒**；初轮静态断言误将失败恢复分支计入成功导航顺序，已明确限定成功路径，版本文档同步后复验通过。

## 0.23.2 本地发行

包含下述多页稳定性与查询参数可见恢复修复。沿用已记录的完整/专项测试证据，
本轮只做版本一致性与发行产物检查，不重跑浏览器全套或安装冒烟，不上传远端仓库。
完整 Chromium 曾有两个失败，修正或单独复验情况见下文；不声明完整套件一次全绿。

## 0.23.1 工作树验证

多 Page 导航样式与标题层级修复：相关非浏览器 **35 passed**；Chromium 专项
**2 passed，25.28 秒**；追加独立报告标题保留断言后 Page 专项 **12 passed**。
升版后的发行一致性检查 **21 passed**。随后按用户要求构建本地 ZIP、wheel 与源码包；
此次打包不重跑完整三浏览器套件或安装冒烟，不上传远端包仓库。

## 0.23.0 发行验收（2026-09-10）

- 完整 `tests/e2e`：Chromium **83 passed，909.66 秒**；Firefox **83 passed，925.15 秒**；WebKit **83 passed，918.55 秒**，三轮均无失败和跳过。
- 页面 Runtime 使用所选引擎；CLI 自管浏览器用例仍按其现有契约固定 Chromium，不将这部分宣称为跨引擎覆盖。
- 复用 git-ignored 的本地 Arrow/Plotly CDN 测试资源缓存，生产 CDN 行为不变。
- 完整非浏览器：**715 passed，83 deselected，116.01 秒**。首轮发现 Page 浏览器用例遗漏 e2e 标记，导致沙箱启动错误；补齐分类后完整重跑通过。版本检查曾因 plan 旧版本号失败，同步后通过。
- 静态检查通过。本次构建 ZIP、wheel、sdist；不运行安装冒烟、不上传远端包仓库。
- 多页的已知未完成边界仍见下方清单及 Changelog，现有测试通过不代表跨页失效和热更新隔离已完成。

## 工作树：Dashboard 多 Page 独立分析入口（实施中）

2026-09-10 稳定性专项：热更新语义快照开始覆盖所有 Page 的依赖闭包，
Workspace Change 事件新增按 Dashboard/Page 定位的 `page_changes` 证据，保留原有
Dashboard 汇总。已补非默认页 Python、独立参数、共享 Python、展示改动和删页回归。
Shell 已消费按页证据：未打开页也标记过期，未受影响的当前页不重建 Canvas、不自动查询；
导航元数据刷新保留当前 Page 参数定义，异步导航有 generation 保护。
事件消费游标与 Run 返回的已知版本分离，避免新 Run 确认吞掉其他 Page 的事件；
会话恢复以服务端兼容性检查为准，避免旧事件把新结果误标过期。
非浏览器相关 **25 passed**；Chromium 专项覆盖真实代码编辑、切回、重跑、展示编辑、
新增目录和刷新恢复。共享数据保存后的跨页失效提示已接入，整体验收正在进行。

共享数据失效的证据层已接入：每个 Source 执行或命中缓存时记录读取的 mutation epoch，
同一个捕获值同时用于缓存键与 Run diagnostics，避免两个时点读取导致证据错配。
`GET /api/runs/{id}` 与 `/api/session/runs` 返回 `data_outdated_sources`，区分数据变化和
Query 定义变化，不改写历史 Result。两页共用 Source、第三页不依赖该 Source 的回归
证明只标记前两页，重跑其中一页不清除另一页的过期证据，也不隐式执行任何 Query。
Action/Page 相关 **51 passed**，追加共享页 API 回归后 Page **14 passed**。
浏览器已通过现有事件连接接收 Source 版本并提示 Data changed，关闭文件热更新时仍有效。
真实 SQLite Chromium 回归 **1 passed，19.04 秒**：三页执行、保存局部更新、相关页过期、
无自动查询、刷新恢复、显式重跑；保存中离页只有已发送动作完成，第二个排队动作无回执、
无写入且不改投其他页。既有 Action 浏览器 JSON/Arrow 两种传输专项 **2 passed**。
新增快速切页立即 Run 保护，避免详情加载期间提交上一页；参数编辑器读写绑定所选 Page，
保留整个文件的版本冲突检查，不修改其他页同名参数。Page 非浏览器 **15 passed**。
最终非浏览器复验（参数编辑器与 Worker 管道补丁后）**724 passed，113.30 秒**。
Worker 退出前已发送的最后一帧现在会被读取；查询与 Action 各覆盖成功帧和 EOF，
不重启动作、不把 exit code 0 当成写入成功。此前一次 Action 回执仍为 running 的偶发
失败未确认根因，已增强断言现场，后续完整复验未复现，不声称已定位修复。
完整 Chromium **83 passed、2 failed**：一项是测试未适配平板断点自动收起 Sidebar，
已修正并验证双向切换；另一项为推导候选未加载，单独两次重跑通过，根因仍待观察。
修正后两项合并重跑 **2 passed，23.62 秒**，不将其表述为完整套件一次全绿。
Firefox 专项首轮 **4 passed、1 failed**，修复 Action 同步成功后未清除当前 Page
过期徽标的问题，失败项复验 **1 passed**；WebKit 同一专项 **5 passed**。
新增 Control checkpoint 与滚动恢复断言后，多页专项 Chromium/Firefox/WebKit 各 **1 passed**。
下游日期范围、单选框刷新显示默认值已复现并修复：底层恢复正确，但
`setQueryParameterStates` 原先只同步多选框；现于所有值和 intent 回填后统一同步参数组件，
Run 发送前显式保存草稿并更新 URL。没有新增 DSL 或自动查询。
查询中/完成后刷新各覆盖底层值、可见日期、单选摘要、实际结果及仅一次 Query；
Chromium 两项加既有多页/日期投影组合 **4 passed，62.54 秒**，Firefox **2 passed，36.06 秒**，
WebKit **2 passed，35.88 秒**。相关非浏览器 **85 passed**；新增症状搜索测试后
文档搜索 **18 passed**。CLI `docs --search '刷新 默认值'` 可定位恢复边界与排查方法。
这些是本次补丁后的专项复验，不是重新运行完整浏览器套件；随 0.23.2 本地发行。

边界：Dashboard 统一代码/资源/发布，Page 独立参数和运行状态；不做共享参数、
软链接复用、跨页 Control、页面嵌套或第二套执行引擎。继承现有安静工作台视觉，
只加入 Page 导航与页内操作状态，不重设计 Sidebar。

- [ ] 定义 Page 模型、旧单页投影、引用校验与按入口推导依赖闭包。
- [ ] Page 身份贯穿 Executor/Run/Result、CLI、候选域与缓存，防止同名参数串用。
- [ ] Server 运行、恢复、渐进事件、交互和 Action 按页隔离；切页不自动 Query。
- [ ] Shell 提供 Page 导航、URL/历史、每页 draft/applied/checkpoint/滚动恢复和后台运行状态。
- [ ] 共享数据失效标记相关页过期，未发送 Action 不跨页改投。
- [ ] Bundle 保留整个 Dashboard，报告/分享绑定正确 Page，静态导出不偷偷查询其他页。
- [ ] 补 CLI 文档、双分析路径示例、错误诊断与旧单页兼容测试。
- [ ] 保持渐进式暴露：单文件 Quickstart 不要求 pages/sections；最短 Scaffold 与 docs 创建入口保持简单，多页按独立任务检索；覆盖无 pages 的单页执行与 UI 无多余导航。
- [ ] 非浏览器与真实浏览器验收：不同参数、仅当前页取数、切回恢复、迟到响应、后台完成、刷新/历史、导出。

最终验收必须证明页面与执行同时隔离；只增加 pages 字段或隐藏 Sections 不算完成。
用户已要求升级 0.23.0 并打包；多页未完成边界在发行说明保留，不将本次测试与发行等同于全部功能完成。

已落地第一步：Page 严格模型、独立参数/视图投影、加载时按当前页数据和显式候选入口
裁剪 Source/Transform 注册表。两页可以复用同一个本地 Python 文件，并使用同名不同类型
的参数；重复 Page ID、顶层混入共享参数和未知 Page 明确拒绝。
Executor 已接受 page_id，Run 记录页身份，查询契约/节点缓存指纹包含 Page，跨页 Run
复用明确拒绝。Server 最新 Run 按 session/Dashboard/Page 隔离，交互与 Action 从 Run
读取 Page；会话恢复返回两页记录，页详情元数据不触发 Query。Canvas、报告与共享缓存
记录/解析 Page 身份；全项目校验扫描所有页，单页 preflight 使用本页定义。
CLI run/report 已接入 --page，页面内 canonical Source/View 引用使用按页 Catalog 投影，
不覆盖共享目录索引。Analysis Result 封存 page_id，Result 导出不重查也不接受改投 Page，
--from-result 拒绝串用其他页的参数。前端导航已接入并完成基础 Chromium 专项；跨页失效
提示、热更新与更多异常恢复仍未完成，不能视为整个多页功能已完成。
阶段证据：Page 专项 **5 passed**（含真实 Python Source 执行）；既有 Action/协议与早期
Page 检查组合 **84 passed**。后续仍需完整工作流和浏览器验证。
第二阶段证据：Page 专项 **7 passed**，包含重叠运行不相互取消、会话恢复、错误页 Run
拒绝、正确页 HTML 报告及非默认页参数错误；相关 Action/交互/维护回归 **46 passed**。
第三阶段证据：Page 专项 **8 passed**，增加 CLI 第二页执行、同名 View 解析和已封存 HTML
无查询导出；Page/Analysis/Catalog/单文件回归组合 **84 passed，16.39 秒**。新增 docs pages
按任务发现入口，明确标注浏览器导航仍在开发，Quickstart 不要求 pages。

2026-09-10 进度：Quickstart 收敛为单 YAML 路径，CLI 不要求 --page；无 pages、单个
显式 Page、多 Page 默认入口三种情况均增加执行回归。文档/作者入口/单文件/Page
相关 **111 passed**。Bundle 改为收集所有 Page 的 Workspace Asset 和 Action 资源绑定，
不扩大单页运行闭包、不复制凭据与可写数据；相关 **24 passed**。
Chromium 多页专项 **1 passed，12.57 秒**：重叠运行、按页恢复、URL、刷新、历史导航与
切页不自动查询。测试发现并修复 multiple_input 整数数组被原生 number input 清空的问题。
静态检查通过；未运行完整浏览器套件，未升版、未打包。

## 0.22.4 连续保存与复杂分析联动稳定性

Server Action 使用每 Canvas 有界内存串行队列，保留独立 payload/request ID；
查回执不排队，等待不消耗 RPC 超时。Action 刷新可以接续新 Run，切换查询不得隐式重定向写入。
本地 queued/submitting 与服务端回执分开；未提交有独立错误码，结果不确定或同步失败取消待发请求。
没有自动重试、并发写入、刷新合并或持久消息队列。
保存队列相关非浏览器 **83 passed**；Chromium JSON/Arrow 专项 **2 passed，41.75 秒**。
本次发行不重跑完整浏览器套件，不跑安装冒烟。

范围固定为输出登记/清理、级联候选字段、同 Run 重载 generation、典型链路和故障现场。
不扩张 DSL，不加执行框架、业务推断或自动重试。测试用小型候选目录与服务端全量事实表，
以原生左表/右图、SQLite 示例标注串起交互；没有手动高亮或冗余 value 刷新依赖。

- [x] 输出值、kind、schema 与 signature 同步；错误恢复也触发更新，删除清理元信息。
- [x] 父字段允许从 Control 读取；静态 schema 缺失提前报错，运行时区分 pending/error/field_mismatch/empty。
- [x] 同 Run 重载接续服务端 generation 水位，保留旧请求拒绝规则。
- [x] 候选和 Output 的生产 JS 回归；完整分析/标注链路加入重复运行。
- [x] 完成非浏览器及 Chromium/Firefox/WebKit 的专项验证并记录结果。
- [ ] 继续观察此前表格就绪超时；已有有界慢请求/未完成请求、readyState/Control phase 现场，不认定根因已修复。

最终验证：非浏览器 **700 passed，82 e2e deselected，106.66 秒**；Chromium
**7 passed，96.90 秒**、Firefox **7 passed，103.34 秒**、WebKit **7 passed，98.86 秒**，
各 66 项未选中。这是专项 21 项通过，不是三个引擎的历史全套。每个引擎内完整分析链路
独立重复三轮，另含表格选择、混合运行时及 JSON/Arrow 标注刷新。运行命令与现场说明见
`tests/e2e/README.md`；此前偶发超时本轮未复现，仍待观察。
CLI 文档入口 `docs interaction-stability` 可按“级联候选为空”“右图漏刷”检索。
Runtime 构建一致性、Ruff、JS 语法与 diff 检查通过；保留现有 Starlette/httpx 弃用警告。
上述稳定性修复与连续保存队列一起纳入 0.22.4；未增加 DSL。

## 0.22.3 服务端专用输入的浏览器传输边界

不改 DSL、执行依赖闭包或行数上限。浏览器传输根来自 View/Canvas/候选域和
活动 browser-js 输入；仅供 server-python 使用的 Base Output 留在 Run Artifact。
初始包提供就绪元信息；实时 output_ready 不再无条件下载全量数据。服务端输入
schema 继续由 InteractionExecutor 校验，浏览器调度不再等待这些数据的本地副本。

验证：非浏览器全套 **695 passed，79 e2e deselected，105.30 秒**；Chromium
定向 **3 passed，67 deselected，32.48 秒**。覆盖 100,001 行输入切出 2 行、
正常页面刷新/缓存 Run、混合运行时及 HTML 限制、渐进失败与连续 Run 隔离。
网络请求断言不下载全量输入，反向测试保留浏览器消费者的行数限制。
Runtime 构建一致性、Ruff、JS 语法、diff 检查通过。
发行前完整 Chromium 套件：**78 passed、1 failed，853.65 秒**；失败项是
表格选择联动的视图就绪等待，未经代码或断言修改，单独复跑 **1 passed，12.44 秒**。
因此记录为全套执行加失败项补测，不声称单次全套全绿；超时根因尚未确认。
测试使用已校验的本地 Arrow/地图资源缓存，不改变生产 CDN 行为。
升版后的发行清单、协议和文档搜索检查 **110 passed，1.20 秒**；版本一致性检查通过。
版本升为 0.22.3，构建 wheel、sdist、ZIP 与 SHA-256；保留旧发行包，不远端发布。
按本次范围不跑 Firefox、WebKit 或安装冒烟。

独立待查：绕过 Shell、直接重载同一 Run 的 iframe 时，客户端 generation 从 1
重新开始，可能被服务端以 interaction_generation_stale 拒绝；本轮未修改该契约。

## 0.22.2 选择高亮修复

复现并修复 affectedViews 漏掉 writer_edges 和 mode:value 的问题；选择变化时
发起视图和显式值消费者收到 update，不改数据过滤语义，不增加 DSL。
View Evidence 增加调度 control_revisions 和完成 binding_revisions，Scaffold 保持
同一个 state 并刷新 context，文档解释快照、业务 ID 和 canonical 高亮。
验证：0.22.2 非浏览器全套 **694 passed，78 e2e deselected，104.69 秒**；Chromium
定向回归 **2 passed，67 deselected，26.69 秒**，覆盖点击、外部选择、清空、快速
连续变化和刷新恢复，同时断言 Query Run 与无关视图不变、revision 同步。
Runtime source/bundle、Ruff、JS 语法及 diff 检查通过；已有 Starlette/httpx 弃用
警告保留。本轮未跑完整浏览器矩阵或安装冒烟；版本升为 0.22.2，发行格式为
wheel、sdist、ZIP 与 ZIP SHA-256，本地构建不等于远端发布。

## 0.22.1 保存反馈与诊断

不增加 DSL：成功回执在浏览器同步前通知；Action/刷新/浏览器耗时明确区分范围，
不把 Python 总耗时归因于数据库，不把渲染 Promise 完成声称为屏幕已绘制。
`docs action-save` 提供可运行 SQLite 示例、完整失败恢复、运行版本/applied Run
与资源检查入口；Skill 只增加问题路由。示例采用已有外部 auth 和通用 Python，
不加入业务标注模型、进程池或自动写入重试。

验收：非浏览器全套 **691 passed，77 e2e deselected，104.82 秒**；包括真实
SQLite 示例、冲突/清空/读取、耗时与复用证据，以及 Node 执行生产 Shell 函数的
快速成功/等待/传输失败/刷新失败回归。Runtime 构建一致性、Ruff、JS 语法与 diff
检查通过。已有 Starlette/httpx 弃用警告未改。按用户要求不运行浏览器或冒烟；
发行格式为 wheel、sdist、ZIP 与 SHA-256，本地构建不等于远端发布。

## 0.22.0 本地发行构建

本次范围：Server Actions 及资源根目录修复，发行格式为 wheel、sdist 和 ZIP。
非浏览器基线 **682 项通过**。最近一次完整 Chromium 套件为 **71 passed、6 failed**；
失败诊断捕获 Arrow/Plotly 地图 CDN 超时。随后使用仓库内真实资源缓存重跑这
**6 项全部通过（81.29 秒）**。这是全套执行加失败项补测，不是单次全套全绿。
测试缓存 `.browser-test-assets/` 已被 Git 忽略，不进入发行包；其来源和 SHA-256
见 `tests/e2e/README.md`。默认生产 CDN 行为不变。
按用户要求不再重跑全套，不执行安装或 Query/Report 冒烟；本地构建不等于远端发布。

## 0.21.9 本地发行构建

独立 YAML 入口：`validate/run/serve/report` 编译为现有 Workspace 快照，支持内嵌 code 与 canvas 脚本/样式、显式外部 `--auth`、单看板无 Sidebar。普通 Workspace Schema 保持不变；独立输入增加编译便利语法。首版修改后重启，不做原文件热更新或页面编辑写回。已构建 wheel、sdist、ZIP 及 ZIP 校验和；本地构建不等于远端发布。

打包前验证：非浏览器全套 604 passed；随后默认完整 pytest（非浏览器及 Chromium）退出码 0。Ruff 和 diff 空白检查通过。未单独运行 Firefox、WebKit，也未运行安装冒烟。打包后 review 的修复须另行验证，不能沿用上述结果。

| 工作 | 实现状态 | 已有验证 |
| --- | --- | --- |
| Control 全选候选边界 | 已解析值继续过滤，静态 compact 全选受 choices 约束，显式空选保留 empty policy | Python、Canvas 生产 matcher 与 Web Component 共用回归；非浏览器套件通过 |
| Custom Renderer 多输入过滤 | 表格主输入与 rows 一致，额外 alias 只应用自身绑定，不修改原始 Output | View Controller 与 Web Component 回归覆盖未绑定输入、空结果和非表格输入 |
| 文档状态语义 | 同步 Query default / Control initial、全选边界及 Renderer 输入规则 | 文档、CLI 任务入口和搜索验证通过 |
| 文档搜索 | task 正文、完整匹配优先及部分回退、专题别名、合法结果数量 | 搜索、authoring 与协议相关测试 141 项通过；follow-up command 可执行 |
| 架构与计划清理 | 删除历史迁移清单、重复版本宣称与过期设计，保留当前取舍 | 文档验证不替代发行验证 |

既有修复不改变 DSL；独立输入增加便利语法但不改变编译后的执行协议。既往版本浏览器结果不能代替工作树变更的验证。

## 打包后 review 修复

- 统一外部 Adapter 环境相对路径基准。
- 为 standalone 依赖列表和 Presentation 结构错误提供字段与文件定位。
- 同步当前发行记录，源码归档携带 ARCHITECTURE.md。

修复验证：standalone、Adapter、发行清单、文档搜索及协议相关回归 143 passed；Ruff 和 diff 检查通过。按本次范围保留 0.21.9 重建产物，浏览器矩阵与安装冒烟不属于此次补测。

## 下次交付前

- [ ] 对全选与多输入过滤补齐/运行相关真实浏览器回归，确认 Server 与 portable HTML 一致；未运行部分明确披露。
- [ ] 按最终合并内容执行非浏览器门禁、Runtime source/bundle 一致性与文档检查。
- [ ] 用户确认版本与范围后构建 wheel、sdist、ZIP 和校验和；浏览器矩阵与安装冒烟按本次范围执行并如实记录。

不因文档修改自动发布，不将跳过的验证勾为完成。

## 维护待办

### Server Action：显式 Python 写入与局部刷新（纳入 0.22.0）

设计与验收边界见 [Server Actions](docs/server-actions.md)。这是独立于自动
Source/Transform 的副作用入口，不开发标注专用 CRUD DSL。

- [x] 核验已修复的 auth 路径、standalone 结构校验与发行内容回归。
- [x] Dashboard-local Action 契约、资源别名与刷新目标的提前校验。
- [x] Python 执行、外部资源绑定、事务示例、持久请求回执与重复提交保护。
- [x] Source 失效后的依赖局部刷新、未变分支复用与缓存失效。
- [x] View-only 重绘、applied Run/revision 隔离、保存与刷新分别反馈。
- [x] Server API、Renderer bridge、CLI、standalone/Bundle/热更新接入。
- [x] 更新文档、Schema、Scaffold、AI Skill，并完成相应集成与浏览器回归。

当前进度：已加入 Action 定义、Dashboard 加载、standalone 内嵌 Python 降级、
刷新目标静态校验、资源别名/路径边界和 JSON 输入边界。Python worker 已有真实
SQLite/文件 CRUD、超时未知结果、凭据脱敏及持久回执/重复提交回归。执行器已能
从 applied Run 复用未受影响节点，仅重算指定 Source 的下游，并保持旧 Run 不变。
成功回执与 Source 缓存 epoch 同事务提交，其他会话下次查询也能避开旧缓存；
standalone 更换内容快照后回执仍位于稳定的外部状态目录。

Server API 已接入：显式调用、回执查询、单独重试刷新；包含容量限制、同源检查、
RunManager applied Run 保留及新旧 Run 原子隔离。已覆盖保存成功但刷新失败、
刷新重试不重复写入、View-only 不查库、迟到请求及检查与启动之间的竞态。
Worker 还会执行启动前捕获的代码和声明依赖，避免等待期间改文件改变实际写入。

Renderer 已接入 `context.actions`，提供调用、回执查询和刷新重试。Shell/Canvas
同步更新 Run 身份，先准备数据再按 Output 变化局部更新，保留草稿参数与无关 View
实例；不全局取消未受影响的 Interactive Transform。静态 HTML 写入入口不可用。

作者入口已齐：`docs server-actions`、writeback 搜索、`schemas server-action`、
`scaffold server-action.python`、`inspect context --focus action:<id>`，以及
`actions invoke/status/refresh`。CLI 调用同一 Server API，不另建执行器、不自动
重试写入；Scaffold 默认拒绝执行，待作者实现业务逻辑。Skill 明确 AI 作者路由、
外部资源与显式写入授权边界。事务文档示例经真实 SQLite 更新/冲突回归验证。
Bundle 携带 Action 代码/helper 与待配置资源名，不复制外部可变文件、凭据或回执；
Action 代码/helper 热更新归为 Canvas 变化，不使只读 Query 失效。

2026-09-08 最终验收：非浏览器全套 **676 项通过**（77 项 e2e deselected）；
Chromium、Firefox、WebKit 各 **2 条 Action JSON/Arrow 专项通过**，覆盖局部更新、
草稿保留、无关 View、仅重绘 View、传输失败后重试、连续写入与只读导出。
Runtime source/bundle 一致性、Ruff 与 diff 检查通过。已有 Starlette/httpx 弃用
提示仍在，未修改依赖。逐项证据见 Server Action 设计文档的 Acceptance evidence。
以上是功能开发阶段的专项证据，不是完整三浏览器套件或安装冒烟；后续发行验证见本页 0.22.0 记录。

资源绑定复核后的修复：File Adapter 省略 `root` 时，runtime config 复用正常
`resolve_path` 的配置基准目录并传递绝对路径；Action worker 拒绝未解析的 root，
不再将其转为 `None/`。新增 6 项回归先复现失败、修复后通过，覆盖外部 auth 文件、
auth 目录、Workspace 三种入口的实际文件 CRUD、越界拒绝及 worker 防御检查。
修复后非浏览器全套 **682 项通过，77 项 e2e deselected**；后续浏览器与打包范围见本页 0.22.0 记录。

### AI 开发效率：有证据再下结论

评测工具位于 [tools/authoring-evaluation](tools/authoring-evaluation/README.md)，与正式 CLI 和发行包隔离。

- [ ] 在同模型、客户端、权限与时间预算下，对固定任务进行重复、随机顺序的 Dataviz / standalone HTML 成对试验。
- [ ] 保存原始 JSONL、环境、验收、input/output Token、首次成功率、修正轮次与耗时。
- [ ] 根据真实 friction 改善 focused context、docs 和 Scaffold，不预设节省比例。

### 对外发布准备

- [ ] 维护者决定许可证并添加 LICENSE；许可证未定不阻塞本地开发，但阻塞正式对外授权。
- [ ] 添加 CONTRIBUTING.md，说明安装、测试、Runtime/Component 变更与 PR 验收。
- [ ] 正式 GitHub Release 提供发行包、SHA-256 与对应 CI 记录；本地打包不等于远端发布。

## 按真实需求触发，不是开发承诺

- 原始大表 View 的服务端分页或按需 Record Batch：先证明实际瓶颈，不能从候选 Lookup 或聚合基准外推。
- Binary Artifact 上传、远程 URL 抓取及源文件自包含快照：先明确持久化、权限与可复现需求。
- Workspace Python helper：少量复制允许存在，只有收益超过导入、hash、缓存和 Bundle 生命周期成本时再评估。
- 输出级 Transform 执行计划：先使用已有输出签名与独立 Transform，没有重算成本证据不增加 DSL。
- 新日期粒度、实体控件或图表：先验证已有组件、Scaffold 与 Custom Renderer，避免重复能力。

## 持续验收规则

1. 为真实正确性、易用性或排障问题增加工作；文件或类的数量不是重构目标。
2. 跨 Runtime 共用 conformance expected，生产代码与生成 bundle 同步，不在不同 runner 各写一份答案。
3. Query Parameter、Control、Result 与临时诊断保持各自 owner；迟到请求、失败和取消不得覆盖新状态或推进 applied evidence。
4. Source/Domain SQL 保持 Dashboard-local，静态文件使用 Workspace Asset；Bundle 创建独立快照，不合并或覆盖已有 Workspace。
5. 文档与 CLI/Schema 一致，说明边界和理由；完成过的迁移不留作待办，未验证行为不写成保证。
6. 分别记录实现、测试、打包与发布状态，浏览器测试和安装冒烟不能互相代替。

当前不增加通用网页开发器、共享业务 SQL、隐式跨 Dashboard 依赖、第二套执行/图表引擎、多租户沙箱或 ChatBI 重构。领域取舍由 ARCHITECTURE 维护，不在计划重复展开。

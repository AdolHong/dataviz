# 异步时序与生命周期专项

目标：不改 DSL，以可控时序验证操作中途同步、旧响应隔离、页面／组件销毁；
同时核对级联初始化与保存刷新边界。不是等待下游报错，也不靠加 sleep 或自动重试。

## 覆盖盘点与验收清单

| 边界 | 证据入口 | 验收结果 |
| --- | --- | --- |
| 输入中途同步 | components/test_checkbox_sync.py、test_radio_sync.py、test_inputs.py | 单选组复现 3 项失败后修复；鼠标／空格／方向键与替换候选、组合输入的节点及光标保持通过 |
| 旧响应不能覆盖新选择 | components/test_renderer_races.py、extended/test_parameter_domains.py、core/test_queries.py | 迟到 mount 成功与异常、Lookup 旧选择元数据和迟到失败均不覆盖新状态；慢切页不阻塞新导航 |
| View 生命周期 | components/test_renderer_races.py、extended/test_renderers.py、extended/test_control_state.py | waiting/cancelled/unavailable 作废挂载；销毁后异常不回写；pending 失败清理；update 结束清理最终 state；首屏 Plotly purge；真实 Plotly/Perspective、Server/HTML 链路通过 |
| Transform 生命周期 | tests/test_async_transform_lifecycle.py | prepare 后不启动已销毁任务；execute 后不填缓存；publish/fail 不发送迟到通知或再次修改 Output |
| 级联就绪 | core/test_controls.py::test_server_compute_waits_for_required_control_domain | ready/empty/error 三种可控门闩场景通过；独立分支仍可运行 |
| 保存与刷新 | core/test_actions_and_analysis.py | 增加宿主确认前不发送写入的确定性门闩；排队、跨页、刷新失败只重试刷新继续通过 |

## 修复前证据

- Renderer 终态未作废进行中的 mount，迟到成功覆盖 waiting/cancelled/unavailable。
- Renderer catch 只检查 generation，适配器销毁后迟到异常仍写入错误状态。
- Firefox 小型组件复现 8 项中 7 项失败：`.test-evidence/async-renderer-before.log`。
  增加终态失效计数和统一过期判断后该组 8 项通过：`.test-evidence/async-renderer-after.log`。
- 更强的资源测试在第一阶段修复上再现 5 项失败：`.test-evidence/async-renderer-resources-before.log`；隔离旧 body、清理 pending 失败及延后 update 清理后 10 项通过于 `async-renderer-resources-after.log`。
- Transform 的 prepare/execute 销毁竞态：`.test-evidence/async-transform-before.log`，2 项失败。
- Radio 同步丢操作／焦点：`.test-evidence/async-radio-before.log`，3 项失败。
- 首屏 Plotly 绕过统一挂载：`.test-evidence/async-bootstrap-before.log`，销毁后 states=1、purges=0；修复后 states=0、purges=1。
- 核心矩阵的 WebKit 保存场景首次失败保留于 `.test-evidence/20260913T043451403392Z/failures/webkit/f7985e2d161fae8b/`：图表已显示，但宿主尚未提交 Run，Action 被拒绝。
  第一次握手探针误用了 module 私有函数（`async-action-handshake-before.log`），不是产品复现；改为扣住真实宿主消息后，`async-action-handshake-repro.log` 确认确认消息前队列已经发送。原队列现等待身份匹配的宿主确认。

## 验证范围与复用边界

- 三浏览器组件阶段验证：各 33 passed，`.test-evidence/20260913T043436001929Z/`。
  首屏路径修复后再跑受影响 Renderer：各 14 passed，`.test-evidence/20260913T044329331063Z/`；其余组件没有再改，复用前次结果。当前组件总数 34。
- 三浏览器核心首次运行：Chromium 16 passed、Firefox 16 passed；WebKit 15 passed / 1 failed，`.test-evidence/20260913T043451403392Z/`。
  保存握手修复后，只重跑相关 3 项／引擎，全部通过：`.test-evidence/20260913T044037662602Z/`。
  原失败仍保留，不将两次运行合称“最终完整核心矩阵一次通过”。
- Renderer 真实生命周期及 applied generation：各 3 passed，`.test-evidence/20260913T043543950121Z/`。
  首屏路径归一后相关 Server/HTML 生命周期再验证：各 2 passed，`.test-evidence/20260913T044334269923Z/`。
- Lookup 旧响应隔离：各 2 passed，`.test-evidence/20260913T044115595547Z/`。
- 非浏览器 runtime/action/documentation/authoring/Skill 与专项检查：158 passed，1 条既有 Starlette/httpx warning，`.test-evidence/async-lifecycle-final-contracts.log`。
  首屏归一后 runtime/authoring/专项/浏览器分层检查 91 passed，`.test-evidence/async-lifecycle-bootstrap-contracts.log`。
- Ruff、JS 语法、生成 Runtime 新鲜度和 diff 空白检查通过；没有全量浏览器重跑、版本变更、打包或远端发布。

## 长期边界

这是上表边界的确定性覆盖，不承诺所有异步排列、任意第三方 Renderer 都无缺陷。
mount 返回 state 前就抛错的资源、永久不结束的第三方 Promise，以及作者直接操作全局 DOM／网络，仍需要作者清理；平台不引入新 DSL 或强制终止任意 JavaScript。
组合输入测试验证合成事件下节点／值／光标保持，不冒充真实操作系统输入法验收。
本轮按 impeccable 的稳健性原则保留操作目标、焦点与既有视觉；无 CSS 或主题调整。
CLI `docs renderers`、`docs server-actions` 与配套 Skill 已补充异步边界和清理职责；原有 revision／生命周期诊断保留，没有新增全局遥测系统。

版本仍为 0.25.2；以上是未发布工作树的专项验收，不改变此前 0.25.2 安装包。

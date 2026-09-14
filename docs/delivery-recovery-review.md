# 交付、风险与故障恢复审查

基于已打包的 0.25.9 继续审查；下面的新改动尚未打包，不以评分作为验收。
不新增 DSL、不修改业务数据库，发现具体缺口才修复。

## 交付判断与恢复边界

本轮是源码的增量可靠性审查，不是一次新版本发行验收。已确认的断流、状态读取挂起、
保存宿主 HTTP 占用不释放以及恢复测试提前结束问题已修正；不能将这些修复算进现有
dist/0.25.9。下一次打包仍按 `docs/versioning-and-release.md` 核验产物；本轮不上传、不绕过 CI。

| 情况 | 恢复方式 | 保留的定位信息与限制 |
| --- | --- | --- |
| Query 显示 Unconfirmed | 使用 Retry status 重查原 Run，完成后采用原快照 | Run ID、Page、实际服务版本；不重复 Run，不把未知当失败 |
| 保存未确认 | 用原会话、原 request_id 查询 actions status | Dashboard、Action ID、request_id；禁止换 ID 盲目重写，无法查证时核对业务库 |
| 已保存但刷新失败 | 同一 request_id 调 actions refresh；客户端展示失败另查 View | succeeded 回执、refresh.run_id、View 诊断；刷新成功不等于浏览器已完成绘制 |
| 提交前 action_not_submitted | 修复连接或上下文后由用户重新提交 | 此次宿主未发送写入；不同于 POST 后的 action_response_unknown |
| 浏览器停滞 | 先保留阶段/步骤/堆栈证据，再按必要范围复现 | 旧 Firefox 导航停滞尚无根因；定向通过不能抹掉历史失败 |

其他已知边界：HTTP 超时不回滚服务端 Python；自定义代码可能已产生外部副作用。
回退软件包也不会回退业务数据库，应先核对未确认写入，并备份业务数据及运行记录，
再在隔离环境确认旧包与当前 DSL/数据兼容；不要用覆盖安装或删除 `.dataviz` 代替恢复。
本机只有 examples，不能用样例测试承诺生产负载、任意自定义 Renderer 或长期运行可靠性。

因此目前可以给出“相关恢复路径已验证”的结论，不能给出“所有平台零风险”或“新包已可发布”
的结论。旧 Firefox 风险须在发布记录继续披露；公开发行门禁没有降低。

## 已修正

1. CLI Controls 文档仍描述菜单 Revert 和搜索不影响全选，与当前组件不符。
   已对齐 Select results / Clear results、保留搜索外选择、远程分页完整性限制，
   区分菜单动作与 Query snapshot Revert。文档搜索回归 21 项通过。
2. Shell 的 Query EventSource 永久关闭时没有恢复动作。现在仅对当前 Run、当前连接
   重查回执；CONNECTING 继续原生重连，迟到的旧连接不影响当前 Run。
3. 重查回执若返回 queued/loading，旧代码会提前清掉 pending Run。现在保留身份，
   用 Unconfirmed / Retry status 继续查询状态，不重新 POST，也不发送 DELETE。
4. 永久断流可能同时丢失 Canvas 渐进输出事件。确认原 Run 完成后重新加载该 Run 的
   已完成快照，使图表恢复；不会重新查询数据。此恢复可能重置尚未完成查询期间的
   Canvas 临时交互，不承诺断流后保留任意自定义 Renderer 内存状态。

## 验证及首次失败

- 新增非终态/永久断流回归修复前 3 项失败：`delivery-stream-before.log`；修复后通过。
- 最终状态/文档定向 29 项通过：`.test-evidence/delivery-stream-final-checks.log`。
- 三浏览器核心各 16 passed：`.test-evidence/delivery-stream-core.log`。
  此次核心在最后的“断流后强制采用完成快照”分支补丁前执行；正常路径未变，复用结果。
- 原完成读取失败浏览器用例三引擎通过。新永久断流用例首次误用模块内函数造成测试错误，
  改为公开 Run API；之后 WebKit 发现 Ready 但图表仍 loading，属于真实恢复缺口，补齐快照采用。
- 最终永久断流用例三浏览器各 1 passed：`.test-evidence/delivery-stream-snapshot.log`。
  使用 HTTP 204 令真实 EventSource 永久关闭，确认状态与表格恢复、查询 POST 始终只有一次。
  首次证据保留在 `delivery-stream-browser.log`、`delivery-stream-browser-fixed.log`，没有删除失败。

未重跑完整矩阵，未声称旧 Firefox 导航停滞因此修复；它与本次确定性断流不是同一个已证实问题。
当前工作树和 dist/0.25.9 不是同一份代码；本轮审查结论见文末。

## 排障入口的安全默认值

通用 troubleshooting 原先将 Source/Transform 失败的第一步写成重新 run，容易在尚未查清
结果时重复取数。现改为先检查已有 Result；需要复现时才显式执行，并指向兼容 Artifact 复用约束。
新增查询 Loading/Unconfirmed、保存未确认、保存后刷新失败、未提交队列取消四类症状，
指向原有 status/refresh 入口，区分未提交、未知与已保存，不默认回滚或自动重试。
同时说明 CLI/Server 版本可能不同、先保留身份与时间，以及分享日志前脱敏。

验证使用真实 docs CLI 与搜索入口，并执行文档中的关联 topic，防止不可用的指引被发布；
同时运行 Action CLI 的既有状态/刷新契约测试。日志 `.test-evidence/delivery-recovery-guidance.log`。
本轮仅改文档和其回归，没有增加自动写入、查询或浏览器操作。

## 状态读取悬停也必须可以恢复

完成状态 GET 原先没有客户端等待上限。现在仅此 GET 使用 AbortController 与 30 秒计时器；
请求完成或失败都会释放计时器，超时进入既有 Unconfirmed / Retry status，保留原 Run ID。
只中止 HTTP 读取，不发送 DELETE，不重提 Query，不更改 Source/Action 超时策略。
浏览器后台挂起时不承诺精确墙钟 30 秒，也不将该上限当作数据库执行预算。

- 定向状态与文档回归 34 项通过：`.test-evidence/delivery-status-timeout-checks.log`。
  修复前失败保留于 `delivery-status-timeout-before.log`；计时器及 abort 回归修复后通过。
- 三引擎分别覆盖完成读取失败、永久断流、真实 fetch 不返回直到 30 秒客户端取消：
  各 3 passed，`.test-evidence/delivery-status-timeout-browser.log`；状态与表格恢复、POST 计数仍为 1。
- 最终代码的三浏览器核心各 16 passed：`.test-evidence/delivery-status-timeout-core.log`。
  此次包含上一轮最终的断流快照采用分支代码，不再仅复用分支补丁前核心证据。
- JavaScript 语法与 diff whitespace 检查通过。未执行完整矩阵、未打包或上传。

## 收尾审计发现的待修项

相关状态、Action CLI/队列/持久化、Live、View 失败、文档与发布证据回归共 80 项通过，
日志 `.test-evidence/delivery-final-audit.log`。最终三引擎核心 summary 均 exit 0、timed_out=false。

但代码审计仍发现 `handleServerActionMessage` 的 HTTP 请求无等待上限：Canvas 的 RPC
超时不能中止宿主的 fetch，宿主 `pendingServerAction` 只在 finally 释放，永久挂起的请求
可能使后续保存持续被拒绝。现有轮询 deadline 也只能在两次 HTTP 请求之间检查。
需对该宿主 HTTP 链路补确定性故障回归和有界等待，并保留“超时不代表服务端写入回滚”的语义。
该审计发现的修复与验证见下节；不能以这次 80 项通过代替后续新增路径的验证。

## 保存宿主 HTTP 挂起修复

宿主的预检、POST、轮询与输出下载现在共用从调用开始计算的 290 秒 HTTP 等待预算，
早于 Canvas 300 秒 RPC 截止。finally 清理计时器和自有占用；不重试写入、不取消服务端工作。
invoke 提交前超时返回 action_not_submitted，提交后返回 action_response_unknown；
已经得到 succeeded 回执时继续保留它，将客户端刷新失败单列。WebKit 返回通用
AbortError/code 20 时使用原始 abort reason，避免丢失这一分类。
这是 HTTP 等待保证，不声称能中止任意自定义 Renderer 的 JavaScript 挂起。

- 五处挂起（预检、POST、轮询、输出下载、status）在修复前失败；修复后与原保存测试共
  11 项通过，进一步的 Action/CLI/文档检查 46 项通过。最终 WebKit 原因归一化后 11 项再次通过。
  日志 `delivery-action-host-before.log`、`delivery-action-host-after.log`、
  `delivery-action-host-final-checks.log`、`delivery-action-host-reason-unit.log`。
- 浏览器使用真实 SQLite 写入，等待提交后让 HTTP 响应挂起，再触发仅测试中捕获的宿主
  290 秒回调；不实际等待五分钟、不改变执行/轮询或 Canvas RPC 计时器。
  校验 unknown、原 request ID 查回执成功、revision=1、POST 仍只有一次。
  Chromium/Firefox 通过见 `delivery-action-host-browser-polled.log`；WebKit 的通用中止原因
  问题修复后单独通过，见 `delivery-action-host-webkit-reason.log`。
- 核心 Chromium/WebKit 各 16 passed；Firefox 15 passed、1 failed（完全透明背景 RGB 字符串
  不同，首次 trace 中其他视觉属性相同）。仅归一化 alpha=0 的颜色，失败用例定向通过，
  见 `delivery-action-host-core.log`、`delivery-action-host-firefox-style.log`。
- 首次新浏览器用例的等待与请求计数时点错误全部保留，不混作产品缺陷；同时发现
  Playwright wait_for_function 的 async predicate 并不可靠地轮询 Promise 解出的条件，
  新用例已用有截止时间的异步读取循环替代。进一步扫描还发现三处同样写法：保存丢失响应
  后恢复、永久断流后查原 Run、资源服务等待 Run ready；已全部替换，不能用此前通过证明等待正确。

## 恢复等待证据补强

上述三例改为 await evaluate 的状态轮询，只有最终状态匹配才结束，截止后明确抛错。
保存恢复仍检查 SQLite revision=1 和写入次数=1；查询恢复仍检查原 Run、表格 ready 和
POST 次数=1。资源服务直接返回达到 ready 的 Run 身份，避免等待与取身份分成两次请求。
每次读取本身挂起由现有阶段 watchdog 兜底，不把循环截止时间当成 HTTP 超时。
此轮没有修改产品行为，也没有为通过降低断言或扩大重试。

三浏览器定向各 3 passed（总 9 项），均 exit 0、无超时：
`.test-evidence/20260914T153053333368Z/summary.json`。
测试说明已记录 async predicate 的陷阱与正确等待方式。未重跑无关全套。

当前未打包，也没有重新声称完整矩阵一次通过。旧 Firefox 导航停滞仍为独立未解释事项。

## 本轮收尾核验

2026-09-14，在最终产品代码上运行以下相关非浏览器回归，共 83 passed（4.62 秒）：

```sh
.venv/bin/python -m pytest -q -o addopts= tests/test_run_request_races.py tests/test_action_host_timeout.py tests/test_action_save.py tests/test_action_cli.py tests/test_action_journal_faults.py tests/test_live_disposal.py tests/test_live_output_failure.py tests/test_view_sync_failure.py tests/test_documentation_search.py tests/test_ai_release.py
```

首次命令误写不存在的 `test_action_save_feedback.py`，退出 4、未执行测试；更正为实际
`test_action_save.py` 后得到上述结果，不将收集失败算作产品失败或通过。
`git diff --check` 通过；源码 CLI 的 `docs troubleshooting --format json` 可以取得恢复指引。
浏览器证据按上文复用最后一次受影响范围验证，不宣称最新全套或远端 CI 已通过。

本轮已完成有明确证据的缺口修复、恢复验证与风险说明；没有待执行的本轮测试。
当前不存在足够证据继续修改 Firefox 导航实现，保留原始失败及取证入口，等待新的复现证据，
不通过增加无依据重试掩盖它。本结论不等于生产认证或下一次发行门禁通过。

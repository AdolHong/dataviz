# 异步竞争、失败恢复与资源清理审查

基于 0.25.8 工作树；本轮不升版、不打包。保留上一轮已有修改，不重写已验证的数据契约。

## 1. 异步状态竞争

确定性复现：开始取消 Page A 的 Run，在 DELETE 回包前切到 Page B。
旧实现无论取消成功/失败，都把 A 的消息写到 B 的 Header，失败时还改写 B 的按钮。
现在仅更新所属 Runtime；只有当前仍是该 Runtime 才更新页面。
另外检查 Run ID，防止旧取消回包改写同页后来的一次 Run。

`runDashboard` 增加 queryRequestInFlight 检查，避免函数重入绕过禁用按钮重复 POST。
现有导航 generation、参数查询 AbortController、Transform request identity、Renderer generation
继续负责阻止旧响应提交；本轮没有另建状态体系。

证据：`tests/test_run_request_races.py`；修复前两个可控回包案例均失败，日志
`.test-evidence/async-review-cancel-before.log`；修复后通过。
三浏览器 core 包含慢 Page/lookup 被新导航取代、跨 Dashboard 导航和独立 Page 查询；
extended Worker 场景覆盖连续 Control 变化、取消后清除 updating、超时后恢复。

## 2. 失败后的恢复

发现完成事件后的 GET /api/runs/{id} 没有异常处理。网络失败时 pendingRunId 不清除，
状态留在 loading，事件流已结束后也没有可靠的重查入口。

现在显示 Unconfirmed / Retry status，保留原 Run ID。点击只重新读取该 Run 的完成状态，
不重新 POST，不盲目取消。读取成功走原有提交逻辑，恢复正常按钮及视图。
迟到失败/成功都须匹配 pendingRunId；切换到其他页时不修改其 Header。
这不把“取不到回执”称为“计算失败”，也不假装成功。

证据：快速测试验证重查只发 GET；真实浏览器注入 503，恢复后确认 Ready、表格可见且 POST
总数仍为 1。首次浏览器测试因按钮含隐藏文字失败，改为断言 data-run-label；保留首次日志，
不改产品代码、不放宽业务断言。已有 progressive_failure_and_consecutive_run 验证失败后
重新 Run 可恢复，无需手动刷新网页。

## 3. 资源清理

发现 Runtime.dispose 未显式关闭 Canvas Live EventSource，也未终止 JSON Output 下载。
浏览器销毁 iframe 通常会收回 Realm，但不能替代公开 dispose 的契约。
现在 Runtime 持有 Live cleanup，销毁时关闭连接、中止下载、清空引用；迟到下载与事件被隔离，
已销毁 Runtime 不能重新 connectLive。正常 Run 结束关闭流时仍允许已开始的 Output 下载完成。

快速测试循环 30 次，断言连接归零、signal aborted、重复 dispose 幂等，甚至忽略 abort 的
模拟下载完成后也不能发布数据。真实浏览器资源案例使用原生 Worker/ResizeObserver 和
真实 Perspective/Plotly，20 轮 empty→restore 比较资源基线；补充 document/window 的
pointerup/pointercancel/blur 监听计数，检查全局手势监听是否随恢复积累。

静态核对：Plotly 全局手势监听有对应 removeEventListener；Viewer observer 有 disconnect；
Worker 终止/Blob URL 回收沿用现有生命周期；Shell 每个 Page 的 Run 流在新监听前关闭旧流，
终态 stream_end 关闭；workspace 仅保留一条监听。Page Runtime 中保留结果是回切恢复策略，
不是本轮擅自清空的缓存。

## 验证与边界

- 定向非浏览器：24 passed，含跨页及同页新 Run 的取消回包隔离，见
  `.test-evidence/async-review-targeted-expanded.log`。
- 三浏览器核心：各 16 passed，见 `.test-evidence/async-review-core.log`。
- 定向恢复/Worker/Perspective 首次结果及定位：`.test-evidence/async-review-extended.log`。
- 状态重查修正测试与真实资源验证：三浏览器各 2 passed，
  `.test-evidence/async-review-recovery-resources.log`。
- 增加全局手势监听计数后的资源结果：三浏览器各 1 passed，
  `.test-evidence/async-review-listener-resources.log`。

本轮是限定主链的审查与确定性故障测试，不证明任意自定义 Renderer 都不会泄漏，
也不代替长时间内存压力测试、真实数据库慢请求观测或完整浏览器矩阵。
历史 Firefox 停滞仍需新的阶段证据；本轮通过不表示已定位它。

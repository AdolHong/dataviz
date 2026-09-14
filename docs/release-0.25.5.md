# 0.25.5 本地发行验收

日期：2026-09-14。Server、Share 与导出 HTML 统一 W Controls / E Parameters，
包含组合键、帮助和无障碍提示。Q/R/Esc/? 不变，无 DSL 变更；配套 Skill 继续随 wheel 发布。

## 完整运行与失败处理

- 非浏览器全套：804 passed、149 deselected，180.86 秒；一条现有 Starlette/httpx
  弃用 warning。日志 `.test-evidence/full-20260914-nonbrowser.log`。
- 三浏览器完整矩阵：`.test-evidence/20260914T043149475213Z/`。
  Chromium 149 passed（466.57 秒）；Firefox 140 passed（555.86 秒）；
  WebKit 139 passed / 1 failed（469.19 秒）。九项固定 Chromium CLI 用例不重复运行于另两引擎。
- WebKit 失败为 `test_three_surface_renderer_pending_error_and_recovery`：
  测试看到 View loading 后立即调用尚未创建的 `releaseAuditInitial()`。
  loading 也包含输入准备阶段，不保证 Renderer validate 已开始。
  仅修改测试：等待 Renderer 自身设置的就绪标记，再验证 loading、pending、error 与恢复；
  没有固定等待、自动重试或修改产品实现。WebKit 定向复验 1 passed（4.89 秒），
  覆盖 Server/Share/HTML，日志 `.test-evidence/full-20260914-webkit-renderer-recheck.log`。
  首轮日志与 trace 保留；不是首轮全绿或修正后全量重跑声明。
- 本轮之前修正的 Share/server-Python 测试不再继承 browser-js 示例的 1 秒超时，
  新增正常与慢冷启动两种情况，使用默认服务端预算并输出完整错误回执。
  专门的硬超时/取消测试保留，已包含于本轮非浏览器全套。

使用经哈希校验的本地浏览器资源缓存，不代表验证了 CDN 可用性。
升版只追加发行与安装包检查，复用上述产品测试；未声明远端 CI、多 Python 版本验证或 PyPI 上传。

# 0.25.4 本地发行验收

日期：2026-09-14。包含 Output 下载隔离、初始化退出保护、浮层引用释放与 Perspective
异步 Worker 清理完成计数；不改 DSL。完整修复证据见 `stability-boundaries-workstream.md`。
配套 Skill 仍由根 dataviz-skill.md 构建进 wheel。

## 完整运行与失败处理

- Python 3.12 非浏览器全套：801 passed、2 failed、149 deselected、1 条现有 Starlette/httpx
  弃用 warning，184.85 秒。日志 `.test-evidence/release0254-nonbrowser.log`。
  两项为旧测试：队列缺宿主就绪前提、导出断言匹配已删除的 bootstrap 代码。
  更新测试并保留排队/初始化契约，相关分组 78 passed（23.17 秒）：
  `.test-evidence/release0254-targeted.log`。未因此重跑完整非浏览器套件。
- 浏览器完整矩阵 `.test-evidence/20260913T155321353638Z/`：
  Chromium 149 passed（539.46 秒），WebKit 140 passed（551.26 秒），
  Firefox 139 passed / 1 failed（655.37 秒）。九条固定 Chromium 的 CLI 用例不在另两引擎重复。
- Firefox 窄屏控件测试在打开 Controls 前没有关闭保留的模态 Parameters，Header 被遮挡。
  修正显式关闭前提；三浏览器关联复验 Chromium/Firefox 各 2 passed。
  WebKit 关联复验另发现 ready 可能是降级表格，不能作为真实 Perspective 已创建的证据；
  增加真实实例就绪等待后 WebKit 两项通过（45.92 秒）。没有放宽 Worker 必须创建并销毁的断言。
  日志 `.test-evidence/release0254-choice-recheck.log`、
  `.test-evidence/release0254-webkit-choice-final.log`，首次 trace 全部保留。
- 升版后发行检查 24 passed：`.test-evidence/release0254-packaging-tests.log`。

仅测试前提/断言在完整运行后调整，产品行为未再修改。以上不是一次全绿或修改后完整矩阵重跑声明。
本地包不代表远端 CI、多 Python 版本门禁或 PyPI 上传完成。

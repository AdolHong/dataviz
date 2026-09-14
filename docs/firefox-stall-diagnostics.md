# Firefox 停滞与测试运行器加固

2026-09-14。针对 `.test-evidence/20260914T124717490599Z/firefox.log` 的 9 个完成标记。
当时进程采样显示 Python/greenlet 等待 Playwright，但没有用例阶段记录；
可能停在第 9 项清理或第 10 项执行，不能据此认定为页面或 Firefox 产品缺陷。
这两项位于 `core/test_navigation.py`，定向复验通过不等于解释了旧停滞。

本轮不改产品 Runtime，而是修复测试运行器无界等待和诊断信息不足：

- 记录用例及 collection/setup/call/teardown/sessionfinish 阶段，不再只剩点号。
- 每阶段默认 180 秒，Python faulthandler 独立输出堆栈并失败退出。
- 父进程兜底覆盖启动、收集及驱动失联；超时标为 124，不自动重试。
- 只清理该测试进程拥有的进程组和已追踪后代；进程组信号被拒绝时按进程身份兜底。
- 清理正常退出的遗留子进程；不要求失联浏览器还能成功截图或结束 trace。
- 嵌套诊断 pytest 不覆盖外层阶段记录，不改变 CI 用例选择和通过门禁。

使用 `scripts/test_browsers.py` 获得这些保障；直接 pytest 不会自动启用本监护机制。
完整命令与证据文件名见 [浏览器测试说明](../tests/e2e/README.md)。
原始超时探针失败日志保留在 `.test-evidence/firefox-watchdog-contracts.log`；
进程组信号兜底修正后的回归见 `.test-evidence/firefox-watchdog-contracts-final.log`。
真实 Firefox 导航定向及三引擎小型用例见 `firefox-watchdog-navigation.log`、
`watchdog-three-engines.log`（均位于 `.test-evidence/`）。

最终验收：16 项工具契约通过（`firefox-watchdog-all-contracts.log`），Firefox 导航与
失败截图/trace 的嵌套诊断 3 项通过（`firefox-watchdog-final.log`），三引擎组件各 1 项
通过（`watchdog-three-engines-final.log`）。未跑完整矩阵，未升版或打包。

边界：旧停滞的具体 Playwright 调用未能从历史证据还原。解决的是无限等待、
证据缺失和残留进程，而不是宣称消除了 Firefox 内部所有卡死。

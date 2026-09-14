# 0.25.10 本地打包记录

由 0.25.9 增加一个 patch。包含查询永久断流恢复、原 Run 状态重查及 30 秒读取上限、
Server Action 宿主 HTTP 链路 290 秒预算，以及恢复文档和测试等待修正。
不改 DSL；配套作者 Skill 继续随 wheel、sdist、发行 ZIP 提供。

## 复用证据及边界

最终相关非浏览器回归 83 passed；三浏览器恢复等待定向各 3 passed。
公共运行时改动后的核心及 HTTP 挂起测试结果与首次失败记录见
[交付与恢复审查](delivery-recovery-review.md)。这次仅升版和本地构建，不重跑完整矩阵，
不声称远端 CI 通过，不上传 PyPI。

旧 Firefox 导航停滞仍未解释；打包不代表修复。HTTP 超时不代表服务端写入回滚，
保存未知必须按原 request_id 查回执，不能盲目再次写入。

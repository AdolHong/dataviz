# 0.25.0 发布验证

2026-09-12，按用户要求从 0.24.13 升级到 0.25.0。仅构建本地产物，不上传远程仓库。

## 浏览器首轮

三个浏览器均执行完整 `tests/e2e`（各 118 项）：

| 浏览器 | 通过 | 失败 |
| --- | ---: | ---: |
| Chromium | 95 | 23 |
| Firefox | 97 | 21 |
| WebKit | 94 | 24 |

原始日志位于 git-ignored `.test-evidence/0.25.0/{browser}.log`，合成数据失败 trace 位于 `/tmp/dataviz-0250-failures`。这些结果不能描述为首轮全绿。

## 测试前提修正

- 单 Dashboard fixture 显式进入 Dashboard URL，不再假设根路径自动打开第一个看板；保留根路径留空与历史恢复的产品行为。
- 侧栏允许贴齐视口底部，窄屏点击遮罩会关闭；保留菜单边界、内部滚动、键盘和 ARIA 断言。
- 伪造消息测试使用不启动第二个应用的同源空白 iframe，先监听 load 再插入；仍验证错误来源与过期 frame token 均不能写入状态。
- Runtime 浏览器 fixture 改为 module scope，避免后续独立 Playwright 测试嵌套同一个同步事件循环。

入口等 16 项在三个浏览器复测通过后，测试自身的空白 iframe load 竞态导致等待挂起；停止这三次进程，修正监听顺序后续跑。后续每浏览器查询恢复/诊断时间线 3 项及消息隔离/窄屏边界 2 项通过。没有将中止的进程描述为完整套件通过。

真实 Perspective 仍使用 CDN，无模拟替换或延长断言超时；Arrow 和地图使用现有已验证本地缓存。

## 最终补测与限制

- Chromium：画廊三端 3 passed；真实 Perspective 三端/双屏宽 2 passed。首轮失败项均有后续通过记录，不代表再次完整运行 118 项。
- Firefox：窄屏 Perspective 通过，但宽屏独立串行确认仍失败，20 秒内未 ready；不能声称全绿。
- WebKit：最后串行补测 5 passed、2 failed。画廊三端与 lasso 通过；窄屏 Share 的 Perspective 初始化超过 15 秒，退化为普通表格（`created=0`）；导出 HTML 的 box select 手势后，选择轮廓未在 20 秒内清除。
- 初次并行与后续串行结果均保留，不把偶发失败简单归因于网络，也不把模拟 Table fallback 当作真实 Perspective 通过。
- 发布/版本定向非浏览器检查 25 passed；变更文件 Ruff 与 diff 检查通过。CLI 专项的完整非浏览器证据见其独立记录，本次没有重跑完整非浏览器或多 Python 版本矩阵。

**结论：提供用户要求的 0.25.0 本地构建包，但三浏览器发布门禁尚未全绿。** 剩余问题是 Firefox/WebKit 的真实 Perspective 加载，以及 WebKit 导出图表框选清理；未在本次测试/打包任务中扩大为渲染器修复。

## 构建边界

构建 wheel、sdist、pip-installable source ZIP。核对包版本、Skill 与源码字节一致、前端资源齐备，并排除本地凭据和运行缓存。安装检查使用临时 target 加当前环境已有依赖，不等同于三个产物各自进入全新依赖 venv 的完整发行门禁；没有远程上传。

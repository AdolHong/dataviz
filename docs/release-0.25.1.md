# 0.25.1 浏览器可靠性与测试流程

状态：2026-09-13，最终代码的完整本地门禁通过，进入 0.25.1 发行构建。三个浏览器均是各自完整运行，不以定向重试或历史绿灯替代完整门禁。

## 修正与简化

- `scripts/test_browsers.py` 统一资源准备、三个隔离引擎并行执行、日志与失败证据；可用 `--jobs 1` 串行诊断。失败仍继续其他引擎，最终退出码保留失败，不自动重试，不覆盖已有日志。
- CI 每个引擎复用相同入口，以资源清单哈希作为缓存键，命中后仍逐文件验证。配置和入口 6 项检查通过；没有执行远端 CI。锁文件项目版本从遗漏的 0.24.12 同步到 0.25.1，未改依赖版本，`uv lock --check` 通过。
- `tests/e2e/assets.json` 固定真实 Arrow、地图、Perspective 5.4.0 JS/WASM/Worker 资源及 SHA-256；下载一次、每次校验，不替换真实渲染器，不改变生产 CDN 配置。
- 删除 Runtime page fixture 内重复的资源配置，集中到共享 fixture；精确 page/context 路由同时覆盖页面与 Worker，其他网络策略不变。
- 保留真实三端（Server、Share、导出 HTML）、双屏宽、Control 联动及 Worker 清理断言；过时的根路径自动选择、侧栏几何与 iframe 测试前提已在前一轮修正，未恢复旧产品行为。
- 为导出图表手势增加仅包含事件点数、轮廓数和模式的失败诊断，不记录业务值。
- 完整测试暴露 Multiple Input 的真实竞态：无关 Control 的回执触发整表单同步，删除尚未填写的新增行。新增确定性回归在修复前失败（预期 3 行、实际 2 行）；组件改为值不变时保留 DOM/草稿/光标，值改变才重建。修复后该回归与画廊三端 4 passed。
- 第二轮完整矩阵暴露同父域内 Query Parameter 的选择竞争：旧 Lookup 的 selected_items 被用于修正新选择。延迟响应回归在修复前将“深圳”错误恢复成“全部”；修复为核对发起时的选择快照，变化后重新查询元数据再协调。新回归和原级联恢复场景在三个浏览器各 2 passed。
- Firefox reload 边界曾无法通过旧 FrameLocator 定位已正确绘制的历史值；失败截图为“1”且页面提示正确。测试改为检查当前 iframe 文档中相同的值，并重新获取 frame 定位，保留不自动查库、显式刷新后为“2”的后续断言；未更改产品恢复逻辑。该场景定向通过后，仅 Firefox 重跑完整套件。
- WebKit 的真实框选诊断发现：散点图等待 `plotly_selected` 时，径向图开始 `newPlot`，其内部 purge 清掉共享节流回调。Managed chart service 现在等待选择完成再初始化／销毁其他图表；取消、失焦及释放后无完成事件的情况有释放路径。不修改 Plotly 压缩包或 DSL。回归在按住真实框选／套索时请求挂载另一张图，验证挂载延后、选择事件有点、Control 提交及轮廓清理；三引擎各 2 passed。
- Firefox 表格排序测试先滚动到表格、获取并确认按钮焦点，再验证重绘后的焦点与横向滚动保持；不再把尚未获得焦点当成“丢失焦点”。三端定向 3 passed，原有排序／输入法／分页断言不变。

## 证据

- 最终完整非浏览器：776 passed、1 条现有 Starlette/httpx 依赖弃用 warning，212.52 秒，日志 `.test-evidence/0.25.1-nonbrowser-release.log`。CI 入口调整另有 6 项配置／缓存／执行器检查通过；`uv lock --check`、Ruff、`git diff --check` 及三个改动 JS 的语法检查通过。
- 缓存接入后的 WebKit 定向验证：Perspective 三端/两个屏宽 2 passed（14.88 秒）；真实框选/套索 2 passed（26.22 秒）。这是定向结果，不作为完整矩阵通过声明。
- 首次 `.test-evidence/0.25.1-full` 运行暴露上述产品缺陷；修复后主动停止该旧代码运行，不把其中的局部通过拼接为完整通过。
- `.test-evidence/0.25.1-final` 暴露第二个缺陷，保留失败 trace，不将修改中途的运行视为最终门禁。
- 前轮门禁 `.test-evidence/0.25.1-gate`：Chromium 120 passed；WebKit 119 passed / 1 failed（上述框选竞态）；Firefox 的独立完整重跑 `.test-evidence/0.25.1-firefox-gate` 为 119 passed / 1 failed（上述焦点测试前提）。这些不是最终发行通过记录。
- 最终代码完整门禁 `.test-evidence/0.25.1-release-gate`：Chromium **120 passed**（1318.03 秒），Firefox **120 passed**（1379.75 秒），WebKit **120 passed**（1331.41 秒）；统一入口退出码 0，`summary.json` 的三个退出码均为 0，无跳过／失败，不合并定向通过数。三个引擎并行总用时约 23 分钟。

测试通过 pytest 的 `pythonpath = ["src"]` 使用工作树代码；项目虚拟环境另有旧安装包，不将其 CLI 输出当成发行版本证明。发行构建检查 wheel／sdist／ZIP 的版本、CRC、私有文件排除与 Skill 内容；另将 wheel 安装到独立临时目录，检查真实导入路径、CLI 版本及 Skill／前端资源。该安装检查复用现有 Python 依赖环境，不等于远端 CI 的多 Python 版本、全新依赖环境安装矩阵。

缓存只控制已知上游资源的字节，不证明公网 CDN 可用性或所有网络场景可靠。0.25.0 的未通过证据保留在独立记录中，不回写成通过。

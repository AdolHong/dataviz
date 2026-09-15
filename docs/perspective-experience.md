# Perspective 分析体验优化

流式 Source 暂缓；此轮不新增流式 DSL，也不改变 Run 的不可变数据语义。

## 行为边界

- 非空数据更新复用 Viewer/Worker；连续更新最多保留当前替换和最新数据，不排队刷新中间版本。
- 空筛选立即显示现有空状态，隐藏但保留 Viewer；恢复数据后沿用用户透视配置。
  不向 Perspective 执行可能长时间等待的空表 replace/flush。退出 View 才释放保留资源。
- 同一标签页内，配置按文档路径、Dashboard、Page、View、列名、作者配置和 Perspective 版本隔离。
  查询重建 iframe 后恢复兼容配置；变更作者配置/列结构不套用旧偏好。
- 仅保存单 Viewer 的分析配置白名单，不保存数据行、table 名称或 Worker 句柄；上限 65536 字符。
  浏览器禁止 sessionStorage 时不阻断分析。不能恢复的配置回退作者默认值。
- 这是浏览器偏好，不是 YAML 修改或已发布报告配置。导出/Share 不自动继承另一文档路径下的偏好。
  多面板 Workspace 的布局保存不属于此次单 Viewer 配置契约。

## 验证证据

- `tests/test_perspective_disposal.py`：Worker 终止完成后才计为释放；替换未完成时连续三个版本仅处理首个和最新两个版本。
- 三引擎相关契约测试各 4 passed：`.test-evidence/20260915T023714535140Z/summary.json`。
  这些使用 Perspective 接口替身，验证宿主的复用、空状态、保存恢复、降级、销毁和 HTML 行为。
- 真正 Perspective 引擎 Chromium 1 passed：`.test-evidence/20260915T023751847761Z/summary.json`；
  验证空筛选后 Viewer 身份相同、分组排序不丢失，重新 Run 恢复配置，以及 HTML 空状态恢复。
- 真正引擎 Firefox/WebKit 各 1 passed：`.test-evidence/20260915T023855214661Z/summary.json`。
- 三引擎核心各 16 passed：`.test-evidence/20260915T023856401682Z/summary.json`。
- 单元与文档定向回归 27 passed；未运行全量扩展矩阵。
- 最终加强为与默认值不同的按 day 分组、orders/revenue 列重排及 revenue 降序；
  真实引擎和接口替身在三个浏览器各 2 passed：`.test-evidence/20260915T024104615373Z/summary.json`。
- 首次两项失败为新增断言误插入降级用例，修正位置后仍有一个真实复用失败：
  通用 empty 分支先销毁实例。已将保留逻辑接入该分支。
  原证据保留于 `.test-evidence/20260915T023402808348Z` 和 `.test-evidence/20260915T023511340866Z`；
  修复验证 `.test-evidence/20260915T023641335626Z`。

以上为开发阶段证据，当时未升版、打包或执行远端 CI；后续发布验收见 [0.26.0 记录](release-0.26.0.md)。

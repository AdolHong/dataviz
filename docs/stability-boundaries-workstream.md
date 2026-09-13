# 稳定性边界审查：保存、切换、级联与资源

日期：2026-09-13。基于 0.25.3 工作树；本轮未升版、未打包，不改 DSL 或视觉。
按 AGENTS.md 保留首次失败，先确定性复现，再做对应修复。采用 impeccable harden 的
错误状态与资源释放约束，不扩展视觉设计或新增业务功能。

## 四项审查结论

| 方向 | 审查与实证 | 结论 |
|---|---|---|
| 保存恢复 | 检查持久回执、幂等、未知结果不重放、刷新重试；新浏览器测试先用真实 POST 受理写入，再丢弃响应，刷新页面后按原 ID 查询回执，SQLite revision 仍为 1 | 当前检查范围未发现新缺陷；保留故障注入回归 |
| 快速切换隔离 | 核对 navigation generation/AbortController、Canvas identity、页内 Run 与状态；验证运行中切页、切回状态、过期 Canvas 消息、候选请求失败不阻塞导航 | 页面级保护有效；同一 Runtime 的旧下载缺少隔离，已修复 |
| 动态级联 | 核对初始化与必选域等待，测试 ready/empty/error、EMPTY/FAIL 后恢复、父级快速切换、reload 与迟到 lookup 错误 | 现有级联场景通过；初始化跨 await 后仍继续操作已销毁 Runtime，已修复 |
| 长期资源 | 检查 Renderer/Worker/observer 所有权、Output promise Map、浮层注册表；重复创建、打开、移除选择框 40 次，检查注册表回到基线；验证 Renderer Server/HTML 生命周期 | 发现浮层强引用残留、destroy 不完整及已完成下载 Promise 保留，已修复 |

## 复现与修复

- `tests/test_output_transport_lifecycle.py` 的 11 项初始均失败：旧下载成功/失败分别与
  remove、replace、commit、dispose 交错；初始化暂停在 restore、hydrate、apply 后销毁。
  首次证据 `.test-evidence/stability2-transport-before.log`。
  50-output-store 使用当前请求身份判定是否仍可发布；提交/替换/移除使旧下载失效，
  finally 只释放自己的 Promise，不删除新请求；初始化在等待后检查 disposed。
  最后另加两项检查确保当前下载/发布错误仍传播，不被过期任务抑制逻辑吞掉。
  60-renderer-disposal 清空下载 Promise Map。底层下载不被强制取消，迟到结果失去发布权限。
- `tests/e2e/components/test_overlay_lifecycle.py` 初始两项均失败：40 次替换残留 40 条记录；
  destroy 后重注册仍拿到已删除旧记录且关闭/点击状态错误。
  首次证据 `.test-evidence/20260913T050646993264Z/`。
  浮层销毁关闭面板、撤销自身监听并清除 owner 标记；MutationObserver 在 DOM 移除后
  清理已断开的 owner，不清理同步移动后仍连接的控件。

## 验证范围

- 非浏览器：`tests/test_runtime.py`、`tests/test_async_transform_lifecycle.py`、
  `tests/test_output_transport_lifecycle.py`、`tests/test_server_actions.py`、
  `tests/test_server_action_api.py` 共 **82 passed**；日志 `.test-evidence/stability2-contracts.log`。
  现有一条 Starlette/httpx 弃用 warning，不涉及本次修复。
- 三浏览器组件层各 **36 passed**：`.test-evidence/20260913T050718052810Z/`。
- 三浏览器核心层各 **16 passed**：`.test-evidence/20260913T050801059635Z/`。
- 三浏览器扩展定向各 **5 passed**：`.test-evidence/20260913T050828104234Z/`。
  包含过期 Canvas 消息、参数级联/恢复、候选失败时导航、迟到 lookup 错误及 Renderer Server/HTML 生命周期。
- 新增丢响应/刷新后查回执场景三浏览器各 **1 passed**；入口日志
  `.test-evidence/stability2-recovery.log` 记录各引擎证据目录。
- 加强同步移动控件不被销毁的断言后，浮层两项三浏览器各 **2 passed**：
  `.test-evidence/20260913T051147707789Z/`。
- 作者契约、文档搜索与浏览器分层检查 **89 passed**：
  `.test-evidence/stability2-final-contracts.log`。
- 最后收窄错误处理到下载阶段，避免吞掉 publishOutputs 的真实异常；Output/Runtime
  **30 passed**：`.test-evidence/stability2-transport-errors-final.log`。
  此改动之后只复验受影响的保存刷新（JSON/Arrow）与动态域三态，不重跑整个核心层；
  三浏览器各 **5 passed**，最终结果记录于 `.test-evidence/stability2-transport-core-final.log`。
  各分组有重叠，不相加作为独立用例数。Ruff、JS 语法、生成资产一致性和 diff 检查通过。

## 边界，不作过度承诺

- Canvas 队列仍是内存队列，不保证关页前未提交项会继续执行。重新打开页面后核对回执需要
  保留原 action/request ID；本轮没有引入持久化客户端任务箱或自动重试写入。
- 真实响应丢失与 reload 已验证；没有声称覆盖所有网络代理行为、操作系统强杀或服务器断电。
  SQLite 事务、未知回执与服务重建的保护另由现有 Python 契约回归覆盖。
- 40 次循环验证确定的引用容器不积累，并结合 Renderer 资源生命周期测试；这不是两小时
  内存基准，也不承诺任意 Custom Renderer 的第三方全局副作用都能由平台回收。
- 本轮没有重新执行完整扩展矩阵、所有 Python 版本或远端 CI；不把定向通过写成全量通过。

## 第四项补充确认：资源循环与实际清理完成

第四项的结论是：**已识别的资源所有权问题已修复；确定的资源容器在重复操作中不累积**。
这不是对任意看板、任意第三方 Renderer 或连续数小时总内存曲线的无限保证。

补充审查发现，上轮 `test_managed_renderer_lifecycle_matrix_in_server_and_export`
主动注入了 Perspective 契约替身（terminate 为空），因此只能验证生命周期契约，不能作为
真实 Perspective Worker 释放的证据。现在该测试移除替身，使用经过校验缓存的真实
Perspective 5.4.0 JS/WASM/Worker 与真实 Plotly，不依赖 CDN 可用性。

- 保留原 Server、Share、HTML 流程；Server 内增加 **20 轮清空→恢复**。
  每轮核对活跃原生 Worker、有效 ResizeObserver、Renderer 注册实例、Perspective
  创建减销毁数、下载 Promise 数量与基线完全一致，不用容差放宽累积断言。
- 原生资源包装器保留实际执行，仅计数；ResizeObserver 同时计入 unobserve 最后一个目标
  和 disconnect。循环中等待 Perspective 已完成清理，不用固定休眠或自动重试掩盖问题。
- 上轮 **40 次浮层创建/打开/移除** 与同步重挂、清理后重注册测试仍保留，证明注册表释放与
  触发监听不重复。未进行所有第三方事件监听器的通用堆分析。
- 真正的代码修复：Perspective Worker terminate 可能返回 Promise，原代码没有等待，
  过早报告 disposed。现在等待其完成才更新销毁计数；错误仍走既有错误处理。
  `tests/test_perspective_disposal.py` 用可控 Promise 验证等待和幂等。
  原行为确定性失败证据 `.test-evidence/stability4-termination-before.log`；
  测试只在内存恢复原函数语句，不回滚或改写工作树。

验证与失败归类：

- `.test-evidence/20260913T153709521377Z/` 和 `20260913T153828002650Z/` 的 Worker 增长
  来自契约替身不关闭原生 transport，不能用它们证明产品内存泄漏。
- `.test-evidence/20260913T153921548585Z/` 为计数器漏计 unobserve 的测试问题，已修正。
- 使用真实资源且计数器完整后，三浏览器各 **1 passed**，每条含 20 轮循环及三种展示环境：
  `.test-evidence/20260913T153957768312Z/`，耗时 Chromium 14.33s、WebKit 20.14s、Firefox 40.27s。
- 相关非浏览器 **85 passed**：`.test-evidence/stability4-contracts.log`。
- 最后加强 Runtime 结束后的原生 Worker、Worker URL Map、下载 Promise 清零断言，
  三浏览器各 **1 passed**（Chromium 14.07s、WebKit 28.74s、Firefox 38.73s），
  定向结果入口为 `.test-evidence/stability4-final.log`。Ruff、JS 语法与 diff 检查通过。

本次不升版、不打包，不改 DSL 或视觉。impeccable harden 仅用于清理与错误状态边界。

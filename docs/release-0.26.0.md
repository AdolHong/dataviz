# 0.26.0 本地发布审查

从 0.25.12 升级一个 minor。范围：本地 CSV/SQLite 与单 YAML 入口、用户级状态目录、
自动/手动执行、文件热更新与可选定时刷新；Perspective 空筛选保留实例、更新合并与标签页偏好恢复。
流式 Source 暂缓，没有新增流式契约。

## 审查修复

- 自动更新在 debounce 期间转入后台，不再提交；保留一次最新更新，在重新可见时恢复。
- Perspective 更新循环结束到 Promise 完成之间的新数据，不再被交接边界丢弃。
- 补充确定性回归；定向 20 passed，Ruff 与 `uv lock --check` 通过。
- 版本同步至 pyproject、Runtime、lock、README 与 plan。

## 全量验证

- 全量非浏览器首轮：868 passed、11 failed，日志与 JUnit：
  `.test-evidence/release-0.26.0-nonbrowser.{log,xml}`。
- 11 项为需要同步的测试/文档前提：计划未更新版本、旧源目录缓存路径、旧无参数函数签名截取，
  以及旧 Perspective replace 文本断言。没有取消原来的语义断言。
- 修正后 AI release、CLI 渐进入口与请求竞态相关 45 passed：
  `.test-evidence/release-0.26.0-followup.{log,xml}`。
- Runtime 相关补测 17 passed：`.test-evidence/release-0.26.0-runtime-followup.{log,xml}`。
- 三浏览器全量矩阵记录：`.test-evidence/20260915T024849645275Z/summary.json`。

- 全量 Chromium：173 passed、1 failed；WebKit：164 passed、1 failed。
  共同失败为旧生命周期断言要求空选销毁 Perspective，与本版保留实例设计冲突。
  更新为验证实例保留，保留 20 次资源计数检查及最终销毁检查；三引擎定向各 1 passed：
  `.test-evidence/20260915T030232009340Z/summary.json`。
- Firefox 首轮停滞于查询完成后刷新页面的结果断言，退出 124；queries 模块诊断复现同一位置：
  `.test-evidence/20260915T025619160596Z/summary.json`。
- 查询恢复测试补齐 iframe 就绪前提：在稳定的顶层上下文等待表格 ready，再进入子帧验证。
  保留参数值、结果内容及仅执行一次查询的断言，没有增加超时或重试。
  Firefox queries 模块 4 passed：`.test-evidence/20260915T030248902171Z/summary.json`；
  正常日志模式三引擎刷新用例各 2 passed：`.test-evidence/20260915T030356223584Z/summary.json`。
  这支持测试对子帧加载时机的等待不足；不宣称已证明或修复 Firefox 驱动底层停滞根因。
- Firefox 未执行部分续跑：109 passed、3 failed，证据 `.test-evidence/20260915T030334642930Z/`。
  两项 Perspective 失败为 Worker 模块仍请求 CDN（trace 有 CORS 失败），绕过缓存后降级为基础表格。
  Firefox 缓存 fixture 仅将精确 bootstrap import 替换为已校验的真实 Worker 字节，保留原生运行与销毁。
  两项加契约用例共 3 passed：`.test-evidence/20260915T031813691158Z/summary.json`。
- completion-timeout 失败期间本机发生 Idle Sleep（11:06:05–11:09:17，共 192 秒），
  对应 trace 从 26109ms 跳到 216526ms；系统证据 `.test-evidence/release-0.26.0-sleep-evidence.log`。
  未改产品或超时阈值，隔离复验三个完成状态分支 3 passed：
  `.test-evidence/20260915T031749185012Z/summary.json`。这次按环境中断处理，不宣称修复产品缺陷。

- 缓存 fixture 相关补验 6 passed、1 failed：`.test-evidence/20260915T032041136494Z/`。
  配置保留测试在 restore 后立即空选，未确认配置已完成渲染；增加 flush 并在空选前
  读回断言分组确为 day，再保留原有恢复后配置断言。Firefox Perspective 模块 5 passed：
  `.test-evidence/20260915T032157859952Z/summary.json`。
  最终三引擎真实/契约空选恢复用例各 2 passed：
  `.test-evidence/20260915T032259020802Z/summary.json`。
- 文档搜索与发布约束补测 47 passed：`.test-evidence/release-0.26.0-docs-final.{log,xml}`。

完整验证由首轮与上述必要范围补验共同覆盖，并非声称单次全绿。
安装冒烟与产物摘要另见本地 dist 的发布证据；此文不声明远端 CI 通过。
完整功能边界见 [本地数据](local-data-acceptance.md) 与 [Perspective](perspective-experience.md)。

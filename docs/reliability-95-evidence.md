# 9.5 可靠性目标：证据台账

目标是收集足够证据支持 9.5 的自评，不通过反复主观加分宣布完成。
自评不是客观认证；本文件没有降低此前“可以放心依赖”的标准。

## 判定原则

- 已知静默数据错误、标注丢失/重复写、旧结果覆盖新结果或常见操作必须刷新，均阻止达标。
- 本地测试证明被覆盖的行为；不能代替真实使用、跨版本升级或远端 CI。
- 修复数、测试数、重试后全绿不作为评分公式。
- 未发现问题可以不改代码；首次失败必须解释并保留。
- 不擅自收集用户数据或部署遥测，不擅自发布/升级下游。

## 当前证据与缺口

| 维度 | 已有证据 | 尚缺的证据 |
| --- | --- | --- |
| 数据正确性 | JSON/Arrow 固定值、升级样例、筛选/HTML 对照；日期/Decimal 文本/大整数文本选择键三引擎对照 | 更广的业务类型与实际看板升级反馈 |
| 异步与恢复 | 导航竞争、取消隔离、Run 重查、连续选择、失败重跑 | 网络中断组合、实际长时使用故障记录 |
| 写入安全 | 幂等回执、版本冲突、过期 unknown、保存和刷新分离；独立进程竞争、写后退出、回执/epoch 回滚 | 实际部署环境中的长期故障与恢复记录 |
| 资源与性能 | 20 轮原生组件恢复、30 次 Live 销毁、手势监听基线 | 明确数据规模与运行环境下的性能基线、长期操作压力 |
| 升级与发布 | 真实 0.25.6 对照、wheel/Skill 核验、CI 门禁定义 | 当前版本远端 CI 结果、代表性下游多次升级记录 |
| 开发与排障 | CLI 场景搜索、公开输入/状态诊断、失败证据 | 典型任务不查源码的完成记录、真实排障耗时 |

历史 Firefox 停滞仍无确切根因；监护能留证并退出不等于消灭原故障。
上述外部证据尚缺时，不能仅靠更多本地测试宣称达到 9.5。

## 取证路线

1. 先补写入安全的故障注入，检查幂等与不确定结果是否保持安全。
2. 扩大升级取值边界与代表性规模测试；在测试前明确业务断言和测量环境。
3. 查验完整工程门禁的可执行性、现有文档和实际命令的一致性。
4. 汇总仍需下游观察的具体项目；由用户决定部署与提供反馈，不伪造使用时间。

进度以实际日志和可复验测试更新，当前目标未完成。版本仍为 0.25.8 工作树，不发布。

## 本轮取证（2026-09-14）

- 持久化安全与现有 API/发布契约：56 passed，1 个上游弃用警告。
  新增 `test_action_journal_faults.py`：4 个独立进程/16 次同 ID 竞争只有一次受理与一次 epoch 增量；
  写入后进程退出保留 unknown、禁止重放；回执序列化失败同时回滚 epoch。
  日志 `.test-evidence/reliability95-actions.log`。未发现需修改 Action 实现的新问题。
- 三浏览器规模案例各 3 passed：100001 行仅供服务器的数据不下发；12000 行 Arrow/1000 组
  Repeat 的懒加载与现有 750ms reconcile 预算；150000 行聚合不触发 JS 参数上限。
  日志 `.test-evidence/reliability95-scale.log`。这是现有规模边界回归，不是长期性能 SLA。
- 不查实现的当前 CLI 路径：默认 scaffold 生成一个 YAML → strict validate 8/8 → run ready
  （Alpha=12、Beta=19）→ report；返回 reexecuted=false。
  样例 `/private/tmp/dataviz-95-authoring.WkQ73a/dashboard.yaml`，
  Result `result_20260914_142733_81cef0b5e4`，报告摘要日志
  `.test-evidence/reliability95-authoring-report.log`。只证明最短默认路径，不泛化到复杂业务开发。
- 环境误用已解释：裸 `.venv/bin/python -m dataviz.cli` 加载已安装 0.21.6，
  `check_version_drift.py` 能明确诊断；后续 CLI 使用 `PYTHONPATH=src`，没有修改用户安装环境。
  旧 CLI 的 quickstart/standalone 查询结果不作为当前版本缺陷。
- 修正文档真实冲突：versioning-and-release 仍称默认只验 Chromium，现已对齐 CI 三浏览器
  distribution 门禁，并区分本地按影响验证与远端发布门禁。

真实多版本升级/长期使用、当前远端 CI 与历史 Firefox 停滞的证据仍缺；不据此升到 9.5。

## 第二轮取证

用户确认本机只有 examples，没有独立业务看板；因此不再寻找本机业务项目，也不执行生产取数
或保存。样例和合成测试继续作为工程证据，不改称真实业务长期使用证据。

- `test_precise_filter_values.py`：日期、Decimal 精确文本、相邻大整数文本作为原生筛选键，
  连续改选后检查精确业务行，再导出 HTML 检查保留选择。JSON/Arrow 各一项，三浏览器各
  2 passed；不是仅检查类型或画面出现。日志 `reliability95-filter-keys-first.log` 与
  `reliability95-filter-keys-other.log`。数字型 Control 的安全整数限制仍保留，没有改成任意精度计算。
- 修正 multi-page 示例 README 的入口：无历史记录的根地址不会自动打开看板，现给出
  `/dashboards/holiday` 直接地址并说明空状态。
- 启动一次完整非浏览器与三浏览器工程验收，补齐此前分层验证的组合覆盖；
  日志 `.test-evidence/reliability95-full-nonbrowser.log` 与
  `.test-evidence/reliability95-full-browsers.log`。未完成前不记作通过；失败只扩大到必要范围。

## 完整验收与安装检查

- 非浏览器：826 passed、167 deselected，1 个上游弃用警告，234.70 秒。
  后续新增的 lock 版本断言另行定向通过，没有将其冒充为此次全套已执行。
- 浏览器首次矩阵 `.test-evidence/20260914T143106353655Z`：Chromium 163 passed；
  WebKit 153 passed、1 failed；Firefox 在 48 项完成后的多页面导航用例 call 阶段超时，退出 124。
  Firefox 未执行部分另开续跑，排除已执行范围不等于隔离失败或降低 CI 门禁。
  续跑 `.test-evidence/20260914T144136305238Z`：103 passed、2 failed、49 deselected；
  两项失败均为下述 Share/HTML 排序断言，最终定向集合断言已通过。
  至此未执行范围已补齐，但原始导航超时仍未解释，不称为一次完整 Firefox 全绿。
- WebKit 首次失败来自点击后的同步读取，没有等待跨 iframe 的选择确认。修为等待断言后，
  又发现断言不应假定选项排序：Server 与 Share/HTML 的选项顺序可以不同。
  现改为等待准确的选中集合（数量及两个城市分别匹配）；不修改组件来迎合测试顺序。
  首次 trace、排序断言失败及后续结果均保留，不覆盖历史证据。
  最终集合断言在三浏览器各 3 passed（Server/Share/HTML），日志
  `.test-evidence/reliability95-cascader-set.log`；没有重复执行已通过的完整 Chromium/WebKit 矩阵。
- Firefox 导航定向诊断开启 Playwright API 日志后 1 passed，日志
  `.test-evidence/reliability95-firefox-api.log`。没有产品修改，不能宣称停滞已修复；
  原始监护栈仅定位到 Playwright 等待，尚不能判定具体 API 或产品根因。
- 修复真实发布一致性问题：源版本为 0.25.8，uv.lock 自身包仍为 0.25.7。
  `uv lock --offline` 只更新自身版本；`uv lock --check --offline` 与新增版本一致性回归通过。
  发布文档同步说明，不改变依赖版本。
  最后一次发布一致性与文档搜索定向检查 41 项通过，日志
  `.test-evidence/reliability95-release-docs-final.log`。
- 在 `/private/tmp/dataviz-95-install.bd0RbC` 构建临时 wheel、sdist、配套 ZIP：
  wheel 在独立 Python 3.11/3.12/3.13/3.14 环境完成 version、components check、init、
  strict validate 和示例 report；sdist/ZIP 在独立 3.12 环境完成同样流程，另核验 Skill 和 schema 资源。
  日志 `reliability95-install-build.log`、`reliability95-smoke311.log`、
  `reliability95-install312-314.log`、`reliability95-source-install.log`。
  这些是本地安装验收，不是远端 CI，也没有覆盖仓库 dist 中已有发布物或升级用户环境。

当前仍未完整通过三浏览器验收，不能宣布达到 9.5；样例测试也不能补造长期使用证据。

## 固定本地验收样本

没有业务看板时，复用下列现有样例，不另造一套 DSL 或要求用户准备生产数据。
操作中的 Run 只用于样例数据；如本地改过 Adapter 绑定，须先确认仍是样例资源。

| 样例目录 | 固定操作 | 核心判断 |
| --- | --- | --- |
| `examples/minimal-workspace` | 修改最低收入后 Run、区域全选/清空、刷新、导出 HTML | 提交参数恢复；各视图使用同一选择；导出与已运行结果一致 |
| `examples/multi-page-workspace` | 两页分别 Run，改不同参数，来回切页、刷新、浏览器后退 | 参数与结果不串页；切页不额外取数 |
| `examples/feature-showcase` 的 `cascade-explorer` | 多层选择、搜索后选取/清除、右侧面板、Share/HTML | 子级候选协调；保留搜索外选择；三端状态一致且不溢出 |
| `examples/repeat-workspace` | 搜索门店、选择/清空、滚动到更多图表、反复切换 | 懒加载与选择范围正确；不残留旧图、重复监听或无界资源增长 |

写入、断网、进程退出等破坏性场景继续使用 `tests` 的临时 fixture，不向上述样例添加真实写入。
每轮记录代码状态、引擎、首次失败和证据路径；长期累积记录才形成使用趋势，
一次批量循环不称为长期使用。

## Firefox 停滞：补齐步骤留证

原始超时没有记录具体未返回的 API，不能从 greenlet 等待栈推断为 Control 或导航实现缺陷。
新增 opt-in `browser_step` 测试 fixture；只记录静态步骤名和开始/完成/失败，不记录业务参数，
不重置阶段超时。导航用例标记两次 Control apply、reload 和 go_back 四处等待。
这不是所有 API 的全量记录，若最后步骤已完成，只能说明停滞发生在其他位置。

- 监护回归 6 项通过，包含独立进程 setup/call/teardown 超时、正常完成及失败；
  call 被强制退出后保留未完成步骤，退出仍为 124；原有子进程回收断言不变。
  日志 `.test-evidence/reliability95-checkpoints-unit.log`。
- Firefox 导航定向 1 passed、15 deselected，四处步骤均开始并完成，9.46 秒。
  日志 `.test-evidence/reliability95-navigation-checkpoints.log`；步骤记录在
  `.test-evidence/20260914T145041458303Z/firefox.progress.steps.jsonl`。
  本轮为验证新增诊断，不修改产品、不增加重试、不声称原始停滞已修复。

## 达标审计与剩余定位边界

- 已验证的本地证据：数据格式/选择键对照、写入故障注入、异步取消与重查、资源销毁、
  安装格式和 Python 版本矩阵、文档与发布版本一致性。均限于上述具体场景，不是全局无缺陷证明。
- 仍不满足：Firefox 原始导航停滞无根因；没有当前工作树远端 CI 或真实长期使用/升级记录。
  examples 是可重复的工程样本，不补足这些外部证据。
- 额外检查浏览器复用假设：`browser` fixture 为 module scope；原始导航用例前，
  同一实例执行过首页/历史恢复用例。按原顺序只跑这两个 Firefox 用例，开启 API 与步骤日志，
  2 passed、14 deselected，13.42 秒。证据
  `.test-evidence/reliability95-firefox-reused-context.log` 及
  `.test-evidence/20260914T145248880839Z`。
  这一次没有复现，但不能排除更长运行序列或负载相关因素，也不能反证原始超时。
- 当前不再无假设地重复导航用例，不为消除评分阻碍而删除用例、提高超时、放宽断言或改写实现。
  下一次停滞应先核对未完成步骤、API 日志和进程状态，再决定最小复现范围。
  如无新证据，不因自动继续而反复修改文档或新增重复测试；9.5 仍未获证明。

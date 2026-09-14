# 升级验收与排障专项

基线：本地 0.25.6 wheel；目标：当前工作树（从 0.25.7 继续）。
不能把新版本自测、类型字符串相等或后续重试通过替代升级验收。

## 完成条件

1. 固定数据与同一看板分别执行基线和目标，记录真实传输方式、选项值、过滤后业务键、
   图表数据、HTML 导出结果。覆盖日期、Decimal、超安全范围整数；区分预期表示变化与
   业务结果变化。旧版数值碰撞不能作为需要保持的正确结果，必须明确报告。
2. 审查错误降级路径并分类：合法空、pending、失败、取消、缓存保留；对确认的静默错误
   补回归并修复。正常初始化不能被误报为失败。
3. 复用当前诊断/CLI/文档，能定位 View→Output、输入类型/行数/就绪状态、Control 当前值，
   以及等待、缓存、取消和失败原因；以实际查询结果或回归为证据。

## 1. 真实升级对照

执行入口：`tests/upgrade/test_transport_upgrade.py`。使用同一份固定 Parquet、同一看板配置，
分别从真实旧 wheel 与当前源码启动 Server；不是模拟旧类型的新版本自测。
基线 wheel SHA256：`7ad29dfa10447ea7620517bf21a340d792bc464abb8750652b85da3caa2831b4`。
目标为 `fd5d416`（0.25.7）上的本专项工作树，不是另一个已发布包。

| 对照 | 结果 |
| --- | --- |
| JSON，安全整数 | 选项、过滤业务行、数量图、日期图与导出通过 |
| Arrow，安全整数 | 同上；允许下述预期表示变化 |
| Arrow，大整数 | 同上；保留相邻 ID 的区别 |
| JSON，大整数 | 旧版 `unsafe_integer`，原始相邻 ID 已碰撞；当前成功且 ID 精确 |

旧版 JSON 大整数案例无法生成有效的派生图，所以没有伪造旧版导出对照；当前版本仍验证
选择、图表及 HTML。其他案例比较 Run 后重新打开的确定快照，再实际切换商品和导出。
不把此快照验收当作首次实时加载、所有 Share 或所有业务看板的全面验证。

| 字段 | 0.25.6 JSON | 0.25.6 Arrow | 当前 JSON / Arrow |
| --- | --- | --- | --- |
| date | 含午夜时间的字符串 | 毫秒数 | YYYY-MM-DD |
| timestamp | 无时区后缀字符串 | 毫秒数 | UTC ISO 字符串 |
| Decimal | 本样例已是 `1.20` 字符串 | Decimal 底层字数组 | 精确十进制字符串 |
| 超安全范围整数 | 精度损失后报错 | 精确字符串 | 精确字符串 |

业务断言：商品 A 的上海/深圳数量为 10/20；切换 B 后厦门为 7；日期图按日期归一后
仍为 09-12、09-13 的 10/20；选项仍是 A/B。当前原始行在 HTML 中保持一致。
日期/Decimal 直接当作 Control key、任意 JS 算术及旧类型严格相等比较不在本次覆盖中；
不要把精确字符串直接当 Number 做高精度财务计算。Python Artifact 类型不变。

复验命令（需上述真实基线 wheel 和已校验浏览器资源）：

```sh
.venv/bin/python -m pytest -q -o addopts= tests/upgrade/test_transport_upgrade.py
```

这是显式升级验收，不是依赖旧 wheel 的普通 CI 门禁。可用 `DATAVIZ_UPGRADE_BASELINE`
指定同 SHA 的文件位置。默认 Chromium；传输矩阵 4 项通过，证据在
`.test-evidence/upgrade-acceptance-complete.log` 与 `.test-evidence/upgrade-values/*-safe.json`、
`*-large.json`。这些本地证据不随包发布，复验代码保留在仓库。

## 2. 错误降级审查与修复

- 同步 render 抛错：此前只写控制台，会留下旧成功图；现在进入统一 Renderer 错误生命周期，
  清除旧内容并记录 `view_render_failed`。
- Live Output 下载失败：此前只改变 Pipeline；现在传播 Output error，通知依赖视图，
  允许下一次有效 Output 事件恢复，而不是保留旧成功内容。
- Firefox/WebKit 的 Error.stack 可能不含 message：现在保留明确原因，不再只展示调用位置。
- 合法 `[]` 仍是 empty；缺失输入是 pending，行数为 null，不能误报为零行。
- 审查保留的边界：服务端 Output 类型不匹配会抛错；Artifact 写入失败会回滚后重抛；
  Interactive 异常生成失败/取消结果；坏缓存返回 miss 并重新计算，不返回空业务数据。
  取消时 DELETE 的 best-effort catch 保留：本地已中止且旧 generation 被隔离，不伪装新成功。

这是一轮针对输入、计算、缓存、实时发布、渲染主链的审查，不声称扫描消除了整个仓库所有风险。
新增快速回归为 `test_view_sync_failure.py`、`test_live_output_failure.py`，真实浏览器案例为
`test_failed_update_never_leaves_successful_table_visible`。首次失败日志保留在 `.test-evidence/`；
Firefox/WebKit 首次失败明确定位为错误文字缺失，修复后定向验证通过，不靠重试吞掉失败。

## 3. 现有诊断补齐

View 信号沿用现有入口，补齐 Input alias→Output、kind、实际输入类型、行数与就绪状态。
刷新原因区分 `waiting_input`、`input_failed`、`render_failed`、`not_affected`。
Interactive trace 显示当前状态与缓存命中；等待/取消/失败不会继续冒充此前 cache-hit。
检查信号时读取最新 trace，而不只读上次成功渲染的快照。

Control evidence 增加当前 value；refresh 中 control_state 是该次渲染消费的状态。
需要当前值时在 Canvas/HTML 使用公开的 `window.dataviz.control.state(canonicalKey)`。
默认复制诊断仍隐藏控制值、行内容及原始错误文本，仅保留元信息和错误码，避免新增泄漏。
CLI 的 `docs --search '图表没刷新'` 可找到 `interaction-stability` 场景说明；CLI 不假装
能读取另一个浏览器标签页的实时状态。未新增 DSL 或另一套诊断系统。

## 验证范围

- 完整非浏览器阶段：816 passed、161 deselected；后续错误信息和最新 trace 改动另跑相关回归。
- 最终定向单元/诊断/搜索回归：24 passed，包含 queued/loading/cancelled/error 清除旧 cache-hit。
- 三浏览器核心按公共 Runtime 改动运行，Chromium / Firefox / WebKit 各 16 passed；
  结果记录于 `.test-evidence/stability-frozen-core.log`。
- 升级对照 4 passed；新增错误恢复浏览器案例 Chromium 通过，Firefox/WebKit 修复后各通过。
- 不声称跑了本轮完整浏览器矩阵或远端 CI；历史 Firefox 停滞仍不能据此宣称根因已解决。

未升版、未打包。验收提升的是上述边界的证据，不等同于长期可靠性认证。

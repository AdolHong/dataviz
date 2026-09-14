# 输入输出一致性审计（2026-09-14）

范围：当前工作树中 Source/服务端 Python → Artifact → JSON/Arrow → Browser Worker、
原生与 Custom View → 缓存/快照/HTML/Share/CLI，以及 Action JSON 边界。
以下保留原始问题证据，并记录当前工作树中的修复。未增加 DSL；浏览器单元格值的
共同表示是行为变化，升级前需要检查依赖旧的数字时间戳或 Decimal number 的代码。

## 已复现的原始问题（修复前）

| 边界 | 证据与影响 | 建议 |
| --- | --- | --- |
| Custom Renderer 辅助输入 | `view.declarative/controller.js` 的 custom 分支只统一 main；未带 filter 的辅助输入原样传 raw。同一份表在 JSON 下 `inputs.extra` 是数组，在 Arrow 下是 DatavizArrowOutput；main 两种均为数组。给辅助输入增加 filter 还会再次改变其类型。已用真实 descriptor builder 复现。 | 所有声明为 table 的命名输入采用一致的公开表接口，不应由有没有 filter 决定；保留 scalar/object。优先修复。 |
| 日期单元格 | `10-value-contracts.js` 只处理 Date 实例，但真实 Arrow Timestamp.get 返回毫秒数。真实缓存 Arrow 库构造的 2026-09-14 在 rows/columnar 中均为 `1789344000000`；当前 pandas JSON 路径为 `2026-09-14T00:00:00.000`。 | 按 Arrow 字段类型规范化；统一日期、时间戳、时区、精度约定，不能只补 instanceof Date。覆盖筛选和图轴。 |
| 超大整数 | Int64 `9007199254740993` 在 Arrow 被转为字符串；JSON 发数字，JS 解析后会舍入。Python Artifact 保留原值，问题发生在浏览器传输边界。 | 为超出 JS 安全范围的整数制定共同的精确表示；商品 ID 推荐文本。不要以强制 Number 统一接口牺牲精度。 |
| Worker 返回 Frame | `return {main: context.table('rows').filter(...)}` 经过 structured clone 后成为 `{_rows, _columnar}`，prototype 丢失，宿主 `validateInteractiveOutput` 拒绝为非表。已执行真实 Worker handler + structuredClone + 宿主校验复现。 | 输出边界显式支持 Frame→rows，或明确必须 `.rows()`；不要用对象形状猜测用户 object output。 |
| 缓存/快照类型丢失 | Date 经 `datavizCacheClone` / `datavizSnapshotValue` 被 Object.entries 转成 `{}`。Worker 表输出 `[ {when:Date, n:NaN} ]` 在无列 schema 时通过当前校验；Date object output 也被 `datavizJsonCompatible` 判为合法。 | 在进入缓存前规范化或拒绝非 JSON 值；共享一套输出序列化契约，禁止先丢失类型再校验。Map/Set 等同类值需一起覆盖。 |
| 合法共享引用误报 | `datavizJsonCompatible({a:obj,b:obj})` 返回 false，因为 WeakSet 不在离开子树后移除引用；这是共享引用而不是循环。JSON.stringify 可以正常序列化。 | 使用递归栈检测环，分别验证共享引用与真正循环。 |
| 错误输入被当空表 | `datavizTableRows({n:1})` 返回 []；主线程 `data.table`、Frame 构造器也有类似兜底。缺失/pending 输入同样经过该入口，不能简单全局 throw。 | 区分 pending、合法空表、kind mismatch；在有声明类型的边界报错，内部等待路径保留明确状态。 |

## 审计时已有的统一能力与不应强行统一的差异

- 服务端 Python `ExecutionContext.input(tableAlias)` 调用 `table()`，无论上游 list/DataFrame/Arrow，
  最终从表 Artifact 读取 pandas DataFrame；类型不为 table 则拒绝。`context.inputs` 存的是
  ArtifactDescriptor，本来就是元数据接口，不应强行变成浏览器数组。
- Python `normalize_outputs` 将表写入统一 Artifact，支持 DataFrame、Arrow Table、rows 和列映射，
  有 kind/schema 检查；不是每一种上游格式都要求用户自己分支。
- 原生表格/Plotly 的行路径和 Custom main 已通过 `data.table(...).rows()` 统一容器；
  但仍受上述单元格值差异影响。CLI browser 提取复用 tableRows，不能因此认为日期/整数问题消失。
- browser-js 新增 `context.rows(alias)` 已统一行数组入口，`context.table(alias)` 统一 Frame；
  原始 inputs 的传输相关类型仍保留。只有采用稳定入口的代码获得这层保证，且它不解决日期值差异。
- Worker filter 对数组与 columnar 分别处理；这种内部实现差异合理，公开的值和筛选结果应一致。
- Server Action payload/result 采用严格 JSON 检查，拒绝 Date、bytes、自定义对象、NaN、非字符串键等，
  有大小限制和循环检查。它不应该自动接受 DataFrame；标注结果与分析表是不同契约。
- image/file 的浏览器展示值和服务端文件 Artifact 是不同能力，已有 destination 校验；
  不宜“统一”为可写路径，也不能取消 HTML 对 server-python 的离线执行限制。
- Share 和 HTML 共用生成的 Worker/Runtime 实现；同源代码避免分叉，但上述序列化问题会随之传播，
  不能用“三端使用同一文件”代替输入值/快照回归。

## 当前修复

1. Custom Renderer 的主表与未过滤辅助 Arrow 表统一物化为 rows[]；过滤后的表仍为 rows[]。
   scalar/object 保留类型，不因严格 table 入口而破坏合法 Custom scalar。
2. Worker 提供 `context.rows(alias)`；Frame 作为 Named Output 返回时，在 structured clone 前转行数组。
   不将形状类似 Frame 的业务对象猜测为表。原始 `context.inputs` 保留兼容类型，作者应采用稳定入口。
3. Server/HTML JSON 表改为从 Arrow Artifact 读取并统一单元格，Arrow rows/columnar 按字段类型解码：
   date 为日期字符串；timestamp 为 UTC 毫秒 ISO；超大整数和 Decimal 为精确十进制字符串；
   binary 为字节数组；list/struct 递归处理；浮点非有限值转 null。覆盖负 scale Decimal、字典日期和时区。
   无时区 timestamp 不施加本机时区；Python Artifact 及原始 Arrow IPC 的类型、精度不变。
4. 缓存/快照/JSON 检查共用严格克隆：Date、Map、Set、typed array、BigInt、undefined、
   非有限数和循环抛 `interactive_output_not_json_serializable`，附值路径，不先丢类型再校验。
   这与 Source 表传输时的规范化不同：浏览器业务输出必须主动给出 JSON 值。
   递归栈区分合法共享引用和循环；未发布 Output 的 undefined 仍可走等待入口。
5. `tableRows`、主线程/Worker Frame 不再把非表对象降级为空表；合法 [] 不报错。
   pending 输入保持原有调度语义，未放宽必选 Control、服务端或输出 kind 校验。

## 兼容边界

- 毫秒 timestamp 是浏览器表示，不宣称保留纳秒；精确金额计算应留在 Python。
- 本轮验证的 Arrow 类型列于上述清单；不声称任意扩展类型、Union、Map、time/duration 都已对齐。
- rows() 是物化及浅行复制，不是任意深层业务对象的隔离副本；大表仍优先列式接口。
- 任意业务筛选返回 [] 无法自动判错。本轮提供类型错误而非承诺逐行跟踪任意 JS 逻辑。
- workspace 迁移配置差异报告不在本轮；不通过强制全局 JSON 或提高浏览器行数上限规避问题。

## 证据范围

审计原始复现：`.test-evidence/io-audit-boundaries.log`。
第一轮修复后非浏览器全套 810 passed：`.test-evidence/io-boundary-nonbrowser.log`。
最终非浏览器全套 807 passed、159 deselected（e2e）、1 依赖弃用警告：
`.test-evidence/io-nonbrowser-complete.log`。三个单元格测试移入浏览器组件层，避免
非浏览器 CI 依赖未下载的本地 Arrow 资源；不是删除测试。该组件文件另有 Chromium
3 passed，`.test-evidence/io-cell-matrix-complete.log`。
后续定向契约 70 passed：`.test-evidence/io-final-contracts.log`。
真实 Arrow 单元格、Worker columnar、快照三浏览器各 1 passed：`.test-evidence/io-rich-cells.log`。
真实 Server/Share/HTML 强制 JSON/Arrow、Worker 返回 Frame，三浏览器各 2 passed：
`.test-evidence/io-three-surfaces-final.log`；不是只比较共用源码。
最终核心三浏览器各 16 passed：`.test-evidence/io-boundary-core-complete.log`。
JSON/Arrow/auto 两侧及 session cache 三浏览器各 5 passed：
`.test-evidence/io-worker-cache-final.log`。
首次新增三端测试遗漏重新打开分享菜单，日志 `.test-evidence/io-three-surfaces.log` 保留。
旧核心轮次 Firefox 在 9 项后停滞，采样显示等待 Playwright，随后人工终止；
`.test-evidence/20260914T124717490599Z/firefox.log` 保留，不计为通过或宣称已修复停滞。

本轮没有升级或打包，也未修改下游业务看板或业务数据库。

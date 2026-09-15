# 本地数据优先入口：实施与验收

最初开发基于 0.25.12；后续发布验收见 [0.26.0 记录](release-0.26.0.md)。公开使用入口为 `dataviz docs local-data`。

## 已实现边界

- standalone Source 使用 `data: <name>`，四个 CLI 入口 validate/run/serve/report 使用相同的
  `--data name=path`；CSV 是 file Source，SQLite 是 sql Source。缺失、重复、闲置、冲突或类型错误
  的绑定报错，不猜测输入。普通 Workspace Source Schema 不增加这些便利字段。
- `inspect data` 输出有界 JSON；CSV 只读取前 256 KiB 并限制行/列/字段展示，SQLite 默认列结构，
  选表才取样，连接只读且有限时，不计算总行数、不把样本类型当完整推断。
- SQLite 使用 backup 收录已提交 WAL；SQL 连接使用 mode=ro 和 authorizer，拒绝写入/ATTACH。
  可信 Python 不因此成为沙箱。输入是查询快照，不是可变标注数据库。
- inline SQL/Python 和自定义 JS/CSS 仍使用既有 code.inline/canvas 契约。独立文件夹可拆代码，
  不要求 workspace.yaml；Pages 与文件拆分是独立维度。
- 新独立任务的快照、缓存和 Result 存放用户级持久目录，可用绝对 DATAVIZ_STATE_DIR 改写。
  回执按原 YAML 身份跨快照复用；已有源目录回执原位保留，避免与仍运行的旧服务分叉。
  不自动清理 Result/回执，不移动旧 Result，按返回的原快照路径读取旧结果。
- report 运行 YAML 与导出 Result 保持不同语义；Result 模式拒绝新的查询/Control/Page/refresh
  参数，不静默忽略，不在缺结果时回退执行。HTML 仍不具备服务端写入能力。
- 两个实际示例见 `examples/local-csv` 和 `examples/local-sqlite`，Skill/README/CLI 文档以本地
  分析为默认路线；外部 auth、Workspace 按需求展开。

## 已有验证

- 相关非浏览器回归 224 passed（44.73 秒），覆盖 standalone、SQL、Adapters、Action、Pages、
  作者文档与 Skill；补充 WAL 和 SQLite 写入拒绝后 local_data 模块 19 passed。
  一个既有 Starlette/httpx 弃用警告，不作为功能通过证据。
- 两例 Server + CLI HTML 三引擎各 2 passed：
  `.test-evidence/20260915T005753458569Z/summary.json`。
  CSV 表格 food/drink 点选会改变趋势且不再次提交 Run；SQLite 查询输出正确渲染。
- 核心三引擎各 16 passed：`.test-evidence/20260915T005833973197Z/summary.json`。
- 新浏览器用例首次因错误的仓库根目录计算而失败，原记录保留于
  `.test-evidence/20260915T005736330789Z`；仅修测试路径后重跑新用例，没有重试掩盖产品缺陷。
- Skill frontmatter 校验与 git diff whitespace 检查通过。示例 SQLite 生成器只创建新文件。
- 参数化 SQLite 导出补测三引擎各 1 passed：
  `.test-evidence/20260915T010227215320Z/summary.json`；Server 默认 6 行，CLI 指定最低收入
  100 的 HTML 为 4 行。首次测试错误地传入裸数值，记录保留于
  `.test-evidence/20260915T010057370842Z`；按既有 canonical `{"value":100}` 契约修正，
  未放松参数校验或修改执行语义。

未进行新的完整浏览器矩阵或远端 CI，不将本次通过当作历史 Firefox 停滞根因已经查明。
HTML 只包含导出时的数据与可在浏览器执行的交互，不监听原始文件。

## 单文件自动执行与热更新（第二阶段）

- 本地 CSV、只读绑定 SQLite、无外部 auth/adapter 的 Python Source 默认打开即分析；
  Python 仍为可信代码，不保证无网络访问或副作用。所有 Page 都必须满足本地条件，
  外部连接或动态参数域默认保持手动。`serve --execution manual` 可显式关闭自动执行。
- 自动模式参数修改合并后执行，仅运行当前 Page；连续修改只排队最新状态，不自动调用 Action。
- 监听原 YAML、引用代码和绑定数据（包括 SQLite WAL）；生成新的不可变快照，
  不改运行中任务的输入。无效编辑保留旧结果并提示，修正后自动恢复，无需重启。
- 已有 Run、导出和 Share 使用原快照；新输入生效前不允许用旧 Run 发起保存。
  `--no-watch` 关闭后台监听，手动 Run 仍读取最新输入。缓存不落到输入目录。

验证记录：

- 相关非浏览器 278 passed，记录 `.test-evidence/standalone-live-nonbrowser.xml`。
- 三引擎核心各 16 passed：`.test-evidence/20260915T020602392983Z/summary.json`。
- 手动模式与连续编辑三引擎各 2 passed：`.test-evidence/20260915T020509641057Z/summary.json`。
- 自动 SQLite、CSV/Python 连续更新、单 YAML Python 失败恢复三引擎各 3 passed：
  `.test-evidence/20260915T020949141821Z/summary.json`。
- 首次浏览器失败包含测试误用私有 JS 函数、把渐进渲染误当 Run 完成；修正测试后，
  连续编辑又发现真实旧结果闪空问题，已修正为保留成功 Run，相关证据保留于
  `.test-evidence/20260915T020156765297Z` 和 `.test-evidence/20260915T020410973736Z`。
- 上述为相关测试与核心矩阵，不是全量矩阵；没有升版、构建或执行远端 CI。
- 收尾的 live-input、文档、作者入口与 Skill 包装相关测试 103 passed；
  Skill frontmatter 校验通过，桌面与窄屏截图确认自动模式使用低强调 Refresh 入口。

## 文件变化与定时刷新

`serve --refresh-interval 10` 显式开启本地 auto 的定时刷新，1–86400 整数秒；
默认关闭，不接受手动模式或普通 Workspace。复用 Run/Source/Transform 链并传递 `refresh`，
避免命中旧计算缓存。HTML/Share 不获得定时查询能力。

只有当前可见 Page 定时刷新；每次任务完成后重新计时，不在慢任务期间累积 tick。
文件/参数变化仍使用既有合并调度，一项运行中任务加一次最新意图；过期结果不覆盖当前结果。
隐藏标签页停止定时器；恢复可见时，已有待执行更新只提交最新的一次，否则重新计时。
Cancel 暂停定时刷新，手动 Refresh 恢复。
完成状态不确定时不新提交，仍需核对原 Run。每个浏览器标签页独立，不是无人值守服务端调度，
不是增量流式计算，也不对可信 Python 提供副作用隔离。

验证：相关非浏览器 101 passed（`.test-evidence/scheduled-refresh-nonbrowser.xml`）。
初次单元回归仅失败于旧 summary 精确字段断言缺少新增 `refresh_interval: null`，已更新。
定时回归 Chromium 首轮 1 passed（`.test-evidence/20260915T022151882671Z/summary.json`）；
覆盖缓存刷新、慢计算跨两个时间间隔不新增任务、两轮文件编辑合并、旧结果保留和取消后暂停。
补充隐藏标签页生命周期后，三引擎 standalone 相关各 6 passed：
`.test-evidence/20260915T022241546315Z/summary.json`。CLI 参数与文档补测 42 passed。
慢任务期间网络提交次数不增长的加强断言，三引擎各 1 passed：
`.test-evidence/20260915T022511200299Z/summary.json`。
本阶段三引擎核心各 16 passed：`.test-evidence/20260915T022348035858Z/summary.json`。
未执行完整扩展矩阵、未升版或打包。

以上为开发阶段记录；后续发布阶段执行的完整测试、审查修复与构建范围以 0.26.0 记录为准。

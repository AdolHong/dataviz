# CLI 渐进式暴露与可靠性专项

状态：CLI 专项完成，2026-09-12。目标是优化 CLI，尤其 Analysis 与看板搭建的渐进式暴露，提高稳定性和易用性；不引入新的分析执行引擎或强制复杂 DSL。专项结束时未升版或打包；随后按用户要求进入 0.25.0 三浏览器验证与打包，另见 [发布验证记录](release-0.25.0.md)。

## 最终验收

| 要求 | 当前实现与直接证据 |
| --- | --- |
| 最短作者路径 | Quickstart、minimal task 与默认 Scaffold 均可生成单 YAML；`test_quickstart_commands_run_without_auth_page_or_workspace`、`test_minimal_task_commands_use_the_same_executable_single_file_start` 实际逐条执行文档命令，得到 ready Result。高级 Workspace profile 的 validate/run/report 原有回归继续通过。 |
| 命令衔接与保护 | `test_scaffold_default_next_commands_handle_quoted_path_and_preserve_files` 实际执行带引号路径的 next，并验证拒绝覆盖；四类 fragment 回归确保仅指向 owning Dashboard，不自动执行片段。 |
| Analysis 发现与理解 | 空匹配 advice、未知引用恢复命令与分层 describe 已实现；新增 discovery/describe 测试禁止 Executor.run，执行恢复命令，并比较 full/include-code 的实际代码。既有正则非法、可信筛选和批量未知引用回归通过。没有自动放宽 trust/visibility 或猜测物理引用。 |
| 执行参数和 Page | 0/1/2 Page 默认选择与显式页运行、页结果导出回归通过；新增四项非法 Page/参数在 Executor.run 前失败。重复参数在 standalone 编译前拒绝；Analysis 失败契约不依赖 Click 内部上下文。 |
| Result 复用 | 特殊路径下实际执行 Result next_actions 并禁止 Executor.run；既有 immutable/pageable/exportable 回归验证分页、原生 Artifact 导出与索引重建不重查；Page 报告明确 reexecuted=false。 |
| 文档和帮助 | documentation.py、dataviz-skill.md、作者与 Analysis 文档同步；run 帮助分组且不增加必填选项；真实执行 Quickstart 与 task 命令防止文档再次分叉。Skill frontmatter 校验通过。 |

最终证据：完整非浏览器套件 **768 passed，1 条依赖 warning**（`/tmp/dataviz-cli-full.log`）；随后仅调整 minimal task 文档路由并追加五项测试，相关作者/CLI 组 **81 passed**（`/tmp/dataviz-cli-audit-targeted.log`）。不把后者描述为全部非浏览器套件再次运行。变更文件 Ruff 与 `git diff --check` 通过。

CLI 专项未改页面 Runtime/DSL，其验收不包含浏览器、发行包或多 Python 版本验证。后续发布阶段的测试不追溯为本专项证据。以下为过程记录，其中历史待办以本节逐项证据为准。

## 验收范围

1. 最短作者路径：无需数据库凭据、Workspace 层级、Page 或浏览器扩展即可生成、校验、运行一个简单看板；按需进入 SQL/Auth、交互、自定义和多页。
2. 命令衔接：生成的下一步命令能在真实目标路径执行，含空格路径；片段不假装独立可运行，不隐式覆盖用户文件。
3. Analysis 发现与理解：默认结果紧凑且体现业务口径；搜索失败、无可信结果、歧义引用给出可行动诊断；完整代码和依赖按需披露。
4. Analysis 执行：单页无需强制 page 参数，多页选择边界明确；参数错误应在执行前暴露；不静默选择错误目标或增加查库。
5. Result 后续操作：预览、检查、导出和报告复用封存结果；下一步命令可靠，不诱发重复取数。
6. 文档与帮助：CLI 帮助、内置 docs、渐进式文档和作者 Skill 的路径一致；端到端测试执行真实命令，不只断言提示文本存在。

## 初始证据

- `docs quickstart` 推荐单 YAML，但 `scaffold --list` 的完整 profile 仅有 minimal/interactive/custom-renderer，均生成 Workspace。
- materialize 后的 Scaffold `next` 原样返回 `<workspace>`；非完整片段的 verify 还会把片段 ID 当作 Dashboard ID。
- `run --help` 有大量同级选项；已有默认 Page 解析，不应为了优化帮助新增强制 Page。
- `catalog describe --detail full --include-code` 的 JSON 与文本输出需要核查：文本分支直接打印 closure 容器，渐进式格式和可读性不足。

逐项以最终工作树及实际命令/测试结果确认完成，未覆盖部分不以已有测试通过代替。

## 第一轮：单文件起步与命令衔接

- `scaffold standalone` 及省略 recipe 默认生成单个 dashboard.yaml，使用可信内嵌 Python 样例；现有 explicit minimal/interactive/custom-renderer Workspace profile 不变。
- 完整 profile 写入后使用实际路径并进行 shell 引号处理，报告写入生成目录；fragment 明示 owning Dashboard 占位符，不用 fragment ID 构造假运行命令。
- 同步 `documentation.py` quickstart/standalone、`dataviz-skill.md` 与渐进式作者文档。Skill 更新按 skill-creator 原则保留按需路由，未创建重复手册。
- 新测试实际执行内置 Quickstart 的生成、校验、运行命令；执行默认 Scaffold 返回的 next，覆盖路径空格/单引号和拒绝覆盖；验证片段不伪装可运行。
- 定向非浏览器：110 passed、1 条现有依赖 warning（`/tmp/dataviz-cli-progressive-final.log`）；`git diff --check` 通过。
- 尚需继续：Analysis 搜索/详情/页面与参数诊断、Result 后续链路、帮助分层和专项最终审计。此处不是整体目标完成声明，未升版或打包。

## 第二轮：Analysis 发现与详情输出

- `list/search` 在空匹配时输出结构化 advice 与只读恢复命令；文本不再空白，JSON 保留现有 diagnostics 容器和空 entries，不自动放宽可信筛选。
- `describe` 错误项提供可执行概览/文档命令。正常文本补 grain、assurance、caveats 与 Control 输入；summary 只概览依赖数量，debug 展开引用，full 分节点展示定义/资产，显式 include-code 才展示真实换行代码。
- 同步内置 `catalog-discovery`、Analysis 文档和 Skill 决策边界。命令仍使用同一执行引擎、物理引用与 JSON 契约。
- 新回归禁止 Executor.run 并实际执行恢复命令，验证未知引用仍失败、空结果仍为空、summary/full 默认不输出代码、include-code 文本与 JSON 一致。
- 定向回归 112 passed（`/tmp/dataviz-analysis-discovery-final.log`）；相关 Ruff 与 diff 检查通过。未执行浏览器、未升版打包。
- 下一步仍需验证执行前参数/页面选择、Result 复用命令、帮助分层与整体专项审计；当前不标记整体完成。

## 第三轮：执行边界与可靠的后续命令

- `run --help` 分为常用选项、Multi-page and interaction、Advanced analysis；不新增必填参数，明确 dry-run 只检查 Overlay。
- 参数解析拒绝重复名称、空名称、名称首尾空白；字符串、JSON、空值和含等号值保持原语义。run 在 standalone 编译前处理这些语法错误。
- 发现当前 Typer 的上下文与外部 Click 不共享，原 handle_error 无法可靠识别 Analysis 命令；改为各 Analysis 入口显式选择失败契约，不依赖框架内部上下文。
- Result next_actions 改用 shell 引号而非 JSON 引号，避免含美元符号/反引号的真实目录被复制到 shell 后改变含义。
- 新测试实测含空格、单引号、美元符号和反引号路径的生成→运行→Result inspect/show，并禁止 Executor.run，证明后续读取不重查；验证重复参数在编译前失败。
- 既有无 Page/单 Page/双 Page 默认选择及指定 Page 导出回归通过；新增未知页、未知参数、非法类型、兄弟页参数四种失败前禁止执行检查，全部通过。
- 定向组合 148 passed、1 条依赖 warning（`/tmp/dataviz-cli-execution-final.log`）；追加四项测试 4 passed。Ruff 与 diff 检查通过。文档与 Skill 按需指导同步，未引入新 DSL。
- 下一步：整体非浏览器回归、文档/Skill 路由复核及按验收范围逐项完成审计；目前仍未升版打包。

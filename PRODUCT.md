# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Dataviz 的主要用户是 AI。AI 在本地 Workspace 中发现已有数据口径、开发和维护 Dashboard、执行分析，并将结果交给人类复核。

人类用户主要负责提出分析问题、确认数据口径和决策目标，在浏览器中调整参数与 Controls，阅读、比较和审查分析结果。

## Product Purpose

Dataviz 让 AI 快速搭建可靠的 Dashboard，并直接发现、执行和复用 Dashboard 背后的分析数据。成功不只是生成一个能看的页面，而是让同一份 Dashboard 同时成为：

- 人类可操作、可阅读的分析界面；
- AI 可发现、可执行、可复查的分析空间；
- 可以进入 Git、复制、审查和搬运的普通文件工程。

产品长期价值由两件事衡量：Dashboard 是否可靠、易懂且能减少人的困惑；AI 完成真实开发和分析任务所需的上下文、代码量与修正轮次是否持续下降。

## Positioning

Dataviz 的核心差异不是生成更多图表，而是让 Workspace 文件、CLI、Server、浏览器 Runtime、导出结果和 AI 分析共用一套数据依赖与执行语义。Dashboard 不再是分析数据被封存的展示终点，而是人类界面与 AI 分析能力的共同入口。

## Operating Context

Dashboard、Source、Transform、Presentation 和相关资产保存在本地 Workspace，以文件和 Git 作为协作、评审与版本管理边界。

典型工作流包括：

- AI 按任务读取最小文档和 Scaffold，编写文件，经过静态校验、真实执行与必要的浏览器检查完成 Dashboard；
- 人类通过本地 Server 查询数据、调整参数和 Controls、联动图表并阅读结论；
- AI 通过 Catalog 查找既有口径，执行 Source、Named Output 或 View，并在不可变 Result 上继续查看、导出和沉淀 Evidence；
- Dashboard 通过 Bundle 或 HTML 报告交付，同时保留可复查的数据与定义证据。

## Capabilities and Constraints

- Query Parameter 负责改变取数范围；Control 负责 Query 后的局部交互；两者具有不同生命周期，不合并为通用状态袋。
- SQL、Python 和 JavaScript 承担完整业务计算；DSL 只描述稳定的数据流、依赖、交互和展示边界。
- Plotly 是统一图表接口，TanStack Table 是默认表格内核；不建设第二套图表引擎。
- Compiler 与 Runtime 管理依赖图、状态事务、并发、缓存、Renderer 生命周期和跨运行时一致性，普通作者不应手工协调这些机制。
- Result 是可寻址、不可变的运行事实；查看和导出既有 Result 不应重新执行昂贵查询。
- Workspace Asset 可以共享稳定静态文件；业务 SQL、Source、Transform、View 和 Parameter Domain 保持 Dashboard-local，允许适度重复以换取明确所有权和安全搬运。
- Server 是本地优先的作者与分析界面，不是通用网页开发器，也不提供内建账号体系；远程访问依赖可信网络或外部访问控制。
- 当前处于 `0.x` 快速迭代阶段，可以进行明确的破坏式协议升级；不为未投入生产的旧设计维持 alias、自动迁移或双协议 Runtime。

## Brand Commitments

产品名称为 **Dataviz**。对外表达应专业、直接、克制，始终把“更专业地分析数据”和“更可靠地展示分析”放在工具炫技之前。界面与文档需要同时对人类和 AI 友好，但不能用模糊自动化隐藏数据口径、状态或执行事实。

## Evidence on Hand

- `README.md`：当前产品定位、安装与两条最短使用路径。
- `DESIGN.md`：已经实现的产品边界、执行不变量和演进约束。
- `dataviz-skill.md` 与 `src/dataviz/documentation.py`：AI 作者和分析工作流的渐进式指引。
- `examples/` 与内置 Gallery：真实 Dashboard、交互、地图、参数和组件能力示例。
- `tests/`：Python、Server、Runtime 与多浏览器行为证据。
- `CHANGELOG.md`：快速迭代阶段的版本演进记录。

项目目前没有正式 `LICENSE` 文件，也没有可公开宣称的客户案例、外部用户规模或生产 SLA；未来工作不得虚构这些证据。

## Product Principles

1. **分析问题先于图表。** 先明确决策、口径、比较基线与数据视角，再选择图表和交互。
2. **人和 AI 共用事实。** Server、CLI、导出和分析不能各自解释一套数据或状态语义。
3. **复杂度下沉，能力渐进披露。** 常见任务只有一条默认路径；高级能力按真实需要展开。
4. **保留必要领域区别。** 不为表面简单而合并 Query/Control、Run/Result 或数据计算/渲染等不同生命周期。
5. **错误尽早暴露，结果可以复查。** 校验、诊断和 Evidence 应帮助作者快速定位问题，不建立第二套事实来源。

## Open Decisions

- 正式开源或商业分发前，需要确定许可证与兼容性承诺。
- 当前主要用户仍是 AI 与单个人类使用者；多人真实使用后的工作流和治理需求尚未被验证。

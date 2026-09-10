# Dataviz 商业方向参考

更新时间：2026-09-04

> 本文记录 Dataviz Local 与未来商业版 Enterprise Server 的产品边界、商业假设和协议对齐方向。它不是当前 CLI 的实现计划，不构成版本承诺，也不要求 `plan.md` 按本文开发 Enterprise 功能。商业版 Server 大概率属于另一个 Git 仓库；当前仓库只需保持核心协议可被未来 Server 安全复用。

## 1. 核心判断

Dataviz 不应通过削弱本地版本来制造收费点。

本地版本应继续提供完整的个人分析闭环：

```text
Workspace → Catalog → Target → Run → Result → Evidence → Promote
```

未来商业版解决的不是“本地版缺少几个高级命令”，而是个人文件系统无法自然解决的组织问题：

```text
Identity → Organization → Authorization → Coordination
         → Shared Catalog → Controlled Execution
         → Team Result/Evidence → Governance
```

因此产品边界是：

> Local 让一个人完整拥有、执行和分享分析资产；Enterprise 让一个组织安全地连接、治理和复用这些资产。

商业价值来自多人协作形成的网络效应、组织治理和持续服务，而不是隐藏 Python 实现。

## 2. 两个产品层次

### 2.1 Dataviz Local

Local 面向个人、单机和文件夹级分享，保持 local-first、workspace-first：

- `pip install` 后即可使用，不要求账号或联网；
- Workspace 是普通文件夹，可复制、压缩、进入 Git 和代码审查；
- Local Server 面向人提供 Dashboard；
- CLI 面向人、AI 和自动化提供 validate、Catalog、Run、Result、Evidence；
- 本地文件是正式分析定义的唯一事实来源；
- `.dataviz/` 中的 Catalog、usage、Run 和 Result 是可重建或可清理的运行状态；
- 单个 Workspace 内可以做确定性折叠、局部使用统计和检索，但不假装拥有组织全局知识；
- Local 不因为 Enterprise 的存在而变成受限试用版。

Local 的目标是“本地全部完备”，不是“免费但残缺”。

### 2.2 Dataviz Enterprise

Enterprise 面向多用户、多团队、多 Workspace 和长期组织治理，可能包括：

- 登录、SSO、Service Account 和组织成员管理；
- Team、Role、Policy 与细粒度 RBAC；
- Workspace 注册、版本识别和状态同步；
- Dashboard、Named Output、Result 和 Evidence 的可见性权限；
- 跨 Workspace 的统一 Catalog 与知识库；
- 组织级搜索、使用统计、排序、精确去重和相似口径诊断；
- Server Query、受控远程执行、取消、配额与完整审计；
- Team Sharing、订阅、Review、Certification 和 Deprecation 工作流；
- 团队 Result/Evidence 的共享、保留和治理；
- AI 辅助的语义补全、聚类、重复候选、冲突诊断和知识维护；
- 企业管理页面、安全策略、运维能力和支持服务。

Enterprise 的核心不是“云端 Dashboard”，而是：

> 将散落在个人文件夹和 Git 仓库里的可执行分析资产，升级为可搜索、可授权、可审阅的组织知识网络。

## 3. 必须保持的产品原则

### 3.1 Workspace 仍是分析定义的事实来源

即使存在 Enterprise Server，正式 SQL、Transform、Output Contract、Dashboard 和语义定义仍应以普通 Workspace 文件和 Git 变更为准。

```text
Workspace / Git       正式分析定义
Enterprise Catalog    可重建的组织索引
Result Store          已发生的执行事实
Evidence Store        被审阅的结论与来源链路
```

Enterprise 管理页面可以发起修改建议、审批和 Promote，但最终应生成可 validate、可 Git diff、可普通工具审查的 Workspace 变更。不要让 Server 数据库悄然成为第二份不可导出的分析定义。

### 3.2 协作信息可以属于 Server

以下信息天然属于组织协调面，不必强行写回每个 Workspace：

- 用户、团队、角色和授权策略；
- Workspace 注册关系和组织归属；
- 跨 Workspace 使用统计；
- 组织级推荐、收藏、订阅和访问记录；
- Review 队列、审批过程和审计日志；
- Server 执行调度、配额、保留策略和运行状态；
- AI 生成但尚未被人确认的重复、相似和冲突候选。

当某项信息会改变正式分析含义时，应通过 Promote 回到 Workspace；当它只表达组织协作状态时，可以只存在于 Server。

### 3.3 Local 与 Enterprise 共用协议，不共用全部实现

未来商业版不应复制一套 Target、Result 或 Evidence 语义。两端应尽量共用版本化契约，但可以采用不同实现和存储：

- Workspace Schema；
- Target Reference；
- Catalog Entry 与 Describe Contract；
- Result Manifest、Artifact receipt 与 provenance；
- Evidence 与 Workspace Change；
- 稳定错误 envelope；
- capability/version negotiation。

Local 的 SQLite、文件锁、缓存目录和 Server 内部类不属于跨产品公共协议。

## 4. Enterprise 的建议架构

```text
                         ┌─────────────────────────────┐
CLI / Browser / AI ─────>│ Enterprise Control Plane    │
                         │ Auth / RBAC / Catalog        │
                         │ Policy / Audit / Knowledge   │
                         └──────────────┬──────────────┘
                                        │ authorized job
                         ┌──────────────▼──────────────┐
                         │ Customer-managed Executor    │
                         │ Workspace / Runtime / Secrets│
                         └──────────────┬──────────────┘
                                        │
                              Database / Warehouse
```

### 4.1 Control Plane

Control Plane 负责身份、权限、索引、审批、审计和任务协调。它可以由商业方托管，也可以提供企业私有部署版本。

### 4.2 Executor

远程执行不应默认让中心 Server 任意持有客户数据库凭证。更稳妥的方向是让 Executor 部署在客户网络内：

- 从 Control Plane 拉取或接收经过授权的执行任务；
- 在客户环境解析 Workspace 并调用同一 Runtime；
- 从本地 Secret Provider 获取数据库凭证；
- 上传最小必要的状态、provenance 和允许共享的 Result；
- 支持取消、超时、资源限制、网络策略和审计；
- 不允许一个租户读取另一个租户的 Workspace、Artifact 或 Secret。

是否允许 Result 数据离开客户网络应由组织策略决定。Metadata-only、summary-only、full-result 应是明确策略，而不是隐含行为。

### 4.3 Git 与版本控制

Enterprise 不必重新实现 Git。它应该记录：

- Workspace 的稳定 Server ID；
- Repository/branch/commit 或发布版本；
- 当前同步 generation 和内容 hash；
- Catalog Entry 对应的定义版本；
- Result 执行时所使用的不可变定义证据。

Server 负责连接版本与运行事实，而不是发明另一套源码版本历史。

## 5. CLI 与 Enterprise 的对齐方式

当前 CLI 不需要实现商业 Server，但协议设计应避免封死以下路径。

### 5.1 Local 默认行为不变

普通命令继续直接操作本地路径：

```bash
dataviz catalog search ./workspace revenue
dataviz run ./workspace 'sales::source:orders/main'
```

安装本地版本不应要求 `login`，也不应因为未连接 Enterprise 而降低能力。

### 5.2 未来通过 Context 或显式 Locator 连接 Server

可能的使用形式仅作为方向参考，暂不固定为当前 CLI 契约：

```bash
dataviz login https://analytics.example.com
dataviz context use company
dataviz catalog search team://finance revenue
dataviz run team://finance 'sales::source:orders/main'
```

不建议为 Enterprise 再创造 `cloud-catalog`、`server-run`、`team-result` 等平行命令树。同一领域对象应保持相同动词，Local path 与 Enterprise locator 决定请求落点。

### 5.3 Target 与 Workspace 身份分离

当前物理 Target Reference 描述 Workspace 内部对象：

```text
dashboard::source|dataset|interactive|view:...
```

Enterprise 可以为已注册 Workspace 分配组织级不可变 ID，并在 Target 外层增加 Workspace locator。不要为了远程寻址过早修改 Workspace 内部 Target grammar，也不要把组织、团队或域名硬编码进可复制的 Dashboard 文件。

### 5.4 Auth 与 Secret 不进入 Workspace

登录 Token、组织成员关系、Server URL、RBAC 和远程 Secret 引用属于用户配置或 Enterprise Context，不进入可分享 Workspace。Workspace 可以声明逻辑 Adapter 名称，但不携带真实凭证。

### 5.5 同步应可增量、可验证、可回退

未来注册或同步至少需要：

- protocol/schema version；
- Workspace identity 与 generation；
- definition/content hash；
- Catalog metadata；
- capability declaration；
- 明确的删除、重命名和 tombstone 语义；
- 幂等提交与失败回退；
- Server 与 CLI 版本不兼容时的可操作诊断。

## 6. 组织级知识、去重与排序

Local 的知识范围是单个文件夹。它适合便携分享和确定性执行，但无法自然回答“公司里是否还有相同口径”。Enterprise 可以在多个 Workspace 上建立组织级视图。

### 6.1 三层去重模型

#### 确定性折叠

实现资产、Runtime、Adapter 引用、bindings、依赖闭包和 Output Contract 完全一致时，可以自动折叠 occurrence。该层不得依赖 AI 猜测。

#### 相似候选

Server 可以结合 purpose、grain、Schema、lineage、SQL 结构、消费关系和 embedding，生成：

- `possible_duplicate`；
- `possible_variant`；
- `possible_conflict`。

这些只是候选关系，不能自动改变正式口径。

#### 人工治理

有权限的 owner/reviewer 决定：

- 指定 canonical Output；
- 确认合法变种；
- 增加 caveat；
- deprecated 旧口径；
- 保持独立；
- Promote 为新的正式 Output、测试或语义变更。

AI 可以整理证据、解释差异和生成建议，但不能单方面宣布业务等价。

### 6.2 排序原则

组织搜索不应简单按点击次数排序。建议顺序为：

```text
权限过滤
→ 生命周期与可信度策略
→ 查询相关性
→ 精确重复折叠
→ 组织推荐、使用次数、最近使用和新鲜度
→ Top N
```

使用频率表示“常用”，不表示“正确”。`certified`、review 状态、owner、验证时间和 caveat 必须与 popularity 分开表达。

### 6.3 使用事件

Local 可以继续保留简单、best-effort 的本地统计。Enterprise 可定义可扩展的组织事件模型，例如：

- subject kind/reference；
- action kind；
- actor kind/user/service account；
- organization/team/workspace；
- timestamp、success/status；
- result/reference/version；
- privacy classification。

是否上传本地历史、上传到什么粒度、是否保留用户身份，都必须是显式组织策略。

## 7. AI 加工边界

Enterprise 的 AI 能力应优先加工 metadata、Contract 和证据，而不是默认读取所有业务数据。

适合的能力包括：

- 补全缺失的 title、purpose、grain 和 caveat 草案；
- 比较相似 Output 的字段、过滤、时间口径和依赖差异；
- 发现重复、变种与潜在冲突；
- 汇总 Result/Evidence，生成待审阅的知识条目；
- 在定义变更后识别可能失效的 Evidence；
- 为 reviewer 生成差异说明和 Promote 建议。

必须坚持：

- AI 产物默认是 draft；
- AI 不自动 certified；
- AI 不自动合并或删除正式 Output；
- 数据内容是否可发送给模型由组织策略决定；
- 模型、输入范围、输出和人工决策进入审计记录。

## 8. 开源与商业仓库边界

一个可能的代码组织方式：

```text
dataviz-local / dataviz-core     开源仓库
  Workspace、Compiler、Runtime、Local Server、CLI、公共协议

dataviz-enterprise               商业仓库
  Control Plane、Auth/RBAC、管理页面、组织 Catalog、审计、调度

dataviz-executor                 独立包或商业仓库子项目
  客户网络内的受控执行 Agent
```

具体仓库名称和许可证以后决定。无论如何，商业仓库不应迫使 Core 引入账号系统、远程依赖或商业授权检查。

公共协议可以开放，商业 Server 的实现、管理体验、托管服务和企业支持仍可收费。Enterprise 的长期价值来自持续运行、组织数据和服务责任，不依赖让协议保持秘密。

## 9. 建议的商业验证顺序

以下只属于未来 Enterprise 项目的验证顺序，不进入当前 CLI `plan.md`：

1. **只读多 Workspace Registry/Catalog**：注册多个 Workspace，统一搜索和查看 owner/assurance/lineage。
2. **Identity 与 Visibility**：用户、团队、Service Account 和 Catalog 可见性。
3. **组织级 Usage 与精确折叠**：跨 Workspace occurrence、可信排序和重复概览。
4. **Review/Evidence 工作流**：组织认证、过期复核、Evidence 分享和审计。
5. **受控远程执行**：Executor、Secret、Policy、Result 保留、取消和资源隔离。
6. **AI Knowledge Curation**：相似候选、冲突解释、失效检测和 Promote 建议。

第一版商业 MVP 不一定需要远程执行。若企业愿意为“统一发现和治理分析口径”付费，再投入安全执行体系，可以显著降低早期工程风险。

## 10. 非目标

当前不因为商业方向而在 Local 中实现：

- 账号、SSO 或 RBAC；
- 中心化 Workspace 数据库；
- 企业管理页面；
- 跨组织远程执行；
- 商业 License Server；
- Git 的替代品；
- 自动语义合并；
- 必须联网才能工作的核心功能。

当前也不承诺 Enterprise 一定采用 SaaS、私有部署或某种具体计费方式。这些决定应由真实客户、安全要求和商业验证驱动。

## 11. 当前 CLI 需要保留的未来兼容性

在不开发 Enterprise 的前提下，Local 后续设计只需持续满足：

- 核心 Schema 独立版本化；
- Target 在 Workspace 内可稳定寻址；
- Catalog 可重建并提供确定性 generation/hash；
- Result/Evidence 不依赖当前进程即可读取和验证；
- provenance 足以关联定义版本、参数、依赖和 Artifact；
- JSON Schema 与错误码机器可读；
- Workspace 不包含账号 Token 和真实 Secret；
- Local 文件资产可以完整导出、复制和离线使用；
- 新的远程 Context 将来可以作为外层适配，而不改写 Local Runtime。

只要这些边界成立，当前 CLI 就已经为未来商业版留下了干净接口，无需提前承担企业系统的复杂度。

## 12. 尚未决定的问题

- 最终品牌名、开源许可证和商业产品名；
- Enterprise 是托管 SaaS、私有部署，还是两者同时提供；
- Control Plane、Executor 与 Core 的具体仓库和发布关系；
- Workspace 注册身份、重命名和跨组织迁移协议；
- Result 默认保留位置与数据出域策略；
- 企业级计费单位：组织、活跃用户、Executor、存储或执行量；
- AI Provider、BYOK、模型输入范围和隐私策略；
- 哪些组织协作状态应 Promote 回 Workspace，哪些只保留在 Server。

这些问题暂时保持开放。本文首先固定产品边界：Local 完整，Enterprise 协作；Workspace 保存正式分析资产，Server 提供组织治理与网络效应。

## 13. 战略探索：从 Dashboard-first 到 Capability-first

ChatBI 不应被理解为“给 Dashboard 加一个聊天框”。它真正可能改变的是 Dataviz 的核心组织单位：系统不再首先要求作者制作一份完整 Dashboard，而是先沉淀可发现、可执行、可验证的分析能力，再由 AI 或人将这些能力编排成临时报告或稳定 Dashboard。

这不是一个容易追加的小功能。当前 Dataviz 的许多边界都以 Dashboard 为中心：

- Dashboard 是文件所有权和路径边界；
- Dashboard 是参数、Control 和依赖图的作用域；
- Dashboard 是 Compiler、Runtime 和 Server 的主要装载单位；
- Dashboard 是 Catalog 的主要发现入口；
- Dashboard 是 Bundle、portable HTML 和发布的主要单位；
- Section 与 View 共同组成一条预先固化的分析 Story。

如果探索式分析的核心单位变成独立能力，上述假设可能需要拆开。Dataviz 甚至可能从“可靠 Dashboard Runtime”重构为“可靠分析能力 Runtime”，而 Dashboard 只是其中一种发布组合。这一方向可能构成架构分叉乃至未来大版本重置，不能按普通增量需求估算。

### 13.1 为什么值得探索

Dashboard 适合反复使用、口径稳定、布局固定且需要审阅的分析故事；ChatBI 更适合问题尚未收敛、需要快速发现和组合已有口径的探索过程。两者不应互相替代：

```text
探索：搜索能力 → 组合 → 执行 → 解释 → 继续追问
发布：确认口径 → 固定参数与布局 → 校验 → 审阅 → 分享
晋升：探索报告 → 补齐契约和证据 → 稳定 Dashboard
```

对探索而言，最重要的并不是更多 DSL，而是：

1. 快速发现 Workspace 中已有的取数口径、可信 Output、View 和业务知识；
2. 用很少的上下文和 Token 判断哪些能力可以组合；
3. 复用经过验证的执行与可视化颗粒，而不是每次重新生成 SQL 和图表；
4. 保留参数、Result、来源和限制，使 AI 的解释可以被复查；
5. 将真正有长期价值的探索结果晋升为可靠 Dashboard。

### 13.2 待验证的最小分析颗粒

`Source → View` 是一个有价值的直觉，但 Source 或 View 单独都不足以成为可靠复用单位：Source 缺少完整业务语义，View 又可能依赖参数、Transform、Named Output、Asset 和交互状态。

更合适的候选概念是 **Analysis Capability**：

```text
Verified Named Output / Target
+ 参数与语义契约
+ 可选的 View Recipe
+ 可计算的依赖闭包
+ 可靠性、成本和 Evidence
```

一个紧凑的 Capability Card 至少应回答：

- `ref`、title、purpose 和它能回答的问题；
- grain、measures、dimensions 和时间语义；
- 参数契约、默认行为与适用约束；
- 输出 Schema 与建议的可视化意图；
- owner、可靠性级别、最近验证时间、新鲜度和预估成本；
- 完整定义、依赖与 Evidence 的按需展开入口。

Capability Card 应由 Workspace 中的正式定义确定性生成，是可重建索引，不成为第二份事实来源。第一阶段也不必把文件物理拆散：现有 Dashboard 可以继续拥有实现，Catalog 先在逻辑上投影出 Dashboard、Named Output、View 和 Knowledge 等细颗粒入口。

### 13.3 发现、编排与解释

ChatBI 的核心产品价值应集中在三个动作，而不是自由生成一切：

#### 发现

搜索同时覆盖四类对象：

- Dashboard：完整且稳定的已有 Story；
- Named Output / Target：经过验证的数据颗粒；
- View / Recipe：经过验证的呈现方法；
- Knowledge：指标定义、时间语义、排除规则和业务术语。

检索不能只依赖向量相似度。候选排序还应考虑精确术语、grain 兼容性、参数可满足性、可靠性、新鲜度、执行成本和历史复用证据。

为了减少 AI 上下文，信息应渐进暴露：

```text
search    → 返回极短候选卡片
describe  → 返回所选能力的组合契约
evidence  → 仅在需要时展开 SQL、Transform、依赖和 Result
```

#### 编排

AI 优先组合已有 Capability，而不是直接生成未验证代码。临时报告可以排列、替换和追问多个分析块；每个块保留自己的 Target、参数、Output Schema、Result ID 和 provenance。

可视化应优先使用少量按分析意图组织的模板，例如 metric、metric-secondary、trend、ranking、composition、distribution、relationship、map 和 detail-table。AI 描述字段角色和表达意图，模板负责默认样式、字段校验、空态和交互约束。不要让 AI 每次生成任意 Plotly JSON，也不要因此扩张 Dashboard DSL。

#### 解释

解释必须绑定实际 Result 和 Evidence，明确区分：

- 复述已执行结果；
- 基于数据做出的推断；
- 尚未执行的建议；
- AI 临时生成且未认证的口径。

Chat transcript 不能成为分析事实来源；可复查的 Result、参数、定义版本和 provenance 才是。

### 13.4 两条可能的架构路径

目前不预先决定最终采用哪条路径。

#### 路径 A：渐进投影

```text
Dashboard 继续拥有文件与执行定义
→ Catalog 提取细颗粒 Capability
→ ChatBI 搜索并复用这些逻辑颗粒
→ 成熟结果仍发布为 Dashboard
```

优点是能复用当前 Compiler、Runtime、Result 和 Bundle，迁移风险较低。缺点是颗粒仍受 Dashboard 参数作用域和物理所有权约束，跨 Dashboard 组合可能笨重。

#### 路径 B：Capability-first 重构

```text
Workspace 独立拥有 Capability
→ Runtime 执行和组合 Capability
→ Report 是临时组合
→ Dashboard 是稳定发布组合
```

这一路径会把能力所有权、执行单位、报告组合和发布单位彻底分离。它可能要求重做 Loader、Compiler、Catalog、参数作用域、依赖图、Result identity、Bundle 和文档模型，但更符合 ChatBI 的长期形态。

路径 B 不能仅凭概念先进而启动。只有当真实原型证明 Dashboard 所有权持续阻碍能力发现、组合和复用时，才值得承担整体重构成本。

### 13.5 原型与决策门槛

在决定是否拆掉现有架构前，应先做少量纵向原型，而不是建立完整 Chat 产品：

1. 从现有 Workspace 确定性提取 Capability Card；
2. 用短查询检索到正确的口径、Output 和 View；
3. 不读取整份 Dashboard 上下文即可执行一个能力；
4. 将两个兼容能力组合成带证据的临时报告；
5. 将报告中的有效分析块晋升为稳定 Dashboard；
6. 测量检索准确率、上下文 Token、组合失败类型和人工修正成本。

若出现以下任一情况，应把它视为核心架构信号，而不是继续堆兼容层：

- 一个 Capability 必须读取大部分 Dashboard 才能理解或执行；
- 参数、grain 或 Schema 兼容性无法在执行前判断；
- 跨能力组合频繁依赖隐式状态或共享可变对象；
- Result 和 Evidence 无法稳定追溯到单个能力及其版本；
- 为维持 Dashboard 所有权而产生大量复制、适配和特殊规则。

反过来，如果逻辑投影已经能满足发现、编排和可靠执行，就没有必要为了架构纯度物理拆分所有文件。

### 13.6 可靠性分级与边界

探索结果必须显式区分可靠性：

1. **Verified**：直接复用已有可信 Target / View；
2. **Derived**：基于可信 Output 做新的受约束变换或可视化；
3. **Exploratory**：AI 新生成 SQL、Python 或 JavaScript，尚未审阅。

当前不应急于开发：

- 庞大的聊天界面；
- 自动生成任意 SQL 和图表后假装可信；
- 新的共享 SQL 层或隐式跨 Dashboard Source 依赖；
- 为 ChatBI 预先增加大量公共 DSL 和协议；
- 以聊天记录替代 Workspace、Result 或 Evidence；
- 在 Capability 原子和检索效果尚未验证前一次性重写 Runtime。

这一战略探索的 North Star 是：

> 用户用几句话发现并组合已有分析能力，快速得到带来源、可复查的报告；当答案值得长期复用时，可以无损晋升为可靠 Dashboard。

因此，Dataviz 的潜在长期定位不是“更会聊天的 Dashboard 工具”，而是 **Verified Analytical Capability Runtime**：既支持低背景、低 Token 的快速探索，也保留稳定 Dashboard 所需要的确定性、审计和发布能力。

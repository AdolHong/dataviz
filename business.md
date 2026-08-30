# Dataviz 商业方向参考

更新时间：2026-08-29

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

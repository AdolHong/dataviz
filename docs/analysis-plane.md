# AI Analysis Plane

Analysis Plane 让 AI 搜索、理解并执行 Dashboard 已有的数据契约。它不引入第二套查询引擎：Base Output 仍走 Query Executor，server-python 仍走 Interaction Executor，browser-js 仍走同一 Browser Runtime。

## 最短工作流

```bash
dataviz catalog list WORKSPACE
dataviz catalog search WORKSPACE '收入|工资|年入|月入'
dataviz catalog describe WORKSPACE 'sales::source:orders/main'
dataviz run WORKSPACE 'sales::source:orders/main'
```

`list` 默认只列 Base Named Output 的业务概览。`search` 默认使用不区分大小写的 grep-like 正则；希望按普通文本搜索时使用 `--literal`。默认文本把 title、purpose、grain、assurance 和参数契约放在引用前面。Catalog 不生成短别名，所有命令复用同一条规范物理引用。

可复用 Output 应直接声明业务语义；技术 `description` 不再承担口径契约：

```yaml
outputs:
  main:
    kind: table
    semantics:
      visibility: public
      title: 城市季度经营指标
      purpose: 比较城市季度收入、订单和客户表现。
      grain: 每行代表一个城市的一个季度。
      caveats: [退款在次日批处理后回写。]
      assurance:
        status: reviewed
        owner: finance-analytics
        reviewed_at: 2026-08-28
        evidence: [evidence/revenue-contract.md]
      time: {field: quarter, timezone: Asia/Shanghai, meaning: 自然季度}
      measures:
        revenue: {unit: CNY, aggregation: sum}
      relationships:
        - {fields: [city_id], cardinality: many-to-one, target: dim_city}
```

`public` 语义必须具有非空 title、purpose 和 grain。`visibility` 只控制可发现性，`assurance.status: draft|reviewed|certified|deprecated` 单独表达可信度；reviewed/certified 必须给出 owner、日期和 Dashboard 内可定位的 evidence，deprecated 必须给出原因或替代 Output。时间、指标和关系只在适用时声明。`internal` 与未迁移 Output 保留在 lineage 中，也可按精确物理引用执行，但默认不进入 `list/search`；draft/deprecated 同样不进入默认可信搜索。维护者可用 `--include-internal --include-untrusted` 审计完整集合。

public 或 reviewed/certified SQL Output 必须显式投影字段。`SELECT *` 与 `table.*` 会产生稳定 validation warning，`count(*)` 不会；这样上游新增列不会悄悄改变 Output Schema、脱敏边界或精确折叠 identity。

常用过滤：

```bash
dataviz catalog list WORKSPACE --kind all --dashboard sales
dataviz catalog search WORKSPACE '收入|利润' --kind base --source-type sql
dataviz catalog search WORKSPACE region --parameter region
dataviz catalog list WORKSPACE --include-internal --include-untrusted
dataviz catalog list WORKSPACE --top 20
dataviz catalog search WORKSPACE '收入|利润' --expand-occurrences
```

`all/search` 默认在所有实现资产 hash、Source/Runtime、Adapter 逻辑引用、Query bindings 和 Output Contract 都完全相同时折叠重复口径；这只是精确概览压缩，不推断两段不同 SQL 是否语义等价。每组返回稳定 representative 和 `occurrence_count`，`--expand-occurrences` 才展开 canonical references，`--no-fold` 可查看每个 occurrence，`--top N` 在折叠后截取。

Workspace 的 `.dataviz/usage.sqlite` 只记录成功行为的累计次数与最近时间：Server Query 记为 human，CLI `run` 的 Base/Derived Output 记为 AI。搜索、查看、失败和取消都不计数。统计使用 WAL 和原子 UPSERT，但始终是 best-effort；锁竞争或文件故障只写 warning，不会把已成功的执行改成失败。

## 探索执行契约

```bash
dataviz catalog describe WORKSPACE \
  'sales::source:orders/main' 'sales::interactive:forecast/main'
dataviz catalog describe WORKSPACE \
  'sales::interactive:forecast/main' --detail full --include-code
```

`describe` 是 Run 前的只读 Invocation Contract，一次可以解析多个引用并保持输入顺序；它返回参数类型、required/default、候选摘要、Control/Output 摘要、lineage 和可复制 Run 命令，但不执行 Source、候选查询或 Transform。完整模式列出目标所需 Source、Dataset Transform 与 Interactive Transform，包括定义、Workspace 相对路径、content hash、Runtime 和 Output Contract。`--include-code` 才内联已脱敏且不超过 256 KiB 的 SQL/JS/Python；File Source 数据不会内联，Adapter 凭据也不会返回。

## 执行口径

```bash
dataviz run WORKSPACE 'sales::source:orders'
dataviz run WORKSPACE 'sales::source:orders/main' --query-param region=华东
dataviz run WORKSPACE 'sales::interactive:forecast/main' \
  --query-param region=华东 \
  --control dashboard:sales/factor=1.2 \
  --detail debug
dataviz run WORKSPACE 'sales::interactive:forecast/main' \
  --also 'sales::interactive:baseline/main' --detail debug
```

Source/Base 只执行目标的最小 Query DAG。Derived Output 根据声明自动选择 server-python 或无头浏览器；浏览器默认阻止额外 HTTP(S) 请求，确实依赖 CDN 时显式使用 `--allow-network`。Playwright 未安装时按 CLI 给出的命令安装 `ai-dataviz[visual-check]` 和 Chromium。

`run` 始终完整执行并封存不可变 Result，默认 stdout 只显示 Result ID/路径、紧凑 DAG、每个表格 Output 的前 10 行和下一步命令；`--preview-rows` 只改变终端预览，不裁剪实际结果。显式 `--format json` 使用 `dataviz/analysis-result/v3`，包含最终 Query Parameter、有效 Controls、每个 consumer 的 effective/applied revision、对应 `applied_control_state` 与实际 View writer 的 `applied_writer_provenance`，以及输入 Artifact/hash、Schema、行数、Output hash、分段耗时、lineage 和 Result 句柄。机器契约可直接导出 JSON Schema：

```bash
dataviz schemas analysis-entry --format json --full
dataviz schemas analysis-catalog --format json --full
dataviz schemas analysis-describe --format json --full
dataviz schemas analysis-result --format json --full
dataviz schemas analysis-evidence --format json --full
dataviz schemas analysis-promotion --format json --full
dataviz schemas analysis-promote-proposal --format json --full
```

后续命令都只读已封存结果：

```bash
dataviz result show WORKSPACE result_... --offset 0 --limit 100
dataviz result show WORKSPACE result_... 'sales::source:orders/main'
dataviz result inspect WORKSPACE result_... --detail full --format json
dataviz result export WORKSPACE result_... \
  'sales::source:orders/main' --to result.parquet
```

`result show` 分页读取且绝不重跑；`inspect` 渐进披露 Schema、DAG、lineage、hash、时序和 provenance；`export` 只复制明确选择的一个原生 Artifact，不转换格式，也不修改 Result manifest。平台生成的数据存入 `.dataviz/results/<result-id>/outputs/`；直接 File Source 只保留已读 path/hash 收据。Result 只由显式 `dataviz prune` 按策略清理，外部 export 副本不受影响。

## Evidence 与 Promote

一次 Result 可以沉淀为紧凑 Evidence；大型数据不默认复制，只记录 Result hash、Output hash、lineage、consumer revision 与 applied writer provenance 审计、结论/断言和可选的最多 100 行 snapshot：

```bash
dataviz run WORKSPACE 'sales::source:orders/main'
dataviz evidence create WORKSPACE result_... \
  --question '收入口径是否可复用？' \
  --conclusion '退款回写后与财务日报一致。' \
  --status reviewed --reviewer alice
dataviz evidence promote WORKSPACE evidence_... proposal.yaml --dry-run
```

Promotion proposal 支持 `kind: semantics | assertion | new_output`。命令只生成统一 diff 并在临时 Workspace 中执行完整 validate；P1 不提供隐式 apply，因此不会修改正式 Dashboard。新 Output 必须从 draft 开始，reviewed/certified 语义只能引用 reviewed Evidence，且仍需显式 owner、reviewed_at 和可定位 evidence。人审阅 patch 后按普通 Git/文件工作流落地，Catalog 仍由正式 Workspace 重建。

## 一次性 Analysis Overlay

Overlay 用于临时替换某个节点的实现或数据，同时保持 ID、DAG、Adapter/Auth、Runtime、bindings 和 Named Output Contract 不变：

```yaml
schema: dataviz/analysis-overlay/v1
replacements:
  source:orders:
    code: ./experiments/orders.sql
  source:exchange-rates:
    path: ./fixtures/new-rates.csv
  dataset:customer-score:
    code: ./experiments/customer_score.py
    code_dependencies: [./experiments/features.py]
  interactive:scenario:
    code: ./experiments/scenario.js
```

```bash
dataviz run WORKSPACE 'sales::interactive:forecast/main' --overlay overlay.yaml --dry-run
dataviz run WORKSPACE 'sales::interactive:forecast/main' --overlay overlay.yaml
cat overlay.yaml | dataviz run WORKSPACE 'sales::interactive:forecast/main' --overlay -
```

相对资产路径以 Overlay 文件所在目录为基准；stdin 以当前目录为基准。`--dry-run` 会检查节点、字段、文件和目标可达性，并列出受影响闭包。实际执行构造不可变的 in-memory Analysis Variant，使用带 Overlay hash 的独立缓存键，并把最终 Output 与 Overlay provenance 一起封存在普通 Analysis Result 中。它不会修改 Dashboard 或 Catalog，也不会把替代数据复制进 Workspace。

Overlay 运行本地可信 SQL/Python/JavaScript，并非安全沙箱。分享链接不接受 Overlay；远程分析要等独立的鉴权、能力范围、资源限制和审计设计完成。

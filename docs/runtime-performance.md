# Runtime 性能基线

本页记录可复现证据，不承诺脱离硬件、浏览器和 Dashboard 形态的统一行数上限。

## 固定链路

基准 Workspace 位于 `benchmarks/scale-workspace`，固定执行：

```text
DuckDB Query(row_count)
  → Arrow IPC（3 个 int64 字段）
  → browser-js Worker groupBy（128 组）
  → Metric + Plotly line + basic Table
  → dispose → about:blank → GC
```

运行方式：

```bash
uv sync --python 3.12 --extra dev
uv run --no-editable python scripts/run_runtime_scale_benchmarks.py \
  --browser chromium --repeat 3 \
  --output benchmarks/results/runtime-scale-chromium-2026-08-24.json
```

也可测任意 Dashboard：

```bash
dataviz benchmark WORKSPACE DASHBOARD --browser-runtime \
  --browser chromium --repeat 3 --query-param row_count=1000000 --format json
```

输出契约为 `dataviz/browser-runtime-benchmark/v3`。Query 记录 CLI 进程峰值 RSS；Browser 记录页面就绪时间、Playwright driver 与所有后代浏览器进程的 RSS、重复释放后的回落，以及浏览器允许时的主 renderer JS heap。进程树 RSS 包含 Worker、native Arrow、GPU helper 和浏览器固定开销；`performance.memory` 不包含这些内容，不能单独作为总内存结论。

## 2026-08-24 结果

环境：Dataviz 0.3.2 开发树、Python 3.12.8、macOS arm64、10 logical CPUs、Playwright Chromium；每档运行一次 Query，并重复装载/释放同一 HTML 三次。

| 行数 | Query | HTML 构建 | HTML 大小 | 页面就绪中位数 | Browser RSS 峰值增量 | 第三轮释放后增量 | Arrow bytes |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10K | 617 ms | 23 ms | 5.18 MB | 474 ms | 205 MB | 1.7 MB | 0.24 MB |
| 100K | 580 ms | 66 ms | 5.38 MB | 504 ms | 215 MB | 6.8 MB | 2.40 MB |
| 1M | 692 ms | 444 ms | 7.40 MB | 804 ms | 395 MB | 4.0 MB | 24.00 MB |

三档均为 3 个 View `ready`、1 个 browser-js Transform `completed`、0 Renderer failure、0 console error。原始机器可读结果保存在 `benchmarks/results/runtime-scale-chromium-2026-08-24.json`。

## 证据触发的优化

首轮实现把 Arrow 列式输入转换成 1M 个行对象，并为每个 group 保留完整行数组。相同环境的改前结果如下：

| 行数 | 页面就绪中位数（改前 → 改后） | Browser RSS 峰值增量（改前 → 改后） |
| ---: | ---: | ---: |
| 10K | 462 → 474 ms | 199 → 205 MB |
| 100K | 512 → 504 ms | 234 → 215 MB |
| 1M | 1043 → 804 ms | 496 → 395 MB |

因此 `DatavizFrame.groupBy().aggregate()` 改为单遍流式状态：每组只保存 key 以及 count/sum/min/max，不再保存源行。1M 页面就绪中位数降低约 23%，浏览器进程树峰值增量降低约 20%；小数据差异属于运行噪声，不以此声称普遍加速。

## 当前决策

- 不新增通用 Server pagination、Record Batch DSL 或 Scaffold 字段。该聚合链路在 1M 行可完成，尚无证据证明普通 Dashboard 都需要这些复杂度。
- 不把本结果外推为“1M 原始明细安全”。Basic Table、Perspective、全量 Selection、字符串宽表、高基数组合和移动设备需要独立基准。
- 继续默认使用 Arrow + Worker + 先聚合后渲染；AI 面对大数据应优先让 View 消费小型 Named Output，而不是把 1M 原始行直接交给图表。
- Firefox/WebKit 不暴露 `performance.memory` 时返回 `null`，不估算 JS heap；功能边界由三浏览器 E2E 矩阵保证。

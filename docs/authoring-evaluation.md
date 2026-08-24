# AI Authoring 成对评测协议

Dataviz 的长期目标之一，是让 AI 用更少的上下文、输出代码和修正轮次完成可靠看板。但这目前仍是需要实测的产品假设，不预设固定 Token 上限或节省比例。

## 1. 固定任务

安装包内置五类任务：默认声明式看板、三级 Selection、多输入/多输出 Dataset Transform、三 Runtime Interactive Transform、自定义 Renderer。

```bash
dataviz authoring tasks --format json
dataviz authoring tasks three-level-selection --format json
dataviz authoring protocol --format json
```

任务的 `acceptance` 是带稳定 ID 的质量门禁。没有通过同一组验收条件的短代码，不算效率提升。

为两种方案分别生成中性输入包；同一个 `trial-id` 的两个目录会得到内容哈希完全一致的数据：

```bash
dataviz authoring prepare default-dashboard /tmp/trial-001-dataviz \
  --approach dataviz --trial-id trial-001
dataviz authoring prepare default-dashboard /tmp/trial-001-html \
  --approach standalone-html --trial-id trial-001
```

每个目录包含 `TASK.md`、`trial.json`、`assessment.json` 和固定输入数据，不包含完成代码。两边共享同一任务、验收与数据；`TASK.md` 只在必要的 approach 约束上不同。`trial.json` 固定任务契约、approach prompt、各输入文件和聚合 SHA-256；任何一项被改写都会使完整性失败。命令拒绝覆盖非空目录。准备后可以先运行 `dataviz authoring verify DIRECTORY --format json`，此时输入完整性应通过，而尚未执行的质量门禁自然是 `quality_passed: false`。

## 2. 成对试验

一个可比较 trial 必须满足：

- 同一 `benchmark_task` 和 `trial_id`；
- 一次 `dataviz`，一次 `standalone-html`；
- 相同任务文本、模型、客户端/工具、权限、输入数据和时间预算；
- 每次使用新的会话与工作目录，避免第二种方案看到第一种方案的实现；
- 交替或随机安排两种方案顺序，减少顺序偏差。

把任务交给 AI **之前**，先从准备好的 trial 启动计时记录；任务文本、approach、trial id 和哈希由 `trial.json` 提供，不能在命令行重新填写：

```bash
dataviz authoring start MEASUREMENT_WORKSPACE \
  --trial-dir /tmp/trial-001-dataviz \
  --model MODEL_NAME \
  --tool CLIENT_NAME
```

Standalone HTML 方案使用对应的 prepared directory，并保持完全相同的 task contract、fixture digest、`trial-id`、`model` 和 `tool`。

`start` 返回机器可读的 `next_steps`；benchmark 的 finish 命令会自动带回必需的 `--trial-dir`，路径包含空格时也可直接由 shell 使用。

遇到文档、Schema、组件或 Runtime friction 时追加记录：

```bash
dataviz authoring note MEASUREMENT_WORKSPACE SESSION_ID \
  --category documentation \
  --reference "docs selections" \
  --message "没有说明空选择代表全集"
```

AI 完成后，由人、自动化或二者共同为每条验收项记录证据，再复核整个 trial：

```bash
dataviz authoring assess /tmp/trial-001-dataviz state-boundary \
  --status passed --assessor automation \
  --evidence "validate 通过；Playwright 确认 Parameter 需提交而 Selection 即时生效"

dataviz authoring verify /tmp/trial-001-dataviz --format json
```

`passed`/`failed` 必须同时提供 `assessor` 和非空 `evidence`；`unmeasured` 不得伪装成证据。`verify` 会重新计算输入哈希并检查 assessment 的 ID、顺序和状态。它不替代真正的浏览器测试或人工判断，而是让判断依据进入可审计记录。

完成后记录真实结果：

```bash
dataviz authoring finish MEASUREMENT_WORKSPACE SESSION_ID \
  --outcome success \
  --first-attempt failure \
  --correction-rounds 2 \
  --trial-dir /tmp/trial-001-dataviz \
  --input-tokens ACTUAL_INPUT \
  --output-tokens ACTUAL_OUTPUT \
  --docs-used quickstart \
  --docs-used selections
```

`finish` 会再次校验同一个 trial 的 TASK prompt、输入和 assessment。输入被改动、任一验收项未通过，或 start/finish 的契约/prompt 哈希不一致时，不能记录 `outcome=success`。`elapsed_seconds` 由 CLI 自动计算。Token 只接受 AI 客户端提供的真实值；拿不到时省略，保持 `unmeasured`，不能按字符、字节或文件大小推算。

## 3. 比较结果

```bash
dataviz authoring compare MEASUREMENT_WORKSPACE --format json
dataviz authoring compare MEASUREMENT_WORKSPACE \
  --task default-dashboard --format json
```

报告区分：

- `complete_pairs`：两种 approach 都完成；
- `comparable_pairs`：任务文本、固定任务契约、fixture digest、模型和客户端身份一致；
- `quality_pairs`：identity 一致、两边输入完整且每条验收均有证据并通过；
- `paired_aggregate`：只聚合 `quality_pairs`，不会用失败或身份不一致的试验宣称节省；
- `diagnostics`：列出缺失、重复或身份不一致的 trial。

首次成功指第一次实现已经通过该任务所需的 validate、数据契约和页面行为验证。格式化或无行为变化的文案修正不计 correction；修复数据、契约或交互行为算一轮。

## 4. 日志格式

每行是严格的 `dataviz/authoring-event/v3` JSON 事件。日志 append-only，适合 Git diff/merge；损坏行只产生诊断，不覆盖其他历史。旧实验日志不自动迁移或混读。

```bash
dataviz authoring show MEASUREMENT_WORKSPACE --format json
```

不要在 task、notes 或 friction 中写账号密码、原始敏感数据或个人信息。项目在积累足够的重复 trial 之前，只发布评测方法，不发布未经证据支持的 Token 结论。

# AI Authoring 真实评测协议

Dataviz 长期要减少 AI 的输入、输出和试错轮次，但当前不设未经真实任务验证的 Token 目标。每个适合评测的 Workspace 都可以提交根目录下的 `dataviz-authoring.jsonl`，并把它直接分享给 Dataviz 作者。

## 固定流程

```bash
dataviz authoring start WORKSPACE \
  --dashboard DASHBOARD_ID \
  --task "新增一个按区域联动的收入趋势图" \
  --model MODEL_NAME

dataviz authoring note WORKSPACE SESSION_ID \
  --category documentation \
  --reference "docs selections" \
  --message "没有说明空选择代表全集"

dataviz authoring finish WORKSPACE SESSION_ID \
  --outcome success \
  --first-attempt failure \
  --correction-rounds 2 \
  --input-tokens ACTUAL_INPUT \
  --output-tokens ACTUAL_OUTPUT \
  --docs-used quickstart \
  --docs-used selections
```

`elapsed_seconds` 由 CLI 根据 started/finished 时间自动计算。Token 只记录 AI client 提供的真实值；拿不到时省略参数，保存为 `unknown`，不能按 bytes 粗估。

“首次成功”指第一次实现已经通过目标任务所需的 `validate`、Source/Named Output 和页面渲染验证，不需要再次修改实现。格式化、无行为变化的文案修正不计入 correction；为修复契约、数据或交互而重新编辑算一轮。

## 为什么使用 JSONL

每行是独立的 `dataviz/authoring-event/v1` 事件。它是 append-only，适合 Git diff/merge；某一行损坏只产生诊断，不让其余历史消失。`dataviz authoring show WORKSPACE --format json` 会聚合会话与首次成功率、平均修正、耗时和 friction 分类。

不要在 task、notes、friction 中写账号密码、原始敏感数据或个人信息。

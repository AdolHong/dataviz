# Browser Worker 输入与传输兼容

## 使用约定

browser-js Interactive Transform 的数组操作推荐：

```javascript
function transform(context) {
  const item = context.control_inputs.item;
  return {main: context.rows('rows')
    .filter(row => row.item === item)
    .sort((a, b) => b.value - a.value)};
}
```

`rows` 必须为 YAML inputs 中声明的表别名；不是 Output ID。
JSON、Arrow、auto 都返回普通数组及浅拷贝的行对象。
读取时才物化，可能增加内存；大表可保留 `context.table(alias)` 的 Frame API。
Frame.filter 返回 Frame，Frame.sort 使用字段名和方向，不能当作 Array.sort(comparator)。

为兼容既有代码，原始 `context.inputs` / `context.input()` 的类型未强制统一。
旧代码仍需要改用稳定入口；不能将 `Array.isArray(input) === false` 直接解释成空数据。
本能力属于 Interactive Worker，不是 Custom Renderer 或 server-python context 的新增 API。

## 错误边界

rows/table 的未声明别名、null、scalar/object 输入返回结构化
`interactive_input_not_table`，包含 input_alias、input_type、transform_id。
合法空表正常返回空数组。没有放宽服务端或输出校验。
若业务代码自行返回空数组，平台不能仅凭非空上游就判断逻辑错误；
任意筛选代码的中间行数追踪、迁移配置差异报告不在本次实现范围。

## 验证记录

- Worker/作者契约与文档搜索：87 passed，`.test-evidence/worker-rows-contracts-final.log`。
- 三浏览器各 4 passed：强制 JSON、强制 Arrow、auto 阈值两侧，使用相同数组代码，
  连续改变筛选并验证空结果与恢复；检查实际 Arrow 传输指标。
  `.test-evidence/worker-rows-browser-final.log`。
- 首轮新增测试误把合法 empty 断言为 ready，修正等待条件与终态断言后定向复验；
  原始 `.test-evidence/worker-rows-browser.log` 保留。
- 三浏览器原有 Worker 取消/超时/序列化错误用例在首轮均通过。
  核心分析联动另见 `.test-evidence/worker-rows-core.log`。

以上为最初 rows API 的验证记录。后续同类边界修复、全套非浏览器和三浏览器核心验证见
[输入输出一致性审计](io-contract-audit.md)。未升级或打包；配套 Skill 已同步，后续正常构建时随 wheel 分发。

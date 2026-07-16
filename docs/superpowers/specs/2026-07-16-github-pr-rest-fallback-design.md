# GitHub PR REST 回退设计

## 目标

当 `gh pr create` 因 TLS 连接失败而不可用时，AVM 仍能用当前已登录 GitHub 账号创建 PR，并且只在取得真实 PR 信息后推进任务状态。

## 边界

- `gh` 仍是默认实现；正常情况下不改变命令和输出。
- 只为“创建 PR”提供 REST 回退，不扩展到合并、发布、删除分支等写操作。
- REST 回退通过 `gh auth token` 取得既有登录凭据；不读取、打印或持久化 token。
- REST 和 `gh` 都失败时抛出 `GitHubError`，调用方保持当前状态，不写入 PR 编号。

## 数据流

1. `create_pull_request()` 尝试现有 `gh pr create`，再用 `gh pr view` 获取详情。
2. 任一步失败时，执行 `gh auth token`，向 GitHub `POST /repos/{owner}/{repo}/pulls` 发送标题、正文、源分支、目标分支和草稿标记。
3. 将 REST 响应规范为现有调用方使用的 `number`、`html_url`、`state`、`headRefName`、`baseRefName` 字段。
4. 仅在上述任一通道返回完整 PR 后，`run_create_pr()` 才报告成功。

## 错误处理与验证

- 缺少仓库信息或 token、HTTP 非 2xx、响应缺少编号/URL 都失败闭合。
- 单元测试验证：默认路径不使用回退、`gh` 失败后 REST 成功、REST 失败仍拒绝创建。
- 在现有 v6 真实任务上验证分支推送、PR 创建和状态保持的一致性。

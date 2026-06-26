# AVM Agent 配置

## 任务信息

- 版本: v3
- 分支: agent/v3-claude-code
- 状态: BRANCH_READY

## 规则

1. 遵循 AVM 版本管理流程
2. 不得直接推送到 main 分支
3. 所有变更必须通过 PR 审批
4. 提交前运行安全扫描
5. 保持提交消息格式规范

## 验证命令

在提交前运行以下命令:
- `avm validate` - 运行配置的验证命令
- `avm hook pre-commit` - 检查敏感信息

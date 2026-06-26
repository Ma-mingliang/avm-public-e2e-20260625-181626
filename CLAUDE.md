# avm-e2e-test

## AVM 版本管理

本项目使用 Agent Version Manager (AVM) 管理版本。

### 规则

1. 遵循 AVM 版本管理流程
2. 不得直接推送到 main 分支
3. 所有变更必须通过 PR 审批
4. 提交前运行安全扫描: `avm hook pre-commit`
5. 保持提交消息格式规范

### 常用命令

- `avm status` - 查看状态
- `avm preflight` - 预检
- `avm start` - 开始任务
- `avm validate` - 验证
- `avm publish` - 发布

# synthetic-avm-public-e2e - Agent 配置

## 版本管理

使用 AVM (Agent Version Manager) 管理版本。

## 工作流

1. `avm preflight` - 预检
2. `avm start` - 开始任务
3. 执行修改
4. `avm validate` - 验证
5. `avm create-pr` - 创建 PR
6. `avm merge` - 合并
7. `avm publish` - 发布

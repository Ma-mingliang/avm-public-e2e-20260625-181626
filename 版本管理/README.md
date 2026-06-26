# avm-e2e-test - 版本管理

本目录由 Agent Version Manager (AVM) 管理。

## 目录结构

- `正式版本/` - 正式版本记录
- `文档版本/` - 文档版本记录
- `备份/` - 文件备份
- `审批/` - 审批记录
- `交接/` - 交接报告
- `版本索引.json` - 版本索引
- `配置.yaml` - 项目配置

## 使用方法

使用 AVM CLI 管理版本：

```bash
avm status          # 查看状态
avm preflight       # 预检
avm start           # 开始任务
avm validate        # 验证
avm publish         # 发布
```

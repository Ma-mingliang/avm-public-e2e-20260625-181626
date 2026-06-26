# Agent Version Manager (AVM)

智能体版本管理器 — 为 Claude Code、Hermes、Codex 等 AI Agent 提供结构化的版本发布工作流。

AVM 通过状态机驱动的任务生命周期、HMAC 签名审批、安全扫描和 GitHub 集成，确保 Agent 修改代码的过程可追踪、可审计、可回滚。

## 功能特性

- **状态机驱动** — 25+ 个状态的显式转换矩阵，防止非法操作
- **多 Agent 支持** — Claude Code、Hermes、Codex 适配器
- **HMAC 审批** — 基于密钥签名的不可伪造审批记录，绑定文件内容哈希
- **安全扫描** — 检测敏感文件（.env、*.pem、*.key）和密钥泄露
- **任务分类** — 自动区分代码修改、文档修改、只读任务
- **GitHub 集成** — PR 创建、合并、标签、Release 全流程
- **备份与回滚** — 任务级和配置级备份，支持回滚到任意历史版本
- **断点恢复** — 中断的任务可从断点恢复或安全废弃

## 系统要求

- Python >= 3.11
- Git >= 2.30
- GitHub CLI (`gh`) >= 2.40（用于 GitHub 集成）
- Windows 10/11、macOS 13+、Linux（Ubuntu 22.04+）

## 安装

### pip 安装（推荐）

```bash
# 克隆仓库
git clone https://github.com/your-org/AgentVersionManager.git
cd AgentVersionManager

# 安装（开发模式）
pip install -e .

# 安装含开发依赖
pip install -e ".[dev]"
```

### PowerShell 安装

```powershell
# 设置执行策略（如需要）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 克隆并安装
git clone https://github.com/your-org/AgentVersionManager.git
cd AgentVersionManager
python -m pip install -e .

# 验证安装
python -m avm --version
```

### 验证安装

```bash
# 检查环境
avm doctor

# 或使用模块方式
python -m avm doctor
```

## 快速开始

```bash
# 1. 检查环境依赖
avm doctor

# 2. 初始化项目（在 Git 仓库中运行）
avm init-project

# 3. 查看项目状态
avm status

# 4. 开始一个版本任务
avm start

# 5. Agent 执行代码修改...

# 6. 提交检查点
avm checkpoint

# 7. 运行验证
avm validate

# 8. 准备审阅材料
avm prepare-review

# 9. 用户审批
avm approve --approver "张三"

# 10. 创建 PR
avm create-pr

# 11. 发布版本（合并 + 标签 + Release）
avm publish
```

## 命令参考

### 环境与配置

| 命令 | 说明 | 示例 |
|------|------|------|
| `doctor` | 检查 Python、Git、gh CLI、项目配置 | `avm doctor` |
| `init-project` | 初始化项目目录结构和配置 | `avm init-project` |
| `install` | 安装 AVM 到系统 | `avm install` |
| `update-check` | 检查是否有新版本 | `avm update-check` |
| `update` | 更新 AVM | `avm update` |
| `rollback` | 回滚到上一版本 | `avm rollback` |

### 任务生命周期

| 命令 | 说明 | 示例 |
|------|------|------|
| `status` | 显示项目和任务状态 | `avm status --json` |
| `start` | 开始新版本任务 | `avm start --version v1.2.0` |
| `preflight` | 修改前预检（安全扫描、任务分类） | `avm preflight --files file1.py file2.py` |
| `checkpoint` | 阶段提交（记录修改进度） | `avm checkpoint` |
| `validate` | 运行测试和验证 | `avm validate` |
| `prepare-review` | 准备审阅材料 | `avm prepare-review` |
| `approve` | 用户审批（HMAC 签名） | `avm approve --approver "张三" --notes "LGTM"` |
| `create-pr` | 创建 GitHub PR | `avm create-pr` |
| `merge` | 合并 PR | `avm merge` |
| `publish` | 发布版本（标签 + Release） | `avm publish` |

### 任务恢复

| 命令 | 说明 | 示例 |
|------|------|------|
| `resume` | 恢复中断的任务 | `avm resume` |
| `abandon` | 废弃当前任务（仅从 INTERRUPTED 状态） | `avm abandon` |
| `recover` | 从备份恢复 | `avm recover` |

### 文档版本

| 命令 | 说明 | 示例 |
|------|------|------|
| `document-start` | 开始文档版本任务 | `avm document-start --files readme.md` |
| `document-complete` | 完成文档版本 | `avm document-complete` |
| `archive-pending-docs` | 归档待处理文档 | `avm archive-pending-docs` |

### 备份管理

| 命令 | 说明 | 示例 |
|------|------|------|
| `backup-list` | 列出任务备份 | `avm backup-list` |
| `backup-restore` | 恢复任务备份 | `avm backup-restore --name backup-001` |
| `config-backup-list` | 列出配置备份 | `avm config-backup-list` |
| `config-restore` | 恢复配置 | `avm config-restore --name config-001` |

### Agent 与 Hook

| 命令 | 说明 | 示例 |
|------|------|------|
| `launch` | 启动 Agent | `avm launch --agent claude-code --task "修复 bug"` |
| `hook` | Git Hook 处理（由 Git 自动调用） | `avm hook pre-commit` |

## 状态机

任务生命周期的状态转换：

```
IDLE → PREFLIGHT → WAIT_START_APPROVAL → RESERVED → LOCKED
  → BRANCH_READY → MODIFYING → VALIDATING
  → REVIEW_MATERIAL_READY → WAIT_FINAL_APPROVAL
  → PR_READY → MERGING → TAGGING → RELEASING
  → HANDOFF_UPDATING → CLEANING → COMPLETE → IDLE
```

异常分支：
- 任何活动状态 → `INTERRUPTED`（可恢复到多个状态）
- `INTERRUPTED` → `ABANDONED` → `IDLE`
- 任何活动状态 → `AUTH_BLOCKED` / `NETWORK_BLOCKED` / `SECURITY_BLOCKED`
- `MERGING` / `TAGGING` / `RELEASING` → `PUBLISH_INCOMPLETE`（可重试）

## 配置

项目配置文件位于 `版本管理/config.yaml`：

```yaml
# 项目配置
project:
  name: "my-project"
  description: "项目描述"

# 风险控制
risk:
  extra_file_limit: 5          # 单次任务最大文件数
  expansion_ratio: 0.5         # 范围扩展比例
  sensitive_patterns: []       # 自定义敏感模式

# Agent 配置
agents:
  claude_code:
    enabled: true
  hermes:
    enabled: false
  codex:
    enabled: false
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AVM_HMAC_KEY` | HMAC 签名密钥（覆盖 keyring） | 自动生成 |
| `AVM_LOG_LEVEL` | 日志级别 | `INFO` |
| `AVM_NO_KEYRING` | 禁用 keyring | `false` |

## 开发

### 安装开发依赖

```bash
pip install -e ".[dev]"
```

### 运行测试

```bash
# 全部测试
pytest

# 带覆盖率
pytest --cov=src/avm --cov-report=term-missing

# 仅单元测试
pytest tests/unit/

# 仅集成测试
pytest tests/integration/
```

### 代码质量

```bash
# Lint 检查
ruff check src/ tests/

# 格式化
ruff format src/ tests/

# 类型检查
mypy src/avm/
```

### 项目结构

```
AgentVersionManager/
├── src/avm/
│   ├── cli.py              # Typer CLI 入口
│   ├── models.py           # Pydantic 数据模型
│   ├── exceptions.py       # 自定义异常
│   ├── adapters/           # Agent 适配器（Claude Code、Hermes、Codex）
│   ├── commands/           # 命令实现
│   ├── core/               # 核心模块（状态机、审批、安全扫描、分类器）
│   ├── git/                # Git 操作封装
│   └── github/             # GitHub API 客户端
├── tests/
│   ├── unit/               # 单元测试
│   └── integration/        # 集成测试
├── pyproject.toml          # 项目配置
└── .github/workflows/      # CI/CD
```

## 当前实现状态

| 功能 | 状态 | 说明 |
|------|------|------|
| 状态机 | ✅ 完成 | 25+ 状态，完整转换矩阵 |
| 审批系统 | ✅ 完成 | HMAC-SHA256 签名，4 小时有效期 |
| 安全扫描 | ✅ 完成 | 检测敏感文件和密钥泄露 |
| 任务分类 | ✅ 完成 | 自动识别代码/文档/只读任务 |
| Git 操作 | ✅ 完成 | 分支、提交、标签、差异比较 |
| GitHub 集成 | ✅ 完成 | PR、Release、工作流监控 |
| 备份恢复 | ✅ 完成 | 任务级和配置级备份 |
| CLI 命令 | ✅ 完成 | 28 个命令，支持 JSON 输出 |
| Agent 适配器 | ⚠️ 基础 | 框架就绪，具体 Agent 集成需扩展 |
| 远程锁 | ⚠️ 基础 | 本地锁完整，远程锁需 GitHub 环境 |
| LFS 建议 | ⚠️ 提示 | 检测大文件并提示，不自动配置 |

## 故障排查

### "不是 Git 仓库"

```bash
cd your-project
git init
git add .
git commit -m "initial commit"
```

### "gh CLI 未安装"

```bash
# Windows (winget)
winget install GitHub.cli

# macOS
brew install gh

# Linux (Debian/Ubuntu)
sudo apt install gh

# 认证
gh auth login
```

### "审批已过期"

审批有效期为 4 小时。重新运行 `avm approve` 生成新审批。

### "状态转换失败"

当前状态不支持目标操作。查看合法转换：

```bash
avm status
```

### "安全扫描阻塞"

敏感文件（.env、*.pem、*.key）被检测到。将它们加入 `.gitignore` 或从任务范围中移除。

## 许可证

MIT License
# E2E test

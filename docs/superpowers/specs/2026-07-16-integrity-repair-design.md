# AVM 完整性修复设计

## 目标

将 AVM 从“正常路径可运行的 Beta”提升为在篡改、并发、部分成功、网络故障和进程中断下仍能保持关键不变量的发布系统。保留现有 CLI 入口和可兼容的数据字段，但安全决策一律 fail-closed。

## 核心不变量

1. 每次审批只授权一个不可变的发布主体：仓库身份、base SHA、head/tree SHA、完整变更清单、配置哈希、PR base/head、版本和发布策略。
2. 本地状态只是操作日志与缓存；Git 和 GitHub 上已发生的事实必须重新查询和验证。
3. 每个远端步骤必须幂等：对象不存在时创建；存在且内容一致时视为成功；存在但内容不同则阻断。
4. 只有所有发布与清理后置条件均验证成功，任务才能进入 COMPLETE 和 IDLE。
5. 状态、密钥或远端事实不可读取时不得推断为安全状态。

## 架构

### 1. 可信状态存储

统一 `StateMachine` 和 `TaskLocker` 的状态读取语义。任务锁加入单调递增的 revision，并通过 `filelock` 串行化进程内外的读改写。JSON 损坏、schema 不兼容或 revision 冲突均抛出明确错误，不再构造 IDLE。原损坏文件保留用于恢复和审计。

远程锁包含 task ID、repository、base SHA 和 owner。创建失败、已存在或无法验证时阻断启动；只有验证锁属于当前任务后才允许删除。

### 2. 不可变审批主体

引入规范化的 `ReleaseSubject` 数据结构，至少包含：repository、base SHA、head SHA、tree SHA、完整 Git diff manifest、配置哈希、版本、目标分支、PR 编号及发布策略。最终审批签署其规范 JSON 的 SHA-256。

审批验证同时检查审批类型、task ID、有效期、HMAC、subject hash 和实际远端 PR head/base。审批后任何提交、树、配置或策略变化均使审批失效。

HMAC 密钥统一以 hex 编码存入 keyring、解码为原始字节使用。环境变量使用显式编码规则。keyring 不可用且未配置环境密钥时拒绝创建或验证审批，不再使用机器信息派生的确定性密钥。

### 3. Git 与安全扫描

Git 状态解析使用 NUL 分隔和 porcelain v2 固定字段语义，覆盖空格、中文、重命名、删除及冲突路径。安全扫描读取 Git index 中实际待提交的 blob，而不是工作区文件。

无法枚举或读取任一 staged blob、正则配置非法、扫描器内部异常时返回阻断结果。pre-push 解析 Git 传入的 ref 更新，不以当前分支替代实际推送目标。

### 4. PR、CI 与 Publish Saga

合并前验证：审批主体一致、PR 为 OPEN 且非 draft、base 为配置默认分支、head SHA 等于审批 SHA、required checks 明确成功。认证、网络或 CI 查询错误均阻断；只有配置显式声明允许无 CI 时才能跳过。

Publish 依据远端事实推进：

1. 验证 merge SHA 存在且位于默认分支；
2. 确保 tag 指向精确 merge SHA；
3. 生成内容稳定的 release manifest；
4. 确保 Release 存在且包含同一 manifest；
5. 验证远程锁、远程分支和本地分支清理结果；
6. 全部后置条件成立后才进入 COMPLETE，再回到 IDLE。

每一步记录 operation 状态和远端对象标识。调用成功但响应丢失时，重试通过事实查询收敛。清理未完成时保留 `PUBLISH_INCOMPLETE`，不得报告成功。

Manifest 不包含创建后才可知、又会改变自身哈希的字段。Release URL 作为发布结果元数据存入任务状态，不参与已发布 manifest 的内容哈希。

### 5. 备份恢复与自更新

备份索引显式记录 `kind=file|directory`、相对文件清单和哈希，所有索引路径必须限制在备份根目录内。目录恢复先在同卷临时位置构建并验证，再将旧目标改名为回滚副本、替换新目标，成功后删除副本；任一步失败恢复旧目标。

更新备份保存实际可重新安装的 wheel、版本和 SHA-256。回滚通过校验并重新安装旧 wheel 完成，不再只改 `version.json`。`update-check` 查询真实包索引；查询失败报告未知，不伪报最新或有更新。

## 兼容性与迁移

- 保留现有 CLI 命令和主要 JSON 输出字段。
- 旧任务锁缺少 revision 时按 revision 0 迁移；损坏或含未知关键状态的锁不自动迁移。
- 旧审批记录因缺少 ReleaseSubject 视为无效，要求重新审批。
- 旧备份索引可读取；无法可靠判定单文件目录的旧记录只允许显式指定恢复类型。
- 新增配置项采用安全默认值，现有宽松行为必须显式开启。

## 错误处理

错误按 `STATE_CORRUPTED`、`APPROVAL_INVALIDATED`、`AUTH_BLOCKED`、`NETWORK_BLOCKED`、`SECURITY_BLOCKED` 和 `PUBLISH_INCOMPLETE` 分类。错误信息包含失败操作和可执行恢复动作，但不得泄露 secret、HMAC 或完整令牌。所有布尔型外部操作必须检查返回值并验证后置条件。

## 测试策略

所有修复采用红—绿—重构：先加入可重复失败测试，再改生产代码。

必须覆盖：

- 审批后新增提交、改树、改配置、换 PR head/base；
- 损坏状态文件、revision 冲突和多进程并发 start；
- staged secret/安全 worktree 绕过、空格/中文/重命名路径；
- tag 已推送但响应丢失、Release 已存在、manifest 冲突、清理返回 false；
- CI 查询失败、merge SHA 为空或不在默认分支；
- 单文件目录备份、路径逃逸、替换中断和恢复回滚；
- wheel 更新失败及真实回滚；
- 真实 CLI 生命周期与临时 bare remote 集成测试。

最终门禁：全量 pytest 通过；Ruff、格式、Pyright、compileall、构建和 secret scan 通过；关键安全/发布模块分支覆盖率不低于 90%，整体覆盖率不低于 85%。

## 实施阶段

1. 可信状态存储与审批主体；
2. Git 解析、index 安全扫描与 hook；
3. PR/CI 验证与幂等 Publish Saga；
4. 备份恢复与更新回滚；
5. 真实 E2E、CI 门禁、README/LICENSE 和交付一致性。

每阶段独立通过回归测试后再进入下一阶段，不把跨阶段的未验证行为组合成一次大改。

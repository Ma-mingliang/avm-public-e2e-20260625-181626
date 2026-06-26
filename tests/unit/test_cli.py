"""AVM CLI 入口测试"""

from unittest.mock import patch

from typer.testing import CliRunner

from avm.cli import app

runner = CliRunner()


class TestVersionCallback:
    """版本回调测试"""

    def test_version_flag(self):
        """测试 --version 标志"""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "AVM" in result.output


class TestDoctorCommand:
    """doctor 命令测试"""

    @patch("avm.commands.doctor.run_doctor", return_value=True)
    def test_doctor_success(self, mock_doctor):
        """测试 doctor 成功"""
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        mock_doctor.assert_called_once()

    @patch("avm.commands.doctor.run_doctor", return_value=False)
    def test_doctor_failure(self, mock_doctor):
        """测试 doctor 失败"""
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1

    @patch("avm.commands.doctor.run_doctor", return_value=True)
    def test_doctor_with_project(self, mock_doctor):
        """测试 doctor 指定项目路径"""
        result = runner.invoke(app, ["doctor", "--project", "/tmp/test"])
        assert result.exit_code == 0

    @patch("avm.commands.doctor.run_doctor", return_value=True)
    def test_doctor_json(self, mock_doctor):
        """测试 doctor JSON 输出"""
        result = runner.invoke(app, ["doctor", "--json"])
        assert result.exit_code == 0


class TestPreflightCommand:
    """preflight 命令测试"""

    @patch("avm.commands.preflight.run_preflight", return_value=True)
    def test_preflight_success(self, mock_preflight):
        """测试 preflight 成功"""
        result = runner.invoke(app, ["preflight"])
        assert result.exit_code == 0

    @patch("avm.commands.preflight.run_preflight", return_value=False)
    def test_preflight_failure(self, mock_preflight):
        """测试 preflight 失败"""
        result = runner.invoke(app, ["preflight"])
        assert result.exit_code == 1


class TestStartCommand:
    """start 命令测试"""

    @patch("avm.commands.start.run_start", return_value=True)
    def test_start_success(self, mock_start):
        """测试 start 成功"""
        result = runner.invoke(app, ["start"])
        assert result.exit_code == 0

    @patch("avm.commands.start.run_start", return_value=False)
    def test_start_failure(self, mock_start):
        """测试 start 失败"""
        result = runner.invoke(app, ["start"])
        assert result.exit_code == 1

    @patch("avm.commands.start.run_start", return_value=True)
    def test_start_with_version(self, mock_start):
        """测试 start 指定版本"""
        result = runner.invoke(app, ["start", "--version", "v5"])
        assert result.exit_code == 0


class TestValidateCommand:
    """validate 命令测试"""

    @patch("avm.commands.validate.run_validate", return_value=True)
    def test_validate_success(self, mock_validate):
        """测试 validate 成功"""
        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 0

    @patch("avm.commands.validate.run_validate", return_value=False)
    def test_validate_failure(self, mock_validate):
        """测试 validate 失败"""
        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 1


class TestApproveCommand:
    """approve 命令测试"""

    @patch("avm.commands.approve.run_approve", return_value=True)
    def test_approve_success(self, mock_approve):
        """测试 approve 成功"""
        result = runner.invoke(app, ["approve"])
        assert result.exit_code == 0

    @patch("avm.commands.approve.run_approve", return_value=False)
    def test_approve_failure(self, mock_approve):
        """测试 approve 失败"""
        result = runner.invoke(app, ["approve"])
        assert result.exit_code == 1


class TestPrepareReviewCommand:
    """prepare-review 命令测试"""

    @patch("avm.commands.review.run_prepare_review", return_value=True)
    def test_prepare_review_success(self, mock_review):
        """测试 prepare-review 成功"""
        result = runner.invoke(app, ["prepare-review"])
        assert result.exit_code == 0

    @patch("avm.commands.review.run_prepare_review", return_value=False)
    def test_prepare_review_failure(self, mock_review):
        """测试 prepare-review 失败"""
        result = runner.invoke(app, ["prepare-review"])
        assert result.exit_code == 1


class TestCreatePrCommand:
    """create-pr 命令测试"""

    @patch("avm.commands.pr.run_create_pr", return_value=True)
    def test_create_pr_success(self, mock_pr):
        """测试 create-pr 成功"""
        result = runner.invoke(app, ["create-pr"])
        assert result.exit_code == 0

    @patch("avm.commands.pr.run_create_pr", return_value=True)
    def test_create_pr_draft(self, mock_pr):
        """测试 create-pr 草稿"""
        result = runner.invoke(app, ["create-pr", "--draft"])
        assert result.exit_code == 0


class TestMergeCommand:
    """merge 命令测试"""

    @patch("avm.commands.pr.run_merge", return_value=True)
    def test_merge_success(self, mock_merge):
        """测试 merge 成功"""
        result = runner.invoke(app, ["merge"])
        assert result.exit_code == 0

    @patch("avm.commands.pr.run_merge", return_value=False)
    def test_merge_failure(self, mock_merge):
        """测试 merge 失败"""
        result = runner.invoke(app, ["merge"])
        assert result.exit_code == 1


class TestPublishCommand:
    """publish 命令测试"""

    @patch("avm.commands.publish.run_publish", return_value=True)
    def test_publish_success(self, mock_publish):
        """测试 publish 成功"""
        result = runner.invoke(app, ["publish"])
        assert result.exit_code == 0

    @patch("avm.commands.publish.run_publish", return_value=False)
    def test_publish_failure(self, mock_publish):
        """测试 publish 失败"""
        result = runner.invoke(app, ["publish"])
        assert result.exit_code == 1


class TestRecoveryCommands:
    """recovery 命令测试"""

    @patch("avm.commands.recovery.run_resume", return_value=True)
    def test_resume_success(self, mock_resume):
        """测试 resume 成功"""
        result = runner.invoke(app, ["resume"])
        assert result.exit_code == 0

    @patch("avm.commands.recovery.run_abandon", return_value=True)
    def test_abandon_success(self, mock_abandon):
        """测试 abandon 成功"""
        result = runner.invoke(app, ["abandon"])
        assert result.exit_code == 0

    @patch("avm.commands.recovery.run_recover", return_value=True)
    def test_recover_success(self, mock_recover):
        """测试 recover 成功"""
        result = runner.invoke(app, ["recover"])
        assert result.exit_code == 0


class TestDocumentCommands:
    """document 命令测试"""

    @patch("avm.commands.document.run_document_start", return_value=True)
    def test_document_start_success(self, mock_start):
        """测试 document-start 成功"""
        result = runner.invoke(app, ["document-start"])
        assert result.exit_code == 0

    @patch("avm.commands.document.run_document_complete", return_value=True)
    def test_document_complete_success(self, mock_complete):
        """测试 document-complete 成功"""
        result = runner.invoke(app, ["document-complete"])
        assert result.exit_code == 0

    @patch("avm.commands.document.run_archive_pending_docs", return_value=True)
    def test_archive_pending_docs_success(self, mock_archive):
        """测试 archive-pending-docs 成功"""
        result = runner.invoke(app, ["archive-pending-docs"])
        assert result.exit_code == 0


class TestBackupCommands:
    """backup 命令测试"""

    @patch("avm.commands.backup.run_backup_list", return_value=True)
    def test_backup_list_success(self, mock_list):
        """测试 backup-list 成功"""
        result = runner.invoke(app, ["backup-list"])
        assert result.exit_code == 0

    @patch("avm.commands.backup.run_backup_restore", return_value=True)
    def test_backup_restore_success(self, mock_restore):
        """测试 backup-restore 成功"""
        result = runner.invoke(app, ["backup-restore", "--id", "backup-001"])
        assert result.exit_code == 0


class TestConfigCommands:
    """config 命令测试"""

    @patch("avm.commands.config.run_config_backup_list", return_value=True)
    def test_config_backup_list_success(self, mock_list):
        """测试 config-backup-list 成功"""
        result = runner.invoke(app, ["config-backup-list"])
        assert result.exit_code == 0

    @patch("avm.commands.config.run_config_restore", return_value=True)
    def test_config_restore_success(self, mock_restore):
        """测试 config-restore 成功"""
        result = runner.invoke(app, ["config-restore", "--id", "config-001"])
        assert result.exit_code == 0


class TestStatusCommand:
    """status 命令测试"""

    @patch("avm.commands.status.run_status", return_value=True)
    def test_status_success(self, mock_status):
        """测试 status 成功"""
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0

    @patch("avm.commands.status.run_status", return_value=False)
    def test_status_failure(self, mock_status):
        """测试 status 失败"""
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 1


class TestCheckpointCommand:
    """checkpoint 命令测试"""

    @patch("avm.commands.checkpoint.run_checkpoint", return_value=True)
    def test_checkpoint_success(self, mock_checkpoint):
        """测试 checkpoint 成功"""
        result = runner.invoke(app, ["checkpoint"])
        assert result.exit_code == 0


class TestLaunchCommand:
    """launch 命令测试"""

    @patch("avm.commands.launch.run_launch", return_value=True)
    def test_launch_success(self, mock_launch):
        """测试 launch 成功"""
        result = runner.invoke(app, ["launch", "claude"])
        assert result.exit_code == 0


class TestInstallCommand:
    """install 命令测试"""

    @patch("avm.commands.install.run_install", return_value=True)
    def test_install_success(self, mock_install):
        """测试 install 成功"""
        result = runner.invoke(app, ["install"])
        assert result.exit_code == 0


class TestUpdateCommands:
    """update 命令测试"""

    @patch("avm.commands.update.run_update_check", return_value=False)
    def test_update_check_no_update(self, mock_check):
        """测试 update-check 无更新"""
        result = runner.invoke(app, ["update-check"])
        assert result.exit_code == 2

    @patch("avm.commands.update.run_update", return_value=True)
    def test_update_success(self, mock_update):
        """测试 update 成功"""
        result = runner.invoke(app, ["update"])
        assert result.exit_code == 0

    @patch("avm.commands.update.run_rollback", return_value=True)
    def test_rollback_success(self, mock_rollback):
        """测试 rollback 成功"""
        result = runner.invoke(app, ["rollback"])
        assert result.exit_code == 0


class TestInitProjectCommand:
    """init-project 命令测试"""

    @patch("avm.commands.init_project.run_init_project", return_value=True)
    def test_init_project_success(self, mock_init):
        """测试 init-project 成功"""
        result = runner.invoke(app, ["init-project"])
        assert result.exit_code == 0

"""Tests for shell command execution utilities."""

import os
import platform
import pytest

from serena.util.shell import execute_shell_command, _validate_command_safety


class TestShellCommandExecution:
    """Test shell command execution functionality."""

    def test_simple_command_execution(self):
        """Test basic command execution works on all platforms."""
        # Use a simple command that works on both Windows and Unix
        if platform.system() == "Windows":
            result = execute_shell_command("echo hello")
        else:
            result = execute_shell_command("echo hello")
        
        assert result.return_code == 0
        assert "hello" in result.stdout.lower()
        assert result.cwd is not None

    def test_command_with_stderr(self):
        """Test command execution with stderr capture."""
        if platform.system() == "Windows":
            # Use a command that generates stderr on Windows
            result = execute_shell_command("echo error 1>&2", capture_stderr=True)
        else:
            result = execute_shell_command("echo error >&2", capture_stderr=True)
        
        assert result.stderr is not None

    def test_command_with_custom_cwd(self, tmp_path):
        """Test command execution with custom working directory."""
        result = execute_shell_command("pwd" if platform.system() != "Windows" else "cd", cwd=str(tmp_path))
        
        assert result.return_code == 0
        assert str(tmp_path) in result.stdout or str(tmp_path) in result.cwd

    def test_nonzero_return_code(self):
        """Test handling of commands with non-zero return codes."""
        if platform.system() == "Windows":
            result = execute_shell_command("exit 1")
        else:
            result = execute_shell_command("exit 1")
        
        assert result.return_code == 1

    def test_command_safety_validation(self):
        """Test that dangerous commands are blocked."""
        dangerous_commands = [
            "rm -rf /",
            "del /s /q C:\\",
            "format c:",
            "shutdown -h now",
            "dd if=/dev/zero of=/dev/sda",
        ]
        
        for cmd in dangerous_commands:
            with pytest.raises(ValueError, match="Command blocked for safety"):
                _validate_command_safety(cmd)

    def test_safe_command_validation(self):
        """Test that safe commands pass validation."""
        safe_commands = [
            "echo hello",
            "ls -la",
            "dir",
            "python --version",
            "git status",
        ]
        
        for cmd in safe_commands:
            # Should not raise any exception
            _validate_command_safety(cmd)


class TestShellCommandResult:
    """Test ShellCommandResult model."""

    def test_result_model_creation(self):
        """Test creating ShellCommandResult instances."""
        from serena.util.shell import ShellCommandResult
        
        result = ShellCommandResult(
            stdout="test output",
            return_code=0,
            cwd="/tmp",
            stderr=None
        )
        
        assert result.stdout == "test output"
        assert result.return_code == 0
        assert result.cwd == "/tmp"
        assert result.stderr is None

    def test_result_model_with_stderr(self):
        """Test ShellCommandResult with stderr."""
        from serena.util.shell import ShellCommandResult
        
        result = ShellCommandResult(
            stdout="output",
            return_code=1,
            cwd="/tmp",
            stderr="error message"
        )
        
        assert result.stderr == "error message"
        assert result.return_code == 1
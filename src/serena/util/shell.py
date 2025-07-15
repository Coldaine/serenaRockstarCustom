import logging
import os
import platform
import subprocess
from typing import List

from pydantic import BaseModel

log = logging.getLogger(__name__)


class ShellCommandResult(BaseModel):
    stdout: str
    return_code: int
    cwd: str
    stderr: str | None = None


# Dangerous command patterns to block
DANGEROUS_PATTERNS = [
    r'rm\s+-rf\s+/',
    r'del\s+/[sq]',
    r'format\s+[a-z]:',
    r'shutdown\s+',
    r'reboot',
    r'halt',
    r'poweroff',
    r'init\s+0',
    r'init\s+6',
    r'dd\s+if=.*of=/dev/',
    r'mkfs\.',
    r'fdisk\s+',
    r'parted\s+',
]


def _validate_command_safety(command: str) -> None:
    """
    Validate that a command is not obviously dangerous.
    
    :param command: The command to validate
    :raises ValueError: If the command appears dangerous
    """
    import re
    
    command_lower = command.lower().strip()
    
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command_lower):
            raise ValueError(f"Command blocked for safety: matches dangerous pattern '{pattern}'")
    
    log.debug(f"Command safety validation passed: {command[:50]}{'...' if len(command) > 50 else ''}")


def execute_shell_command(command: str, cwd: str | None = None, capture_stderr: bool = False) -> ShellCommandResult:
    """
    Execute a shell command and return the output.

    :param command: The command to execute.
    :param cwd: The working directory to execute the command in. If None, the current working directory will be used.
    :param capture_stderr: Whether to capture the stderr output.
    :return: The output of the command.
    :raises ValueError: If the command appears dangerous.
    :raises subprocess.SubprocessError: If the command execution fails.
    """
    if cwd is None:
        cwd = os.getcwd()

    # Validate command safety
    _validate_command_safety(command)
    
    log.debug(f"Executing shell command: {command[:100]}{'...' if len(command) > 100 else ''}")
    log.debug(f"Working directory: {cwd}")

    is_windows = platform.system() == "Windows"
    
    try:
        # Use shell=True consistently across platforms for better compatibility
        # This fixes the Windows issue where shell=False expects a list but gets a string
        process = subprocess.Popen(
            command,
            shell=True,  # Changed: Use shell=True on all platforms
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE if capture_stderr else subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if is_windows else 0,  # type: ignore
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
        )

        stdout, stderr = process.communicate()
        
        result = ShellCommandResult(
            stdout=stdout, 
            stderr=stderr, 
            return_code=process.returncode, 
            cwd=cwd
        )
        
        log.debug(f"Command completed with return code: {process.returncode}")
        if process.returncode != 0:
            log.warning(f"Command failed with return code {process.returncode}: {command[:50]}{'...' if len(command) > 50 else ''}")
            if stderr:
                log.warning(f"Command stderr: {stderr[:200]}{'...' if len(stderr) > 200 else ''}")
        
        return result
        
    except subprocess.SubprocessError as e:
        log.error(f"Subprocess error executing command '{command[:50]}{'...' if len(command) > 50 else ''}': {e}")
        raise
    except Exception as e:
        log.error(f"Unexpected error executing command '{command[:50]}{'...' if len(command) > 50 else ''}': {e}")
        raise subprocess.SubprocessError(f"Command execution failed: {e}") from e


def subprocess_check_output(args: list[str], encoding: str = "utf-8", strip: bool = True, timeout: float | None = None) -> str:
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stderr": subprocess.PIPE,
        "timeout": timeout,
        "env": os.environ.copy(),
    }
    if platform.system() == "Windows":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore
    output = subprocess.check_output(args, **kwargs).decode(encoding)  # type: ignore
    if strip:
        output = output.strip()
    return output

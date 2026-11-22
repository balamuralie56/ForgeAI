"""
Runs the check command the user configured for a project (usually its test
suite) and captures the result for the assistant to act on.

Only the user ever sets this command - nothing the model writes is
executed. It runs without a shell (so `&&`, pipes and redirection are not
interpreted), inside the project folder, with a timeout that stops the whole
process tree.
"""

import logging
import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from ..models import CheckResult

logger = logging.getLogger("ForgeAI.Plugins.Assistant.CheckRunner")

_HEAD_CHARS = 1500
_TAIL_CHARS = 6000
_PYTHON_NAMES = frozenset({"python", "python3", "py"})


def split_command(command: str) -> List[str]:
    """
    Splits a command line into arguments the way the local shell would
    quote them, without interpreting any shell syntax.

    Args:
        command (str): The command line.

    Returns:
        List[str]: The argument vector.

    Raises:
        ValueError: If the command has unbalanced quotes or is empty.
    """
    if os.name == "nt":
        parts = shlex.split(command, posix=False)
        args = [
            p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'" else p
            for p in parts
        ]
    else:
        args = shlex.split(command)
    if not args:
        raise ValueError("The check command is empty.")
    return args


def _project_python(root: Path) -> Optional[str]:
    """Returns the project's own virtualenv interpreter, if it has one."""
    for venv in (".venv", "venv"):
        for relative in ("Scripts/python.exe", "bin/python"):
            candidate = root / venv / relative
            if candidate.is_file():
                return str(candidate)
    return None


def _trim_output(output: str) -> str:
    if len(output) <= _HEAD_CHARS + _TAIL_CHARS:
        return output
    hidden = len(output) - _HEAD_CHARS - _TAIL_CHARS
    return (
        output[:_HEAD_CHARS]
        + f"\n... {hidden} characters of output not shown ...\n"
        + output[-_TAIL_CHARS:]
    )


def _kill_tree(process: subprocess.Popen) -> None:
    """Stops a process and everything it started."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=30,
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning(f"Could not stop process tree {process.pid}: {e}")
        process.kill()


class CheckRunner:
    """Runs a project's check command."""

    def run(self, command: str, project_root: Path, timeout: float) -> CheckResult:
        """
        Runs the check command in the project folder.

        A leading `python`/`python3`/`py` is replaced with the project's own
        `.venv`/`venv` interpreter when it has one, so tests run against the
        project's dependencies.

        Args:
            command (str): The command line the user configured.
            project_root (Path): The project folder (working directory).
            timeout (float): Seconds before the command is stopped.

        Returns:
            CheckResult: Exit code, trimmed output and timing. Never raises
            for a failing or missing command; the failure is in the result.
        """
        started = time.perf_counter()
        try:
            args = split_command(command)
        except ValueError as e:
            return CheckResult(command, [], None, False, "", 0.0, error=str(e))

        if args[0].lower() in _PYTHON_NAMES:
            venv_python = _project_python(project_root)
            if venv_python:
                args[0] = venv_python
        executable = shutil.which(args[0], path=os.environ.get("PATH")) or (
            args[0] if Path(args[0]).is_file() else None
        )
        if executable is None:
            return CheckResult(
                command,
                args,
                None,
                False,
                "",
                0.0,
                error=f"'{args[0]}' was not found on this computer's PATH.",
            )
        args[0] = executable

        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUNBUFFERED", "1")
        popen_kwargs: dict = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        logger.info(f"Running check command in {project_root}: {args}")
        try:
            process = subprocess.Popen(
                args,
                cwd=str(project_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                **popen_kwargs,
            )
        except OSError as e:
            return CheckResult(
                command, args, None, False, "", 0.0, error=f"Could not start: {e}"
            )

        timed_out = False
        try:
            raw, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(process)
            raw, _ = process.communicate()
        duration = time.perf_counter() - started
        output = _trim_output((raw or b"").decode("utf-8", errors="replace"))
        exit_code = None if timed_out else process.returncode
        result = CheckResult(
            command=command,
            resolved_command=args,
            exit_code=exit_code,
            passed=exit_code == 0,
            output=output.replace("\r\n", "\n"),
            duration_seconds=round(duration, 2),
            timed_out=timed_out,
            error=f"Stopped after {timeout:.0f}s." if timed_out else "",
        )
        logger.info(
            f"Check command finished: exit={exit_code} timed_out={timed_out} "
            f"in {duration:.1f}s"
        )
        return result

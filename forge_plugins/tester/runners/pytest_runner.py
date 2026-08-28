"""
Pytest runner to execute tests within the target workspace.
"""

import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("ForgeAI.Plugins.Tester.Runners")


class PytestRunner:
    """
    Executes pytest tests in the target workspace directory and parses execution results.
    """

    def run_tests(self, workspace_path: str) -> Dict[str, Any]:
        """
        Executes pytest in the workspace directory.

        Args:
            workspace_path (str): Root of the target workspace.

        Returns:
            Dict[str, Any]: Parsed execution statistics.
        """
        base_dir = Path(workspace_path).resolve()
        tests_dir = base_dir / "tests"

        # If tests directory does not exist, return empty stats
        if not tests_dir.exists():
            logger.warning(
                f"Tests folder does not exist at {tests_dir}. Skipping execution."
            )
            return {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "duration_ms": 0,
                "success": True,
                "output": "No tests directory found.",
            }

        # Run pytest inside the target workspace
        cmd = [sys.executable, "-m", "pytest", "tests"]
        logger.info(f"Running pytest command: {' '.join(cmd)} in CWD: {base_dir}")

        try:
            result = subprocess.run(
                cmd,
                cwd=str(base_dir),
                capture_output=True,
                text=True,
                timeout=60,  # Prevent infinite hangs
            )
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode
        except subprocess.TimeoutExpired as e:
            logger.error(f"Pytest run timed out after 60s: {e}")
            err_data = (
                e.stderr.decode("utf-8")
                if isinstance(e.stderr, bytes)
                else str(e.stderr)
            )
            return {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "skipped": 0,
                "duration_ms": 60000,
                "success": False,
                "output": f"Pytest run timed out. Stderr: {err_data}",
            }
        except Exception as e:
            logger.error(f"Failed to execute pytest subprocess: {e}")
            return {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "skipped": 0,
                "duration_ms": 0,
                "success": False,
                "output": f"Subprocess launch failed: {e}",
            }

        combined_output = f"{stdout}\n{stderr}"
        stats = self._parse_output(combined_output, exit_code)
        return stats

    def _parse_output(self, output: str, exit_code: int) -> Dict[str, Any]:
        """
        Parses pytest console output to calculate statistics.
        """
        stats: Dict[str, Any] = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "duration_ms": 0,
            "success": exit_code == 0,
            "output": output,
        }

        # Look for the summary line, e.g., "=== 2 passed, 1 failed, 1 warning in 4.12s ==="
        # or "=== 1 passed in 0.05s ==="
        summary_line_match = re.search(r"===\s*([^\n]+) in \d+\.\d+s\s*===", output)
        if not summary_line_match:
            # Fallback check for smaller summary lines
            summary_line_match = re.search(r"===\s*([^\n]+)\s*===", output)

        if summary_line_match:
            summary_text = summary_line_match.group(1)

            passed_match = re.search(r"(\d+)\s+passed", summary_text)
            failed_match = re.search(r"(\d+)\s+failed", summary_text)
            errors_match = re.search(r"(\d+)\s+error", summary_text)
            skipped_match = re.search(r"(\d+)\s+skipped", summary_text)

            passed = int(passed_match.group(1)) if passed_match else 0
            failed = int(failed_match.group(1)) if failed_match else 0
            errors = int(errors_match.group(1)) if errors_match else 0
            skipped = int(skipped_match.group(1)) if skipped_match else 0

            stats["passed"] = passed
            stats["failed"] = failed
            stats["errors"] = errors
            stats["skipped"] = skipped
            stats["total"] = passed + failed + errors + skipped

        # Parse duration
        duration_match = re.search(r"in\s+(\d+\.\d+)s", output)
        if duration_match:
            stats["duration_ms"] = int(float(duration_match.group(1)) * 1000)

        # If pytest found no tests, return success status accordingly
        if "no tests ran" in output or "collected 0 items" in output:
            stats["total"] = 0
            stats["success"] = True

        return stats

"""
Coverage runner to calculate statements coverage for target workspaces.
"""

import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("ForgeAI.Plugins.Tester.Runners")


class CoverageRunner:
    """
    Runs code coverage tool inside target workspace and parses target percent metrics.
    """

    def run_coverage(self, workspace_path: str) -> float:
        """
        Runs coverage on the workspace tests suite.

        Args:
            workspace_path (str): Target workspace directory.

        Returns:
            float: Covered statements percentage (e.g. 92.5). Returns 0.0 on execution failure.
        """
        base_dir = Path(workspace_path).resolve()
        tests_dir = base_dir / "tests"

        if not tests_dir.exists():
            logger.warning(
                f"Tests folder does not exist at {tests_dir}. Coverage is 0.0."
            )
            return 0.0

        # Determine target source folder. Check for 'src' folder first, otherwise fallback to root '.'
        source_dir = "src" if (base_dir / "src").exists() else "."

        # Execute coverage run command
        run_cmd = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            f"--source={source_dir}",
            "-m",
            "pytest",
            "tests",
        ]
        logger.info(f"Running coverage command: {' '.join(run_cmd)} in CWD: {base_dir}")

        try:
            # 1. Run coverage suite
            subprocess.run(
                run_cmd,
                cwd=str(base_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )

            # 2. Compile to JSON format
            json_cmd = [
                sys.executable,
                "-m",
                "coverage",
                "json",
                "-o",
                "coverage_report.json",
            ]
            subprocess.run(
                json_cmd,
                cwd=str(base_dir),
                capture_output=True,
                text=True,
                timeout=20,
            )

            # 3. Read compiled JSON file
            report_file = base_dir / "coverage_report.json"
            if report_file.exists():
                try:
                    content = report_file.read_text(encoding="utf-8")
                    report_data = json.loads(content)
                    percent = float(
                        report_data.get("totals", {}).get("percent_covered", 0.0)
                    )
                    logger.info(f"Parsed coverage percentage: {percent}%")
                    return percent
                finally:
                    # Clean up temporary coverage files to keep the workspace clean
                    if report_file.exists():
                        report_file.unlink()
                    cov_db = base_dir / ".coverage"
                    if cov_db.exists():
                        cov_db.unlink()

            # Resilient fallback: Try parsing standard coverage report command stdout
            report_cmd = [sys.executable, "-m", "coverage", "report"]
            report_result = subprocess.run(
                report_cmd,
                cwd=str(base_dir),
                capture_output=True,
                text=True,
                timeout=20,
            )
            stdout = report_result.stdout
            logger.warning(
                f"Coverage json report was not generated. Trying report parse of stdout: {stdout}"
            )

            # Simple regex search for line like "TOTAL ... 91%"
            import re

            tot_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", stdout)
            if tot_match:
                return float(tot_match.group(1))

        except Exception as e:
            logger.error(f"Failed to run code coverage subprocess: {e}")

        # Default fallback to 0.0 if execution fails
        return 0.0

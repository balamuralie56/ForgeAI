"""
Unit tests for the centralized Version module, Kernel health reporting, and launcher --diagnostics CLI.
"""

import unittest
from unittest.mock import patch, MagicMock

from forge_core.kernel.kernel import ForgeAIKernel
from forge_core import version
from launcher import ForgeAILauncher, main


class TestHealthAndDiagnostics(unittest.TestCase):
    """Test suite verifying central version metadata, Kernel.health(), and CLI diagnostics output."""

    def test_central_version_constants(self) -> None:
        """Asserts that version.py contains title, version, author, and repository fields."""
        self.assertEqual(version.__title__, "ForgeAI")
        self.assertEqual(version.__version__, "0.4.0")
        self.assertIsNotNone(version.__author__)
        self.assertIsNotNone(version.__repository__)

    def test_kernel_health_report(self) -> None:
        """Verifies that Kernel.health() returns a structured dictionary matching expectations."""
        kernel = ForgeAIKernel(
            config_path="forge.json", defaults_path="config/defaults.json"
        )
        kernel.boot()

        try:
            report = kernel.health()

            self.assertEqual(report["version"], version.__version__)
            self.assertEqual(report["status"], "Healthy")

            services = report["services"]
            self.assertEqual(services["Configuration"], "Ready")
            self.assertEqual(services["Logging"], "Ready")
            self.assertEqual(services["Kernel"], "Ready")
            self.assertEqual(services["EventBus"], "Ready")
            self.assertEqual(services["Memory"], "Ready")
            self.assertEqual(services["TaskEngine"], "Ready")

            self.assertTrue(report["plugins_loaded"] >= 0)
            self.assertIn("ollama", report["providers"])
            self.assertEqual(report["database"], "SQLite")
            self.assertTrue(report["boot_time_ms"] >= 0)
        finally:
            kernel.shutdown()

    def test_launcher_diagnostics_only(self) -> None:
        """Tests that the --diagnostics option returns successfully and never boots the Kernel."""
        launcher = ForgeAILauncher()

        with patch.object(launcher, "boot") as mock_boot:
            with patch("sys.stdout"):
                exit_code = launcher.run_diagnostics()
                self.assertEqual(exit_code, 0)
                mock_boot.assert_not_called()

    @patch("sys.exit")
    def test_main_cli_diagnostics_dispatch(self, mock_exit: MagicMock) -> None:
        """Verifies that passing --diagnostics to sys.argv runs diagnostics and calls sys.exit."""
        mock_exit.side_effect = SystemExit
        with patch("sys.argv", ["launcher.py", "--diagnostics"]):
            with patch.object(
                ForgeAILauncher, "run_diagnostics", return_value=0
            ) as mock_diagnostics:
                with patch.object(ForgeAILauncher, "boot") as mock_boot:
                    with self.assertRaises(SystemExit):
                        main()
                    mock_diagnostics.assert_called_once()
                    mock_boot.assert_not_called()
                    mock_exit.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()

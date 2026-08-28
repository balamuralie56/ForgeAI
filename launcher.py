#!/usr/bin/env python3
"""
ForgeAI Operating System Launcher
Acts as the primary entry point, bootstrapping the configuration,
guaranteeing the filesystem environment, and initializing the logging engine.
"""

import sys
import time
from pathlib import Path
from typing import Any, List

from forge_core.configuration.exceptions import ConfigurationError
from forge_core.kernel.kernel import ForgeAIKernel
from forge_core.kernel.exceptions import KernelError
from forge_core.version import __version__


class ForgeAILauncher:
    """Manages the boot sequence and environment validation for ForgeAI."""

    def __init__(self) -> None:
        self.version: str = __version__
        self.config_manager: Any = None
        self.logging_engine: Any = None
        self.kernel: ForgeAIKernel | None = None

        # Define the strict internal directory structure required for ForgeAI to operate
        self.required_directories: List[Path] = [
            Path("forge_workspace"),
            Path("forge_data"),
            Path("forge_data/logs"),
            Path("forge_data/cache"),
            Path("forge_data/backups"),
            Path("forge_data/databases"),
            Path("forge_data/embeddings"),
        ]

    def ensure_directories(self) -> None:
        """Iterates through required paths and creates them if they do not exist."""
        for directory in self.required_directories:
            directory.mkdir(parents=True, exist_ok=True)

    def print_banner(self) -> None:
        """Outputs the formatted ForgeAI boot banner to the console."""
        kernel_status = (
            "✓ Ready" if (self.kernel and self.kernel._booted) else "Not initialized"
        )
        task_engine_status = (
            "✓ Ready"
            if (self.kernel and self.kernel.task_engine)
            else "Not initialized"
        )
        workflow_status = (
            "✓ Ready" if (self.kernel and self.kernel.workflow) else "Not initialized"
        )
        num_plugins = (
            len(self.kernel.plugin_manager.get_all_plugins())
            if self.kernel and self.kernel.plugin_manager
            else 0
        )

        health_summary = ""
        if self.kernel and self.kernel._booted:
            hr = self.kernel.health()
            health_summary = f"{hr['status']} | Boot Time: {hr['boot_time_ms']} ms"

        print("====================================================")
        print("ForgeAI Operating System")
        print(f"Version {self.version}")
        print("====================================================")
        print(f"{'Loading Configuration...':<34} ✓ Success")
        print(f"{'Loading Logger...':<34} ✓ Success")
        print(f"{'Workspace...':<34} ✓ Ready")
        print(f"{'Plugins...':<34} {num_plugins} Loaded")
        print(f"{'Kernel...':<34} {kernel_status}")
        print(f"{'Task Engine...':<34} {task_engine_status}")
        print(f"{'Workflow Engine...':<34} {workflow_status}")
        if health_summary:
            print(f"{'System Health...':<34} {health_summary}")
        print("====================================================")
        print("ForgeAI Ready")
        print("====================================================")

    def boot(self) -> int:
        """
        Executes the primary boot sequence.

        Returns:
            int: Exit code (0 for success, 1 for failure).
        """
        try:
            # 1. Guarantee filesystem state
            self.ensure_directories()

            # 2. Instantiate and boot Kernel
            self.kernel = ForgeAIKernel()
            self.kernel.boot()

            # 3. Expose backward-compatible attributes
            self.config_manager = self.kernel.config_manager  # type: ignore
            self.logging_engine = self.kernel.logging_engine

            logger = self.logging_engine.get_root_logger().get_logger("Bootstrapper")
            logger.info("ForgeAI boot sequence initiated.")

            # 4. Display Boot Banner
            self.print_banner()

            logger.info("ForgeAI boot sequence completed successfully.")
            return 0

        except (ConfigurationError, KernelError) as e:
            print(f"\n[CRITICAL FAILURE] ForgeAI Kernel Boot Error: {e}")
            return 1
        except Exception as e:
            print(f"\n[FATAL ERROR] Unexpected system failure during boot: {e}")
            return 1

    def shutdown(self) -> None:
        """Gracefully tears down the operating system, shutting down Kernel and flushing logs."""
        if self.kernel:
            self.kernel.shutdown()

    def run_diagnostics(self) -> int:
        """
        Runs read-only diagnostics on the local environment and prints a structured report.
        Never modifies any state.

        Returns:
            int: Exit code (0 for success).
        """
        import platform
        import subprocess
        import socket
        from forge_core.version import __version__, __repository__, __author__
        from forge_core.configuration.config_manager import ConfigurationManager

        print("====================================================")
        print("ForgeAI Operating System - Diagnostics Report")
        print("====================================================")

        # 1. System & Runtime Versions
        print(f"Runtime Version:                  {__version__}")
        print(f"Author:                           {__author__}")
        print(f"Repository:                       {__repository__}")
        print(f"Python Version:                   {platform.python_version()}")
        print(
            f"Operating System:                 {platform.system()} {platform.release()} ({platform.machine()})"
        )

        # 2. Git Version
        git_version = "Not installed or not in PATH"
        try:
            res = subprocess.run(
                ["git", "--version"], capture_output=True, text=True, check=True
            )
            git_version = res.stdout.strip()
        except Exception:
            pass
        print(f"Git Version:                      {git_version}")

        # 3. Read configuration in read-only mode
        config_path = "forge.json"
        defaults_path = "config/defaults.json"
        print(f"Configuration Path:               {config_path}")
        print(f"Defaults Path:                    {defaults_path}")

        try:
            config_manager = ConfigurationManager(
                config_path=config_path, defaults_path=defaults_path
            )
            sys_settings = config_manager.get_system_settings()
            model_settings = config_manager.get_model_settings()
            plugin_settings = config_manager.get_plugin_settings()

            workspace_dir = sys_settings.workspace_dir
            log_dir = sys_settings.log_dir
            model_provider = model_settings.provider
            enabled_plugins = plugin_settings.enabled_plugins
        except Exception as e:
            workspace_dir = "forge_workspace (failed to load config)"
            log_dir = "forge_data/logs (failed to load config)"
            model_provider = "ollama (failed to load config)"
            enabled_plugins = []
            print(f"[Warning] Failed to load configuration: {e}")

        print(f"Workspace Directory:              {workspace_dir}")
        print(f"Log Directory:                    {log_dir}")

        # 4. Ollama Status
        ollama_status = "Offline"
        try:
            # Quick TCP connection check on localhost:11434
            with socket.create_connection(("localhost", 11434), timeout=1.0):
                ollama_status = "Online (Listening on port 11434)"
        except Exception:
            pass
        print(f"Ollama Status:                    {ollama_status}")

        # 5. Database Status
        db_path = Path("forge_data/databases/project_memory.db")
        if db_path.exists():
            db_status = f"Exists ({db_path.stat().st_size} bytes)"
        else:
            db_status = "Does not exist (Will be created on boot)"
        print(f"Database Path:                    {db_path}")
        print(f"Database Status:                  {db_status}")
        print("Memory Provider:                  SQLite (Local Persistent)")

        # 6. Service Registry Catalog
        print("\nRegistered Services Catalog (Mapped on Boot):")
        print(" - ConfigurationService           -> ConfigurationManager")
        print(" - LoggingService                 -> QueueListenerLogger")
        print(" - ModelRouterService             -> ModelRouter")
        print(" - PluginManagerService           -> PluginManager")
        print(" - EventBusService                -> ForgeAIEventBus")
        print(" - MemoryService                  -> ForgeAIMemoryService")
        print(" - TaskEngineService              -> ForgeAITaskEngine")
        print(" - WorkflowService                -> ForgeAIWorkflowService")

        # 7. Registered Model Providers
        print(f"\nRegistered Model Providers:       {model_provider} (Active default)")

        # 8. Registered Plugins
        print(
            f"Configured Enabled Plugins:       {', '.join(enabled_plugins) if enabled_plugins else 'None'}"
        )

        print("====================================================")
        return 0


def main() -> None:
    """System entry execution."""

    launcher = ForgeAILauncher()

    if "--diagnostics" in sys.argv:
        exit_code = launcher.run_diagnostics()
        sys.exit(exit_code)

    exit_code = launcher.boot()

    try:
        if exit_code == 0:
            # Simulation of an active runtime loop before Sprint 2 architecture
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nInitiating graceful shutdown...")
    finally:
        launcher.shutdown()
        sys.exit(exit_code)


if __name__ == "__main__":
    main()

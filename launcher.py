#!/usr/bin/env python3
"""
ForgeAI Operating System Launcher
Acts as the primary entry point, bootstrapping the configuration,
guaranteeing the filesystem environment, and initializing the logging engine.
"""
import sys
import time
from pathlib import Path
from typing import List

from forge_core.configuration.exceptions import ConfigurationError
from forge_core.configuration.service import ConfigurationService
from forge_core.kernel.kernel import ForgeAIKernel
from forge_core.kernel.exceptions import KernelError


class ForgeAILauncher:
    """Manages the boot sequence and environment validation for ForgeAI."""

    def __init__(self) -> None:
        self.version: str = "0.1"
        self.config_manager = None
        self.logging_engine = None
        self.kernel: ForgeAIKernel | None = None

        # Define the strict internal directory structure required for ForgeAI to operate
        self.required_directories: List[Path] = [
            Path("forge_workspace"),
            Path("forge_data"),
            Path("forge_data/logs"),
            Path("forge_data/cache"),
            Path("forge_data/backups"),
            Path("forge_data/databases"),
            Path("forge_data/embeddings")
        ]

    def ensure_directories(self) -> None:
        """Iterates through required paths and creates them if they do not exist."""
        for directory in self.required_directories:
            directory.mkdir(parents=True, exist_ok=True)

    def print_banner(self) -> None:
        """Outputs the formatted ForgeAI boot banner to the console."""
        kernel_status = "✓ Ready" if (self.kernel and self.kernel._booted) else "Not initialized"
        num_plugins = len(self.kernel.plugin_manager.get_all_plugins()) if self.kernel and self.kernel.plugin_manager else 0

        print("====================================================")
        print("ForgeAI Operating System")
        print(f"Version {self.version}")
        print("====================================================")
        print(f"{'Loading Configuration...':<34} ✓ Success")
        print(f"{'Loading Logger...':<34} ✓ Success")
        print(f"{'Workspace...':<34} ✓ Ready")
        print(f"{'Plugins...':<34} {num_plugins} Loaded")
        print(f"{'Kernel...':<34} {kernel_status}")
        print(f"{'Task Engine...':<34} Not initialized")
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


def main() -> None:
    """System entry execution."""
    launcher = ForgeAILauncher()
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
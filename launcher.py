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

from forge_core.configuration.config_manager import ConfigurationManager
from forge_core.configuration.exceptions import ConfigurationError
from forge_core.logging.engine import LoggingEngine


class ForgeAILauncher:
    """Manages the boot sequence and environment validation for ForgeAI."""

    def __init__(self) -> None:
        self.version: str = "0.1"
        self.config_manager: ConfigurationManager | None = None
        self.logging_engine: LoggingEngine | None = None

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
        print("====================================================")
        print("ForgeAI Operating System")
        print(f"Version {self.version}")
        print("====================================================")
        print(f"{'Loading Configuration...':<30} ✓ Success")
        print(f"{'Loading Logger...':<30} ✓ Success")
        print(f"{'Workspace...':<30} ✓ Ready")
        print(f"{'Plugins...':<30} 0 Loaded")
        print(f"{'Kernel...':<30} Not initialized")
        print(f"{'Task Engine...':<30} Not initialized")
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

            # 2. Initialize Configuration
            self.config_manager = ConfigurationManager()

            # 3. Initialize Logging Engine
            self.logging_engine = LoggingEngine(self.config_manager)
            logger = self.logging_engine.get_root_logger().get_logger("Bootstrapper")
            logger.info("ForgeAI boot sequence initiated.")

            # 4. Display Boot Banner
            self.print_banner()
            
            logger.info("ForgeAI boot sequence completed successfully.")
            return 0

        except ConfigurationError as e:
            print(f"\n[CRITICAL FAILURE] ForgeAI Configuration Error: {e}")
            return 1
        except Exception as e:
            print(f"\n[FATAL ERROR] Unexpected system failure during boot: {e}")
            return 1

    def shutdown(self) -> None:
        """Gracefully tears down the operating system, flushing logs."""
        if self.logging_engine:
            self.logging_engine.shutdown()


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
"""
Process-wide Kernel singleton for the ForgeAI Web API.
The Kernel boots once when the API server starts and is shared across requests.
"""

import logging
from typing import Optional
from forge_core.kernel.kernel import ForgeAIKernel

logger = logging.getLogger("ForgeAI.API.Bootstrap")

_kernel: Optional[ForgeAIKernel] = None


def get_kernel() -> ForgeAIKernel:
    """Returns the booted process-wide Kernel, booting it on first access."""
    global _kernel
    if _kernel is None:
        _kernel = ForgeAIKernel(
            config_path="forge.json", defaults_path="config/defaults.json"
        )
        _kernel.boot()
        logger.info("Kernel booted for ForgeAI Web API.")
    return _kernel


def shutdown_kernel() -> None:
    """Shuts down the process-wide Kernel, if booted."""
    global _kernel
    if _kernel is not None:
        _kernel.shutdown()
        _kernel = None

"""
Exception classes for the ForgeAI Kernel and Service Registry.
"""


class KernelError(Exception):
    """Base exception for all errors raised by the ForgeAI Kernel."""

    pass


class ServiceNotFoundError(KernelError):
    """Raised when a requested service is not registered in the Service Registry."""

    pass

"""
Service registry interface for the Task Engine.
Allows registration and resolution within the Kernel.
"""

from .interface import TaskEngine


class TaskEngineService(TaskEngine):
    """
    Service interface representing the Task Engine.
    Plugins and services should resolve this service type from the registry.
    """

    pass

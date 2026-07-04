from dataclasses import dataclass


@dataclass
class ForgeSettings:

    app_name: str

    version: str

    debug: bool

    default_model: str

    workspace: str
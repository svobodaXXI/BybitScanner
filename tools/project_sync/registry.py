"""
registry.py

Project Sync Framework

Version:
0.2.0

Component:
Registry Model

Responsibility:

Stores project registry structures.

This module does NOT:

- scan filesystem;
- analyze architecture;
- update documentation;
- detect changes.

It only defines registry data models.
"""


from dataclasses import dataclass, field
from typing import List



@dataclass
class ModuleRegistryEntry:
    """
    Single module registry record.
    """

    name: str

    path: str

    module_type: str = ""

    layer: str = ""

    responsibility: str = ""

    status: str = "unknown"



@dataclass
class ModuleRegistry:
    """
    Collection of project modules.
    """

    modules: List[ModuleRegistryEntry] = field(
        default_factory=list
    )


    def add(
        self,
        module: ModuleRegistryEntry
    ):
        """
        Add module entry.
        """

        self.modules.append(
            module
        )


    def count(self) -> int:
        """
        Return number of registered modules.
        """

        return len(
            self.modules
        )
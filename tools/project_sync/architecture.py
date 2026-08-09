"""
architecture.py

Project Sync Framework

Version:
0.3.0

Component:
Architecture Model

Responsibility:

Defines architecture data structures.

This module does NOT:

- analyze modules;
- assign layers;
- modify documentation;
- detect dependencies.

It only stores architecture information.
"""


from dataclasses import dataclass, field
from typing import List



@dataclass
class ArchitectureComponent:
    """
    Single architecture component.
    """

    name: str

    path: str = ""

    layer: str = ""

    responsibility: str = ""

    component_type: str = ""

    status: str = "unknown"

    dependencies: List[str] = field(
        default_factory=list
    )



@dataclass
class ArchitectureRegistry:
    """
    Collection of architecture components.
    """

    components: List[ArchitectureComponent] = field(
        default_factory=list
    )


    def add(
        self,
        component: ArchitectureComponent
    ):
        """
        Add architecture component.
        """

        self.components.append(
            component
        )


    def count(self) -> int:
        """
        Return number of components.
        """

        return len(
            self.components
        )
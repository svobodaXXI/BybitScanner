"""
Architecture Registry

Stores architecture components,
layers and dependency information.

Part of:
Project Sync Framework
Architecture Intelligence Layer
"""


from typing import Any


class ArchitectureRegistry:
    """
    Registry of project architecture components.
    """


    def __init__(self):
        self.components: list[dict[str, Any]] = []


    def register(
        self,
        component: dict[str, Any],
    ) -> None:
        """
        Register architecture component.
        """

        self.components.append(component)


    def get_components(
        self,
    ) -> list[dict[str, Any]]:
        """
        Return registered architecture components.
        """

        return self.components


    def find_by_layer(
        self,
        layer: str,
    ) -> list[dict[str, Any]]:
        """
        Return components by architecture layer.
        """

        return [
            component
            for component in self.components
            if component.get("layer") == layer
        ]


    def get_metadata(
        self,
    ) -> list[dict[str, Any]]:
        """
        Return registry metadata.
        """

        return [
            {
                "name": component.get("name"),
                "layer": component.get("layer"),
                "responsibility": component.get(
                    "responsibility"
                ),
            }
            for component in self.components
        ]
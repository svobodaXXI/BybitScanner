"""
registry_builder.py

Project Sync Framework

Version:
0.2.1

Component:
Registry Builder

Responsibility:

Build module registry from ProjectModel.

This module does NOT:

- analyze architecture;
- assign layers;
- update documentation;
- detect changes.

It only creates registry entries.
"""


from pathlib import Path

from .registry import (
    ModuleRegistry,
    ModuleRegistryEntry,
)



class RegistryBuilder:
    """
    Creates registry from project model.
    """


    def build(
        self,
        project_model
    ) -> ModuleRegistry:
        """
        Build module registry.
        """

        registry = ModuleRegistry()


        for file in project_model.files:

            path = Path(
                file.path
            )


            if path.suffix == ".py":

                entry = ModuleRegistryEntry(

                    name=path.stem,

                    path=str(path),

                    module_type="python_module",

                    status="active"
                )


                registry.add(
                    entry
                )


        return registry
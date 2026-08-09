"""
registry_report.py

Project Sync Framework

Version:
0.2.2

Component:
Registry Report Engine

Responsibility:

Serialize registry data into JSON artifact.

This module does NOT:

- analyze architecture;
- classify modules;
- update documentation;
- detect changes.
"""


import json
from pathlib import Path



class RegistryReport:
    """
    Saves registry information.
    """


    def __init__(
        self,
        output_path: str
    ):
        self.output_path = Path(
            output_path
        )


    def save(
        self,
        registry
    ):
        """
        Save registry as JSON.
        """

        data = {

            "registry_type":
                "MODULE_REGISTRY",

            "version":
                "0.2.2",

            "modules":
                [

                    {

                        "name": module.name,

                        "path": module.path,

                        "module_type":
                            module.module_type,

                        "layer":
                            module.layer,

                        "responsibility":
                            module.responsibility,

                        "status":
                            module.status

                    }

                    for module in registry.modules

                ]

        }


        self.output_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )


        with self.output_path.open(
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False
            )
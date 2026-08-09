"""
architecture_report.py

Project Sync Framework

Version:
0.3.3

Component:
Architecture Report

Responsibility:

Serialize Architecture Registry
into JSON artifact.

This module does NOT:

- analyze modules;
- classify components;
- modify documentation.

It only saves reports.
"""


import json
from pathlib import Path


class ArchitectureReport:
    """
    Creates architecture JSON report.
    """


    def __init__(self, output_path):
        self.output_path = Path(output_path)


    def save(
        self,
        registry
    ):
        """
        Save architecture registry.
        """

        data = {
            "components": []
        }


        for component in registry.components:

            data["components"].append(
                {
                    "name": component.name,
                    "path": component.path,
                    "layer": component.layer,
                    "responsibility": component.responsibility,
                    "component_type": component.component_type,
                    "status": component.status,
                    "dependencies": component.dependencies,
                }
            )


        self.output_path.write_text(
            json.dumps(
                data,
                indent=4,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )
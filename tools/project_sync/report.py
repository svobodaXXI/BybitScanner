"""
report.py

Project Sync Framework

Version:
0.1.1

Responsibility:
Create scan report artifacts.

This module only saves scan results.
No scanning.
No validation.
No synchronization.
"""


import json
from datetime import datetime
from pathlib import Path


class ScanReport:

    """
    Creates JSON report from ProjectModel.
    """


    def __init__(
        self,
        output_path: str
    ):

        self.output_path = Path(output_path)



    def save(
        self,
        model,
        version="0.1.1"
    ):
        """
        Save project scan result.
        """

        report = {

            "project":
                model.root_path,

            "directories":
                len(model.directories),

            "files":
                len(model.files),

            "timestamp":
                datetime.now().isoformat(),

            "version":
                version
        }


        self.output_path.parent.mkdir(
            exist_ok=True
        )


        with open(
            self.output_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                report,
                file,
                indent=4,
                ensure_ascii=False
            )
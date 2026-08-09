"""
validation_report.py

Project Sync Framework

Version:
0.4.3

Component:
Architecture Validation Report

Responsibility:

Stores architecture validation results.

This module does NOT:

- execute validation;
- analyze modules;
- modify project files.
"""


import json
from pathlib import Path
from datetime import datetime



class ValidationReport:
    """
    Saves validation results.
    """


    def __init__(
        self,
        path
    ):

        self.path = Path(path)



    def save(
        self,
        result,
        version="0.4.3"
    ):
        """
        Save validation result.
        """


        data = {

            "framework":

                "BybitScanner Project Sync Framework",


            "version":

                version,


            "component":

                "Architecture Validation Report",


            "timestamp":

                datetime.utcnow().isoformat(),


            "status":

                result.status(),


            "issues":

                [
                    issue.to_dict()
                    for issue in result.issues
                ]

        }


        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )


        with open(
            self.path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False
            )
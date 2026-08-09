"""
scanner.py

Project Sync Framework

Version:
0.1

Responsibility:
Filesystem scanner.

This module scans the project directory
and builds ProjectModel.

No documentation updates.
No synchronization logic.
No validation.
"""


from pathlib import Path

from .model import (
    ProjectModel,
    DirectoryInfo,
    FileInfo,
)



class ProjectScanner:
    """
    Scans project filesystem
    and creates ProjectModel.
    """


    def __init__(
        self,
        root_path: str
    ):
        self.root_path = Path(root_path)


    def scan(self) -> ProjectModel:
        """
        Execute project scan.

        Returns:
            ProjectModel
        """

        model = ProjectModel(
            root_path=str(self.root_path)
        )


        for path in self.root_path.rglob("*"):

            if path.is_dir():

                model.add_directory(
                    DirectoryInfo(
                        path=str(path),
                        name=path.name,
                    )
                )


            elif path.is_file():

                model.add_file(
                    FileInfo(
                        path=str(path),
                        name=path.name,
                        extension=path.suffix,
                        size=path.stat().st_size,
                    )
                )


        return model
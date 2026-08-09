"""
model.py

Project Sync Framework

Version:
0.1

Responsibility:
Internal project state models.

This module contains only data structures.
No filesystem operations.
No synchronization logic.
"""


from dataclasses import dataclass, field
from pathlib import Path
from typing import List



@dataclass
class FileInfo:
    """
    Information about one project file.
    """

    path: str
    name: str
    extension: str
    size: int


@dataclass
class DirectoryInfo:
    """
    Information about one project directory.
    """

    path: str
    name: str


@dataclass
class ProjectModel:
    """
    Internal representation of project state.

    This model will become the foundation
    for future:

    - PROJECT_TREE generation
    - MODULE_REGISTRY generation
    - validation
    - synchronization
    """

    root_path: str

    directories: List[DirectoryInfo] = field(
        default_factory=list
    )

    files: List[FileInfo] = field(
        default_factory=list
    )


    def add_directory(
        self,
        directory: DirectoryInfo
    ):
        """
        Add directory information.
        """

        self.directories.append(directory)


    def add_file(
        self,
        file: FileInfo
    ):
        """
        Add file information.
        """

        self.files.append(file)



    def summary(self) -> dict:
        """
        Return short project statistics.
        """

        return {
            "root": self.root_path,
            "directories": len(self.directories),
            "files": len(self.files),
        }
"""
BybitScanner Project Sync Framework

Document Model

Responsibility:
    Data model for project documents.

This module does not scan files
and does not perform analysis.

It only describes a document entity
used by Project Sync components.
"""


from dataclasses import dataclass, field
from typing import List


@dataclass
class DocumentModel:
    """
    Represents one project document.
    """

    name: str

    document_id: str = ""

    document_type: str = ""

    document_class: str = ""

    validation_level: str = ""

    version: str = ""

    status: str = ""

    purpose: str = ""

    responsibility: str = ""

    location: str = ""

    dependencies: List[str] = field(default_factory=list)

    dependents: List[str] = field(default_factory=list)

    last_update: str = ""


    def to_dict(self) -> dict:
        """
        Convert document model to JSON-compatible structure.
        """

        return {
            "name": self.name,

            "document_id": self.document_id,

            "document_type": self.document_type,

            "document_class": self.document_class,

            "validation_level": self.validation_level,

            "version": self.version,

            "status": self.status,

            "purpose": self.purpose,

            "responsibility": self.responsibility,

            "location": self.location,

            "dependencies": self.dependencies,

            "dependents": self.dependents,

            "last_update": self.last_update,
        }
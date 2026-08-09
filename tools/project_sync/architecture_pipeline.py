"""
architecture_pipeline.py

Project Sync Framework

Version:
0.3.4

Component:
Architecture Pipeline

Responsibility:

Connects module registry
with architecture analysis pipeline.
"""


from pathlib import Path

from .architecture_analyzer import (
    ArchitectureAnalyzer,
)

from .architecture_report import (
    ArchitectureReport,
)



class ArchitecturePipeline:
    """
    Executes architecture analysis workflow.
    """


    def __init__(
        self,
        output_path
    ):

        self.analyzer = ArchitectureAnalyzer()

        self.report = ArchitectureReport(
            output_path
        )


    def run(
        self,
        module_registry
    ):
        """
        Execute full architecture pipeline.
        """

        architecture_registry = (
            self.analyzer.analyze(
                module_registry
            )
        )


        self.report.save(
            architecture_registry
        )


        return architecture_registry
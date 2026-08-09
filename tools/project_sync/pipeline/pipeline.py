"""
Project Sync Pipeline

Main execution facade of the Project Sync Framework.

Coordinates:

Architecture Validation

and

Pipeline Execution

through unified Pipeline Engine.
"""


from typing import Any


from ..registry.architecture.architecture_registry import (
    ArchitectureRegistry,
)

from ..rules.rule_loader import (
    RuleLoader,
)

from ..rules.rule_registry import (
    RuleRegistry,
)

from ..validation.architecture_compliance_engine import (
    ArchitectureComplianceEngine,
)


from .context import PipelineContext

from .executor import PipelineExecutor

from .registry import PipelineRegistry

from .result import PipelineResult



class ProjectSyncPipeline:
    """
    Main Project Sync execution facade.

    Responsible for:

    - architecture validation;
    - pipeline initialization;
    - unified stage execution;
    - result collection.
    """


    def __init__(self):

        self.rule_registry = RuleRegistry()

        RuleLoader(
            self.rule_registry,
        ).load()


        self.architecture_engine = (
            ArchitectureComplianceEngine(
                self.rule_registry,
            )
        )


        self.pipeline_registry = PipelineRegistry()

        self.pipeline_registry.register_default_stages()



    def build_architecture_registry(
        self,
        components: list[dict[str, Any]],
    ) -> ArchitectureRegistry:
        """
        Convert raw architecture data
        into ArchitectureRegistry object.
        """

        registry = ArchitectureRegistry()


        for component in components:

            registry.register(
                component,
            )


        return registry



    def build_executor(self):

        stages = []

        for stage_name in (
            self.pipeline_registry.list_stages()
        ):

            stage = (
                self.pipeline_registry.create(
                    stage_name
                )
            )

            if stage:

                stages.append(
                    stage
                )


        return PipelineExecutor(
            stages
        )



    def execute(
        self,
        architecture_components: list[dict[str, Any]],
        context_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute complete Project Sync pipeline.
        """


        architecture_registry = (
            self.build_architecture_registry(
                architecture_components,
            )
        )


        architecture_validation = (
            self.architecture_engine.validate(
                architecture_registry,
                context_data,
            )
        )


        context = PipelineContext(
            project_path=context_data.get(
                "project_path",
                "",
            )
        )


        context.metadata.update(
            context_data
        )


        executor = (
            self.build_executor()
        )


        pipeline_results = (
            executor.execute(
                context
            )
        )


        return {

            "architecture_validation":
                architecture_validation,


            "registry":
                architecture_registry.get_metadata(),


            "pipeline_results":
                [

                    result.to_dict()

                    if isinstance(
                        result,
                        PipelineResult,
                    )

                    else result

                    for result in pipeline_results

                ],


            "context":

                context.to_dict(),

        }
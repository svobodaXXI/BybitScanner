"""
Project Sync Framework

Pipeline Registry

Single Source Of Truth for Project Sync
Pipeline stage registration and creation.

Responsibility:
    Define the canonical operational Pipeline composition.

The Registry:
    - registers canonical PipelineStage implementations;
    - adapts existing Project Sync modules through Stage Adapter;
    - preserves one deterministic stage order;
    - creates stage instances for PipelineExecutor;
    - exposes machine-readable registry state.

It does not:
    - execute stages;
    - perform orchestration;
    - implement business logic;
    - approve migration;
    - modify documents directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Type

from .stage import PipelineStage
from .stage_adapter import create_module_stage


PROJECT_ROOT = Path(
    "C:/BybitScanner"
)


class PipelineRegistry:
    """
    Canonical registry of PipelineStage classes.

    PipelineRegistry is the Single Source Of Truth
    for operational Pipeline composition.
    """

    def __init__(self):

        self._stages: dict[
            str,
            Type[PipelineStage]
        ] = {}

    def register(
        self,
        stage_class: Type[PipelineStage],
    ) -> str:
        """
        Register a PipelineStage class.
        """

        if not isinstance(
            stage_class,
            type,
        ):

            raise TypeError(
                "Pipeline stage must be a class."
            )

        if not issubclass(
            stage_class,
            PipelineStage,
        ):

            raise TypeError(
                "Registered stage must inherit "
                "from PipelineStage."
            )

        stage = stage_class()

        name = stage.name

        if not name:

            raise ValueError(
                f"{stage_class.__name__} must define "
                "a valid stage name."
            )

        if name in self._stages:

            raise ValueError(
                f"Pipeline stage '{name}' "
                "is already registered."
            )

        self._stages[name] = stage_class

        return name

    def register_default_stages(self):
        """
        Register the canonical operational Pipeline.

        Registration order is the execution order.

        The canonical operational Pipeline contains:

            document_registry
                в†“
            validation
                в†“
            dependency_analysis
                в†“
            impact_analysis
                в†“
            snapshot_compare
                в†“
            health_check
                в†“
            synchronization_planning
                в†“
            state_intelligence
                в†“
            state_synchronization_planning
                в†“
            state_synchronization
                в†“
            migration
                в†“
            post_migration_validation
        """

        self.clear()

        document_registry_stage = (
            create_module_stage(
                name="document_registry",
                module=(
                    "tools.project_sync.registry."
                    "document_registry"
                ),
                description=(
                    "Register project documents "
                    "and build canonical document registry."
                ),
            )
        )

        validation_stage = (
            create_module_stage(
                name="validation",
                module=(
                    "tools.project_sync.validation."
                    "document_validator"
                ),
                description=(
                    "Validate registered project "
                    "documents."
                ),
            )
        )

        dependency_analysis_stage = (
            create_module_stage(
                name="dependency_analysis",
                module=(
                    "tools.project_sync.analysis."
                    "dependency_analyzer"
                ),
                description=(
                    "Analyze document dependencies."
                ),
            )
        )

        impact_analysis_stage = (
            create_module_stage(
                name="impact_analysis",
                module=(
                    "tools.project_sync.analysis."
                    "impact_analyzer"
                ),
                description=(
                    "Analyze project impact."
                ),
            )
        )

        snapshot_compare_stage = (
            create_module_stage(
                name="snapshot_compare",
                module=(
                    "tools.project_sync.change_detection."
                    "snapshot_compare"
                ),
                description=(
                    "Compare current project state "
                    "with the previous snapshot."
                ),
            )
        )

        health_check_stage = (
            create_module_stage(
                name="health_check",
                module=(
                    "tools.project_sync.health."
                    "project_health_report"
                ),
                description=(
                    "Evaluate Project Sync health."
                ),
            )
        )

        synchronization_planning_stage = (
            create_module_stage(
                name="synchronization_planning",
                module=(
                    "tools.project_sync.synchronization."
                    "sync_planner"
                ),
                description=(
                    "Create controlled synchronization plan."
                ),
            )
        )

        state_intelligence_stage = (
            create_module_stage(
                name="state_intelligence",
                module=(
                    "tools.project_sync.state."
                    "state_analyzer"
                ),
                description=(
                    "Analyze Project Sync state package."
                ),
            )
        )

        state_synchronization_planning_stage = (
            create_module_stage(
                name="state_synchronization_planning",
                module=(
                    "tools.project_sync.state."
                    "state_synchronization_planner"
                ),
                description=(
                    "Determine whether state "
                    "synchronization is required."
                ),
            )
        )

        state_synchronization_stage = (
            create_module_stage(
                name="state_synchronization",
                module=(
                    "tools.project_sync.state."
                    "state_synchronizer"
                ),
                description=(
                    "Execute controlled state "
                    "synchronization."
                ),
            )
        )

        from .migration_stage import (
            MigrationStage,
        )

        from .post_migration_validation_stage import (
            PostMigrationValidationStage,
        )

        stages = [

            document_registry_stage,

            validation_stage,

            dependency_analysis_stage,

            impact_analysis_stage,

            snapshot_compare_stage,

            health_check_stage,

            synchronization_planning_stage,

            state_intelligence_stage,

            state_synchronization_planning_stage,

            state_synchronization_stage,

            MigrationStage,

            PostMigrationValidationStage,

        ]

        for stage_class in stages:

            self.register(
                stage_class
            )

    def get(
        self,
        name: str,
    ) -> Type[PipelineStage] | None:
        """
        Return a registered stage class.
        """

        return self._stages.get(
            name
        )

    def create(
        self,
        name: str,
    ) -> PipelineStage | None:
        """
        Create a registered stage instance.
        """

        stage_class = self.get(
            name
        )

        if stage_class is None:

            return None

        return stage_class()

    def list_stages(
        self,
    ) -> list[str]:
        """
        Return registered stage names
        in canonical execution order.
        """

        return list(
            self._stages.keys()
        )

    def count(
        self,
    ) -> int:
        """
        Return the number of registered stages.
        """

        return len(
            self._stages
        )

    def contains(
        self,
        name: str,
    ) -> bool:
        """
        Check whether a stage is registered.
        """

        return name in self._stages

    def unregister(
        self,
        name: str,
    ) -> bool:
        """
        Remove a stage from the registry.
        """

        if name not in self._stages:

            return False

        del self._stages[
            name
        ]

        return True

    def clear(
        self,
    ):
        """
        Remove all registered stages.
        """

        self._stages.clear()

    def to_dict(
        self,
    ) -> dict:
        """
        Convert registry state to a
        machine-readable representation.
        """

        stages = []

        for name in self.list_stages():

            stage_class = self.get(
                name
            )

            stage = (
                stage_class()
                if stage_class is not None
                else None
            )

            stages.append(
                {
                    "name":
                        name,

                    "class": (
                        (
                            f"{stage_class.__module__}."
                            f"{stage_class.__name__}"
                        )
                        if stage_class is not None
                        else None
                    ),

                    "definition": (
                        stage.to_dict()
                        if stage is not None
                        else {}
                    ),
                }
            )

        return {

            "stage_count":
                self.count(),

            "single_source_of_truth":
                True,

            "stages":
                stages,
        }

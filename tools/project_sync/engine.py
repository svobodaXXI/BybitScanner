"""
engine.py

Project Sync Framework

Version:
0.4.4

Component:
Sync Engine

Responsibility:

Orchestrates Project Sync pipeline.


Pipeline:

Filesystem

↓

Scanner

↓

ProjectModel

↓

ScanReport

↓

RegistryBuilder

↓

RegistryReport

↓

ArchitecturePipeline

↓

ArchitectureReport

↓

DefaultRules

↓

ArchitectureValidator

↓

ValidationReport



This module does NOT:

- analyze architecture;
- classify modules;
- execute validation rules;
- modify documentation.
"""


from pathlib import Path


from .scanner import ProjectScanner
from .report import ScanReport


from .registry_builder import RegistryBuilder
from .registry_report import RegistryReport


from .architecture_pipeline import ArchitecturePipeline


from .default_rules import create_default_rules

from .validator import ArchitectureValidator

from .validation_report import ValidationReport



VERSION = "0.4.4"



def print_header():

    print("=" * 60)
    print("BybitScanner Project Sync Framework")
    print("=" * 60)
    print(f"Version: {VERSION}")
    print("Component: Sync Engine")
    print("=" * 60)
    print()



def run():

    project_root = Path.cwd()



    scanner = ProjectScanner(
        str(project_root)
    )


    model = scanner.scan()



    scan_report = ScanReport(
        "tools/project_sync/reports/scan_report.json"
    )


    scan_report.save(
        model,
        version=VERSION
    )



    registry_builder = RegistryBuilder()


    registry = registry_builder.build(
        model
    )



    registry_report = RegistryReport(
        "tools/project_sync/reports/module_registry.json"
    )


    registry_report.save(
        registry
    )



    architecture_pipeline = ArchitecturePipeline(
        "tools/project_sync/reports/architecture_registry.json"
    )


    architecture_registry = architecture_pipeline.run(
        registry
    )



    rules = create_default_rules()



    validator = ArchitectureValidator(
        rules
    )



    validation_result = validator.validate(
        architecture_registry
    )



    validation_report = ValidationReport(
        "tools/project_sync/reports/validation_report.json"
    )


    validation_report.save(
        validation_result,
        version=VERSION
    )



    print_header()



    print("Project:")
    print(model.root_path)
    print()



    summary = model.summary()



    print("Directories found:")
    print(summary["directories"])
    print()



    print("Files found:")
    print(summary["files"])
    print()



    print("Registered modules:")
    print(registry.count())
    print()



    print("Architecture components:")
    print(architecture_registry.count())
    print()



    print("Validation rules:")
    print(rules.count())
    print()



    print("Validation issues:")
    print(validation_result.count())
    print()



    print("Artifacts saved:")


    print(
        "tools/project_sync/reports/scan_report.json"
    )


    print(
        "tools/project_sync/reports/module_registry.json"
    )


    print(
        "tools/project_sync/reports/architecture_registry.json"
    )


    print(
        "tools/project_sync/reports/validation_report.json"
    )



if __name__ == "__main__":

    run()
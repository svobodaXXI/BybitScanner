"""
Project Sync Framework

Pipeline Tests

Basic validation of pipeline components.
"""


from .context import PipelineContext
from .result import PipelineResult
from .stage import PipelineStage
from .executor import PipelineExecutor



def test_context_creation():

    context = PipelineContext(
        project_path="C:/BybitScanner"
    )

    assert context.project_path == "C:/BybitScanner"



def test_result_success():

    result = PipelineResult.success_result(
        stage="test",
        data={"status": "ok"},
    )

    assert result.success is True



def test_stage_execution():

    def handler(context):
        return "stage_ok"


    stage = PipelineStage(
        name="test_stage",
        handler=handler,
    )

    context = PipelineContext(
        project_path="C:/BybitScanner"
    )

    result = stage.execute(
        context
    )

    assert result == "stage_ok"



def test_executor():

    def handler(context):
        return "executed"


    stage = PipelineStage(
        name="executor_stage",
        handler=handler,
    )


    executor = PipelineExecutor(
        [
            stage
        ]
    )


    context = PipelineContext(
        project_path="C:/BybitScanner"
    )


    results = executor.execute(
        context
    )


    assert len(results) == 1
    assert results[0].success is True

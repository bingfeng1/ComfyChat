from sqlalchemy import func, select

from app.models.generation import Generation, WorkflowGenerationConfig


def test_tables_created(engine):
    assert engine.dialect.has_table(engine.connect(), "generations")
    assert engine.dialect.has_table(engine.connect(), "workflow_generation_configs")


def test_generation_insert_and_read(session):
    gen = Generation(
        workflow_id="wf1",
        workflow_name="z-image",
        parameters_json='{"positive_prompt": "cat"}',
        status="queued",
        prompt_id="p1",
    )
    session.add(gen)
    session.commit()
    got = session.scalar(select(Generation).where(Generation.id == gen.id))
    assert got.status == "queued"
    assert got.workflow_name == "z-image"


def test_config_unique_per_workflow(session):
    session.add(WorkflowGenerationConfig(
        workflow_id="wf1", api_template="{}", fields_json="[]",
    ))
    session.commit()
    import pytest
    from sqlalchemy.exc import IntegrityError
    session.add(WorkflowGenerationConfig(
        workflow_id="wf1", api_template="{}", fields_json="[]",
    ))
    with pytest.raises(IntegrityError):
        session.commit()

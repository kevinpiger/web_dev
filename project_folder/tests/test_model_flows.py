import uuid

import pytest
from pydantic import ValidationError

from app.schemas.model_flow import ModelFlowCreate


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_rejects_invalid_names(name):
    with pytest.raises(ValidationError):
        ModelFlowCreate(name=name)


def test_create_defaults_and_trims_name():
    body = ModelFlowCreate(name="  Default flow  ")
    assert body.name == "Default flow"
    assert body.is_valid is True
    assert body.description is None


def test_rejects_client_managed_id():
    with pytest.raises(ValidationError):
        ModelFlowCreate(name="Flow", id=str(uuid.uuid4()))

"""Shapes of the JSON the API sends and receives, from docs/api-contract.md.

Input rules ("Conventions"): whole numbers must be JSON integers, unknown
fields are rejected, and text is trimmed before any other rule is applied.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.domain import MAX_DISCOUNT_BPS
from app.models import Outcome, Status

Text = Annotated[str, Field(min_length=1, max_length=1000)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateRequestInput(Input):
    application_id: str
    discount_bps: Annotated[StrictInt, Field(ge=1, le=MAX_DISCOUNT_BPS)]
    reason: Text


class DecisionInput(Input):
    expected_version: Annotated[StrictInt, Field(ge=1)]
    outcome: Outcome
    comment: Text


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DecisionOutput(Output):
    outcome: Outcome
    decided_by: str
    decided_at: datetime
    comment: str


class RevisionOutput(Output):
    number: int
    discount_bps: int
    reason: str
    created_at: datetime
    decision: DecisionOutput | None


class RequestDetail(Output):
    id: str
    application_id: str
    status: Status
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    revisions: list[RevisionOutput]


class ApprovedDiscount(BaseModel):
    application_id: str
    request_id: str
    revision_number: int
    approved_discount_bps: int
    decided_by: str
    decided_at: datetime


class ApplicationSummary(BaseModel):
    id: str
    customer_name: str
    request_id: str | None

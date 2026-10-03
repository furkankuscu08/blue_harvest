"""Shapes of the JSON the API sends and receives, from docs/api-contract.md."""

from pydantic import BaseModel


class ApplicationSummary(BaseModel):
    id: str
    customer_name: str
    request_id: str | None

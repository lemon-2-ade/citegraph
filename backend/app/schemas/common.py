from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ResponseModel(BaseModel):
    """Base for API response models.

    Fields with defaults are always present in responses, so the published OpenAPI schema
    marks them required; generated clients then get non-optional types.
    """

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Page[T](ResponseModel):
    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size

"""Pydantic input/output models for the Fastino MCP tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class ExtractEntitiesInput(BaseModel):
    """Input for the fastino_extract_entities tool."""

    text: str = Field(
        ...,
        description="The raw text from which to extract named entities.",
        min_length=1,
    )
    entity_types: list[str] = Field(
        default=["TOOL", "COMPANY", "API", "FRAMEWORK"],
        description=(
            "Entity type labels the GLiNER model should detect. "
            "Common values: TOOL, COMPANY, API, FRAMEWORK, PERSON, LOCATION, DATE."
        ),
    )


class ClassifyTextInput(BaseModel):
    """Input for the fastino_classify_text tool."""

    text: str = Field(
        ...,
        description="The text to classify.",
        min_length=1,
    )
    labels: list[str] = Field(
        ...,
        description="Candidate classification labels (at least one required).",
        min_length=1,
    )
    multi_label: bool = Field(
        default=False,
        description=(
            "When True, multiple labels can be returned (each with its own confidence score). "
            "When False, only the single best-matching label is returned."
        ),
    )


class DetectPiiInput(BaseModel):
    """Input for the fastino_detect_pii tool."""

    text: str = Field(
        ...,
        description="Text to scan for personally-identifiable information.",
        min_length=1,
    )
    categories: list[str] | None = Field(
        default=None,
        description=(
            "Optional list of PII category filters, e.g. ['EMAIL', 'PHONE', 'SSN', 'CREDIT_CARD']. "
            "When None, all supported categories are detected."
        ),
    )


class ExtractStructuredInput(BaseModel):
    """Input for the fastino_extract_structured tool."""

    text: str = Field(
        ...,
        description="Source text from which to extract structured data.",
        min_length=1,
    )
    schema: dict[str, Any] = Field(
        ...,
        description=(
            "A JSON Schema object describing the structure to extract. "
            "The API will attempt to return JSON that conforms to this schema."
        ),
    )


class AnalyzeContentInput(BaseModel):
    """Input for the fastino_analyze_content tool."""

    text: str = Field(
        ...,
        description="The content to analyze.",
        min_length=1,
    )
    prompt: str = Field(
        ...,
        description="An instruction or question describing what analysis to perform.",
        min_length=1,
    )
    model: str = Field(
        default="fastino-flash",
        description=(
            "Fastino model variant to use for analysis. "
            "Options include 'fastino-flash' (fast, lower cost) and 'fastino-pro' (higher quality)."
        ),
    )


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class EntityResult(BaseModel):
    """A single extracted entity."""

    entity: str = Field(..., description="The extracted entity text span.")
    type: str = Field(..., description="Entity type label (e.g. TOOL, COMPANY).")
    confidence: float = Field(..., description="Model confidence score in [0, 1].", ge=0.0, le=1.0)


class ExtractEntitiesOutput(BaseModel):
    """Output for the fastino_extract_entities tool."""

    entities: list[EntityResult] = Field(
        default_factory=list,
        description="List of detected entities.",
    )


class LabelScore(BaseModel):
    """A single classification label with its confidence score."""

    label: str = Field(..., description="The classification label.")
    confidence: float = Field(..., description="Confidence score in [0, 1].", ge=0.0, le=1.0)


class ClassifyTextOutput(BaseModel):
    """Output for the fastino_classify_text tool.

    For single-label classification, ``results`` will have exactly one item.
    For multi-label, it contains all labels whose score exceeds the model threshold.
    """

    results: list[LabelScore] = Field(
        default_factory=list,
        description="Ranked list of label/confidence pairs.",
    )
    multi_label: bool = Field(
        ...,
        description="Reflects the multi_label flag used in the request.",
    )


class PiiMatch(BaseModel):
    """A single PII occurrence."""

    text: str = Field(..., description="The PII text span found in the input.")
    category: str = Field(..., description="PII category (e.g. EMAIL, PHONE, SSN).")
    start: int = Field(..., description="Start character offset in the original text.", ge=0)
    end: int = Field(..., description="End character offset (exclusive) in the original text.", ge=0)


class DetectPiiOutput(BaseModel):
    """Output for the fastino_detect_pii tool."""

    pii_found: list[PiiMatch] = Field(
        default_factory=list,
        description="All PII occurrences detected in the input text.",
    )
    redacted_text: str | None = Field(
        default=None,
        description="Optional version of the input text with PII replaced by category placeholders.",
    )


class ExtractStructuredOutput(BaseModel):
    """Output for the fastino_extract_structured tool."""

    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted JSON object conforming to the requested schema.",
    )


class AnalyzeContentOutput(BaseModel):
    """Output for the fastino_analyze_content tool."""

    analysis: str = Field(
        ...,
        description="The model's analysis or answer in response to the provided prompt.",
    )
    model: str = Field(
        ...,
        description="The Fastino model variant that produced this analysis.",
    )

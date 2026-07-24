"""Structured data contracts shared by the shopping crew's tasks."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_serializer,
)


SerializableHttpUrl = Annotated[
    AnyHttpUrl,
    PlainSerializer(lambda value: str(value), return_type=str),
]
"""An HTTP(S) URL that remains a plain string in Python-mode model dumps."""


class StructuredModel(BaseModel):
    """Base model that rejects unexpected fields and trims string values."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VerificationStatus(StrEnum):
    """How strongly a product or claim is supported by accessible evidence."""

    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    COULD_NOT_VERIFY = "could_not_verify"
    UNAVAILABLE = "unavailable"


class TotalCostStatus(StrEnum):
    """Whether a product's total purchase cost can be calculated."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    NOT_CALCULABLE = "not_calculable"


class RecommendationConfidence(StrEnum):
    """Confidence in the final recommendation based on available evidence."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Money(StructuredModel):
    """A non-negative monetary amount in its source currency."""

    amount: Decimal = Field(ge=0)
    currency: str = Field(min_length=1, max_length=16)
    label: str | None = Field(
        default=None,
        description="Optional source label such as promotion, regular, or shipping.",
    )

    @field_serializer("amount")
    def serialize_amount(self, amount: Decimal) -> str:
        """Keep decimal values exact when task output is serialized."""

        return format(amount, "f")


class ProductSpecification(StructuredModel):
    """One sourced product specification."""

    name: str = Field(min_length=1)
    value: str = Field(min_length=1)


class UserRequirements(StructuredModel):
    """The shopping request interpreted by the research agent."""

    product: str = Field(min_length=1)
    budget: str = Field(min_length=1)
    buyer_location: str = Field(min_length=1)
    important_preferences: list[str] = Field(default_factory=list)
    requested_product_count: int | None = Field(default=None, ge=1)
    research_date: date


class ResearchIssue(StructuredModel):
    """A candidate exclusion, inaccessible page, or other research limitation."""

    subject: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    source_url: SerializableHttpUrl | None = None


class ProductEvidence(StructuredModel):
    """Structured evidence collected for one unique product."""

    exact_product_model: str = Field(min_length=1)
    listed_price: Money | None = None
    original_price: Money | None = None
    specifications: list[ProductSpecification] = Field(default_factory=list)
    seller: str | None = None
    availability: str | None = None
    warranty: str | None = None
    shipping_cost: Money | None = None
    delivery_information: str | None = None
    source_url: SerializableHttpUrl
    verification_status: VerificationStatus
    unverified_fields: list[str] = Field(default_factory=list)
    verification_notes: list[str] = Field(default_factory=list)


class ProductSearchResult(StructuredModel):
    """Output contract for the Product Search Specialist."""

    requirements: UserRequirements
    products: list[ProductEvidence] = Field(default_factory=list, max_length=5)
    research_issues: list[ResearchIssue] = Field(default_factory=list)
    shortfall_reason: str | None = None


class ProductComparison(StructuredModel):
    """Price and value analysis for one product from the search result."""

    exact_product_model: str = Field(min_length=1)
    listed_price: Money | None = None
    original_price: Money | None = None
    shipping_cost: Money | None = None
    total_known_cost: Money | None = None
    total_cost_status: TotalCostStatus
    missing_cost_components: list[str] = Field(default_factory=list)
    warranty: str | None = None
    seller_reliability: str | None = None
    return_policy: str | None = None
    advantages: list[str] = Field(default_factory=list)
    disadvantages: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus
    source_urls: list[SerializableHttpUrl] = Field(default_factory=list)


class NormalPriceRange(StructuredModel):
    """A same-currency range based on comparable verified products."""

    minimum: Money
    maximum: Money
    sample_size: int = Field(ge=1)
    included_products: list[str] = Field(min_length=1)
    explanation: str = Field(min_length=1)


class BestValueDeal(StructuredModel):
    """The comparison agent's best supported deal."""

    exact_product_model: str = Field(min_length=1)
    price: Money
    seller: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    source_url: SerializableHttpUrl


class PriceComparisonResult(StructuredModel):
    """Output contract for the Price Comparison Analyst."""

    comparisons: list[ProductComparison] = Field(default_factory=list, max_length=5)
    normal_price_ranges: list[NormalPriceRange] = Field(default_factory=list)
    best_value_deal: BestValueDeal | None = None
    limitations: list[str] = Field(default_factory=list)


class RecommendationDetails(StructuredModel):
    """The selected product and its purchasing evidence."""

    exact_product_model: str = Field(min_length=1)
    verified_price: Money | None = None
    seller: str | None = None
    availability: str | None = None
    warranty: str | None = None
    delivery_information: str | None = None
    source_url: SerializableHttpUrl
    why_it_wins: str = Field(min_length=1)


class AlternativeRecommendation(StructuredModel):
    """One ranked alternative to the selected product."""

    rank: int = Field(ge=1)
    exact_product_model: str = Field(min_length=1)
    price: Money | None = None
    seller: str | None = None
    main_advantage: str = Field(min_length=1)
    verification_status: VerificationStatus
    source_url: SerializableHttpUrl | None = None


class BuyingChecklist(StructuredModel):
    """Facts the buyer must confirm before making payment."""

    exact_model_sku: str = Field(min_length=1)
    current_price: str = Field(min_length=1)
    stock: str = Field(min_length=1)
    delivery_cost: str = Field(min_length=1)
    taxes: str = Field(min_length=1)
    warranty: str = Field(min_length=1)
    return_policy: str = Field(min_length=1)
    seller_identity: str = Field(min_length=1)
    secure_payment: str = Field(min_length=1)


class SourceReference(StructuredModel):
    """A product name paired with an exact source URL."""

    product_name: str = Field(min_length=1)
    url: SerializableHttpUrl


class FinalRecommendationResult(StructuredModel):
    """Output contract for the Product Recommendation Advisor."""

    requirements: UserRequirements
    recommendation: RecommendationDetails | None = None
    alternatives: list[AlternativeRecommendation] = Field(
        default_factory=list,
        max_length=4,
    )
    advantages: list[str] = Field(default_factory=list)
    limitations_and_unverified_information: list[str] = Field(default_factory=list)
    confidence: RecommendationConfidence
    buying_checklist: BuyingChecklist
    sources: list[SourceReference] = Field(default_factory=list)

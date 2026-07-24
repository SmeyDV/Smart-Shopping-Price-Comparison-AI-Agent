"""Render and save the final recommendation from validated structured data."""

from __future__ import annotations

from pathlib import Path

from crewai.tasks.task_output import TaskOutput

from tools.schemas import FinalRecommendationResult, Money


REPORT_PATH = Path("report.md")
COULD_NOT_VERIFY = "Could not verify"


def _text(value: object | None) -> str:
    """Return a readable value for an optional structured field."""

    return str(value) if value is not None and str(value).strip() else COULD_NOT_VERIFY


def _money(value: Money | None) -> str:
    """Format exact decimal money without changing the source currency."""

    if value is None:
        return COULD_NOT_VERIFY
    rendered = f"{format(value.amount, 'f')} {value.currency}"
    return f"{rendered} ({value.label})" if value.label else rendered


def _table_cell(value: object | None) -> str:
    """Escape content that could break a Markdown table."""

    return _text(value).replace("\n", " ").replace("|", r"\|")


def _bullet_lines(values: list[str], empty_message: str) -> list[str]:
    """Render a non-empty Markdown bullet list."""

    return [f"- {value}" for value in values] or [f"- {empty_message}"]


def render_recommendation_report(result: FinalRecommendationResult) -> str:
    """Create the user-facing Markdown report from validated task data."""

    requirements = result.requirements
    preference_text = (
        ", ".join(requirements.important_preferences)
        if requirements.important_preferences
        else COULD_NOT_VERIFY
    )

    lines = [
        "# Smart Shopping Recommendation",
        "",
        "## User Requirements",
        f"- **Product**: {requirements.product}",
        f"- **Budget**: {requirements.budget}",
        f"- **Buyer location**: {requirements.buyer_location}",
        f"- **Important preferences**: {preference_text}",
        f"- **Research date**: {requirements.research_date.isoformat()}",
        "",
        "## Final Recommendation",
    ]

    recommendation = result.recommendation
    if recommendation is None:
        lines.append(
            "- No sufficiently supported product could be recommended from the "
            "available evidence."
        )
    else:
        lines.extend(
            [
                f"- **Exact product/model**: {recommendation.exact_product_model}",
                f"- **Verified price and currency**: {_money(recommendation.verified_price)}",
                f"- **Seller**: {_text(recommendation.seller)}",
                f"- **Availability**: {_text(recommendation.availability)}",
                f"- **Warranty**: {_text(recommendation.warranty)}",
                (
                    "- **Delivery information**: "
                    f"{_text(recommendation.delivery_information)}"
                ),
                f"- **Direct purchase/source URL**: {recommendation.source_url}",
                f"- **Why it wins**: {recommendation.why_it_wins}",
            ]
        )

    lines.extend(
        [
            "",
            "## Top Alternatives",
            "",
            (
                "| Rank | Product | Price | Seller | Main advantage | "
                "Verification status | Source URL |"
            ),
            "|---:|---|---|---|---|---|---|",
        ]
    )
    if result.alternatives:
        for alternative in sorted(result.alternatives, key=lambda item: item.rank):
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(alternative.rank),
                        _table_cell(alternative.exact_product_model),
                        _table_cell(_money(alternative.price)),
                        _table_cell(alternative.seller),
                        _table_cell(alternative.main_advantage),
                        _table_cell(alternative.verification_status.value),
                        _table_cell(alternative.source_url),
                    ]
                )
                + " |"
            )
    else:
        lines.append(
            f"| — | No alternatives available | {COULD_NOT_VERIFY} | "
            f"{COULD_NOT_VERIFY} | — | — | {COULD_NOT_VERIFY} |"
        )

    lines.extend(["", "## Advantages"])
    lines.extend(
        _bullet_lines(
            result.advantages,
            "No verified advantages were identified.",
        )
    )

    lines.extend(["", "## Limitations and Unverified Information"])
    lines.append(f"- **Recommendation confidence**: {result.confidence.value}")
    lines.extend(
        _bullet_lines(
            result.limitations_and_unverified_information,
            "No additional limitations were reported.",
        )
    )

    checklist = result.buying_checklist
    checklist_items = [
        ("Exact model/SKU", checklist.exact_model_sku),
        ("Current price", checklist.current_price),
        ("Stock", checklist.stock),
        ("Delivery cost", checklist.delivery_cost),
        ("Taxes", checklist.taxes),
        ("Warranty", checklist.warranty),
        ("Return policy", checklist.return_policy),
        ("Seller identity", checklist.seller_identity),
        ("Secure payment", checklist.secure_payment),
    ]
    lines.extend(["", "## Final Buying Checklist"])
    lines.extend(f"- **{label}**: {value}" for label, value in checklist_items)

    lines.extend(["", "## Sources"])
    if result.sources:
        lines.extend(
            f"{index}. [{source.product_name}]({source.url})"
            for index, source in enumerate(result.sources, start=1)
        )
    else:
        lines.append(f"1. {COULD_NOT_VERIFY}")

    return "\n".join(lines) + "\n"


def save_recommendation_report(output: TaskOutput) -> None:
    """CrewAI task callback that writes validated recommendation data to Markdown."""

    if output.pydantic is not None:
        result = FinalRecommendationResult.model_validate(
            output.pydantic.model_dump()
        )
    elif output.raw.strip():
        result = FinalRecommendationResult.model_validate_json(output.raw)
    else:
        raise ValueError(
            "Final recommendation did not produce the required structured output."
        )

    rendered = render_recommendation_report(result)
    temporary_path = REPORT_PATH.with_suffix(f"{REPORT_PATH.suffix}.tmp")
    temporary_path.write_text(rendered, encoding="utf-8")
    temporary_path.replace(REPORT_PATH)

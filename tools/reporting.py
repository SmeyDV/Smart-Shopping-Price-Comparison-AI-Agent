"""Render and save the final recommendation from validated structured data."""

from __future__ import annotations

from html import escape
from pathlib import Path

from crewai.tasks.task_output import TaskOutput
import pymupdf

from tools.schemas import FinalRecommendationResult, Money


OUTPUT_DIRECTORY = Path("outputs")
MARKDOWN_REPORT_PATH = OUTPUT_DIRECTORY / "report.md"
PDF_REPORT_PATH = OUTPUT_DIRECTORY / "report.pdf"
COULD_NOT_VERIFY = "Could not verify"
PDF_CSS = """
@page {
    size: A4;
}
body {
    color: #172033;
    font-family: sans-serif;
    font-size: 10.5pt;
    line-height: 1.4;
}
h1 {
    color: #12355b;
    font-size: 24pt;
    margin: 0 0 8pt 0;
}
h2 {
    border-bottom: 1pt solid #b8c7d9;
    color: #12355b;
    font-size: 15pt;
    margin: 18pt 0 8pt 0;
    padding-bottom: 3pt;
}
p {
    margin: 4pt 0;
}
ul, ol {
    margin: 5pt 0 8pt 18pt;
    padding: 0;
}
li {
    margin-bottom: 3pt;
}
.subtitle {
    color: #52657a;
    font-size: 10pt;
    margin-bottom: 15pt;
}
.recommendation {
    background-color: #eef6ff;
    border: 1pt solid #8cb7df;
    padding: 9pt;
}
.notice {
    background-color: #fff5dc;
    border: 1pt solid #e2bd65;
    padding: 8pt;
}
.label {
    color: #263f5a;
    font-weight: bold;
}
table {
    border-collapse: collapse;
    font-size: 8.5pt;
    margin: 7pt 0 10pt 0;
    width: 100%;
}
th {
    background-color: #12355b;
    color: white;
    font-weight: bold;
    padding: 5pt;
    text-align: left;
}
td {
    border: 0.5pt solid #b8c7d9;
    padding: 5pt;
    vertical-align: top;
}
tr:nth-child(even) td {
    background-color: #f5f8fb;
}
a {
    color: #075aa8;
    text-decoration: underline;
}
.source-list li {
    margin-bottom: 5pt;
}
"""


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


def _html_text(value: object | None) -> str:
    """Return HTML-safe text for one structured value."""

    return escape(_text(value))


def _html_money(value: Money | None) -> str:
    """Return an HTML-safe formatted monetary value."""

    return escape(_money(value))


def _html_link(url: object | None, label: str) -> str:
    """Create a safe clickable link or a missing-value label."""

    if url is None:
        return escape(COULD_NOT_VERIFY)
    safe_url = escape(str(url), quote=True)
    return f'<a href="{safe_url}">{escape(label)}</a>'


def _html_list(values: list[str], empty_message: str) -> str:
    """Render a non-empty HTML list."""

    items = values or [empty_message]
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


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


def render_recommendation_pdf(result: FinalRecommendationResult) -> bytes:
    """Create an A4 PDF report from validated recommendation data."""

    requirements = result.requirements
    preference_text = (
        ", ".join(requirements.important_preferences)
        if requirements.important_preferences
        else COULD_NOT_VERIFY
    )
    recommendation = result.recommendation

    if recommendation is None:
        recommendation_html = (
            '<div class="notice">No sufficiently supported product could be '
            "recommended from the available evidence.</div>"
        )
    else:
        recommendation_html = f"""
        <div class="recommendation">
            <p><span class="label">Exact product/model:</span>
                {_html_text(recommendation.exact_product_model)}</p>
            <p><span class="label">Verified price and currency:</span>
                {_html_money(recommendation.verified_price)}</p>
            <p><span class="label">Seller:</span>
                {_html_text(recommendation.seller)}</p>
            <p><span class="label">Availability:</span>
                {_html_text(recommendation.availability)}</p>
            <p><span class="label">Warranty:</span>
                {_html_text(recommendation.warranty)}</p>
            <p><span class="label">Delivery information:</span>
                {_html_text(recommendation.delivery_information)}</p>
            <p><span class="label">Purchase page:</span>
                {_html_link(recommendation.source_url, "Open product page")}</p>
            <p><span class="label">Why it wins:</span>
                {_html_text(recommendation.why_it_wins)}</p>
        </div>
        """

    if result.alternatives:
        alternative_rows = "".join(
            f"""
            <tr>
                <td>{alternative.rank}</td>
                <td>{_html_text(alternative.exact_product_model)}</td>
                <td>{_html_money(alternative.price)}</td>
                <td>{_html_text(alternative.seller)}</td>
                <td>{_html_text(alternative.main_advantage)}</td>
                <td>{escape(alternative.verification_status.value)}</td>
                <td>{_html_link(alternative.source_url, "Open source")}</td>
            </tr>
            """
            for alternative in sorted(
                result.alternatives,
                key=lambda item: item.rank,
            )
        )
    else:
        alternative_rows = f"""
        <tr>
            <td>—</td>
            <td>No alternatives available</td>
            <td>{COULD_NOT_VERIFY}</td>
            <td>{COULD_NOT_VERIFY}</td>
            <td>—</td>
            <td>—</td>
            <td>{COULD_NOT_VERIFY}</td>
        </tr>
        """

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
    checklist_html = "<ul>" + "".join(
        f'<li><span class="label">{escape(label)}:</span> {escape(value)}</li>'
        for label, value in checklist_items
    ) + "</ul>"

    if result.sources:
        sources_html = '<ol class="source-list">' + "".join(
            f"<li>{_html_link(source.url, source.product_name)}</li>"
            for source in result.sources
        ) + "</ol>"
    else:
        sources_html = f"<ol><li>{COULD_NOT_VERIFY}</li></ol>"

    html = f"""
    <html>
        <body>
            <h1>Smart Shopping Recommendation</h1>
            <p class="subtitle">
                Evidence-based price comparison report · Research date:
                {requirements.research_date.isoformat()}
            </p>

            <h2>User Requirements</h2>
            <ul>
                <li><span class="label">Product:</span>
                    {_html_text(requirements.product)}</li>
                <li><span class="label">Budget:</span>
                    {_html_text(requirements.budget)}</li>
                <li><span class="label">Buyer location:</span>
                    {_html_text(requirements.buyer_location)}</li>
                <li><span class="label">Important preferences:</span>
                    {escape(preference_text)}</li>
            </ul>

            <h2>Final Recommendation</h2>
            {recommendation_html}

            <h2>Top Alternatives</h2>
            <table>
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Product</th>
                        <th>Price</th>
                        <th>Seller</th>
                        <th>Main advantage</th>
                        <th>Status</th>
                        <th>Source</th>
                    </tr>
                </thead>
                <tbody>{alternative_rows}</tbody>
            </table>

            <h2>Advantages</h2>
            {_html_list(result.advantages, "No verified advantages were identified.")}

            <h2>Limitations and Unverified Information</h2>
            <p><span class="label">Recommendation confidence:</span>
                {escape(result.confidence.value)}</p>
            {_html_list(
                result.limitations_and_unverified_information,
                "No additional limitations were reported.",
            )}

            <h2>Final Buying Checklist</h2>
            {checklist_html}

            <h2>Sources</h2>
            {sources_html}
        </body>
    </html>
    """

    page_rectangle = pymupdf.paper_rect("a4")
    content_rectangle = page_rectangle + (42, 42, -42, -50)

    def page_layout(
        _page_number: int,
        _filled: pymupdf.Rect,
    ) -> tuple[pymupdf.Rect, pymupdf.Rect, None]:
        return page_rectangle, content_rectangle, None

    story = pymupdf.Story(html=html, user_css=PDF_CSS, em=11)
    document = story.write_with_links(page_layout)
    try:
        page_count = len(document)
        for page_number, page in enumerate(document, start=1):
            footer = f"Smart Shopping Report  ·  Page {page_number} of {page_count}"
            text_width = pymupdf.get_text_length(
                footer,
                fontname="helv",
                fontsize=8,
            )
            page.insert_text(
                (
                    max(42, (page_rectangle.width - text_width) / 2),
                    page_rectangle.height - 24,
                ),
                footer,
                fontname="helv",
                fontsize=8,
                color=(0.32, 0.40, 0.48),
            )

        document.set_metadata(
            {
                "title": "Smart Shopping Recommendation",
                "subject": f"Price comparison for {requirements.product}",
                "author": "Smart Shopping & Price-Comparison AI Agent",
                "creator": "PyMuPDF",
            }
        )
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def save_recommendation_report(output: TaskOutput) -> None:
    """CrewAI callback that writes validated recommendation data to MD and PDF."""

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

    markdown = render_recommendation_report(result)
    pdf = render_recommendation_pdf(result)

    MARKDOWN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PDF_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_markdown_path = MARKDOWN_REPORT_PATH.with_suffix(
        f"{MARKDOWN_REPORT_PATH.suffix}.tmp"
    )
    temporary_pdf_path = PDF_REPORT_PATH.with_suffix(
        f"{PDF_REPORT_PATH.suffix}.tmp"
    )

    try:
        temporary_markdown_path.write_text(markdown, encoding="utf-8")
        temporary_pdf_path.write_bytes(pdf)
        temporary_markdown_path.replace(MARKDOWN_REPORT_PATH)
        temporary_pdf_path.replace(PDF_REPORT_PATH)
    finally:
        temporary_markdown_path.unlink(missing_ok=True)
        temporary_pdf_path.unlink(missing_ok=True)

from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crewai.project.crew_loader import load_crew
from crewai.tasks.output_format import OutputFormat
from crewai.tasks.task_output import TaskOutput
from crewai.utilities.crew_json_encoder import CrewJSONEncoder
from pydantic import ValidationError

from tools.reporting import render_recommendation_report, save_recommendation_report
from tools.schemas import (
    AlternativeRecommendation,
    BuyingChecklist,
    FinalRecommendationResult,
    Money,
    PriceComparisonResult,
    ProductEvidence,
    ProductSearchResult,
    RecommendationConfidence,
    RecommendationDetails,
    SourceReference,
    UserRequirements,
    VerificationStatus,
)


ROOT = Path(__file__).resolve().parents[1]


def sample_requirements() -> UserRequirements:
    return UserRequirements(
        product="Gaming laptop",
        budget="Under 1,000 USD",
        buyer_location="Cambodia",
        important_preferences=["16 GB RAM", "Dedicated GPU"],
        requested_product_count=5,
        research_date=date(2026, 7, 24),
    )


def sample_product(index: int = 1) -> ProductEvidence:
    return ProductEvidence(
        exact_product_model=f"Example Laptop {index}",
        listed_price=Money(amount=Decimal("799.00"), currency="USD"),
        seller="Example Store",
        source_url=f"https://example.com/products/{index}",
        verification_status=VerificationStatus.VERIFIED,
    )


def sample_final_result() -> FinalRecommendationResult:
    return FinalRecommendationResult(
        requirements=sample_requirements(),
        recommendation=RecommendationDetails(
            exact_product_model="Example Laptop 1",
            verified_price=Money(
                amount=Decimal("799.00"),
                currency="USD",
                label="promotion",
            ),
            seller="Example Store",
            availability="In stock",
            warranty="Two years",
            delivery_information=None,
            source_url="https://example.com/products/1",
            why_it_wins="It has the strongest verified value.",
        ),
        alternatives=[
            AlternativeRecommendation(
                rank=1,
                exact_product_model="Alternative Laptop",
                price=Money(amount=Decimal("899"), currency="USD"),
                seller="Second Store",
                main_advantage="Better GPU | more memory",
                verification_status=VerificationStatus.PARTIALLY_VERIFIED,
                source_url="https://example.com/products/2",
            )
        ],
        advantages=["Verified price and local warranty"],
        limitations_and_unverified_information=[
            "Delivery cost could not be verified."
        ],
        confidence=RecommendationConfidence.MEDIUM,
        buying_checklist=BuyingChecklist(
            exact_model_sku="Confirm Example Laptop 1",
            current_price="Confirm 799.00 USD promotion",
            stock="Confirm current stock",
            delivery_cost="Ask for the final delivery cost",
            taxes="Confirm whether taxes are included",
            warranty="Request written warranty terms",
            return_policy="Request the return policy",
            seller_identity="Verify the seller identity",
            secure_payment="Use a secure payment method",
        ),
        sources=[
            SourceReference(
                product_name="Example Laptop 1",
                url="https://example.com/products/1",
            )
        ],
    )


class StructuredOutputSchemaTests(unittest.TestCase):
    def test_money_serializes_decimal_without_float_rounding(self) -> None:
        money = Money(amount=Decimal("799.00"), currency="USD")

        self.assertEqual(money.model_dump(mode="json")["amount"], "799.00")
        self.assertIn('"amount":"799.00"', money.model_dump_json())

    def test_product_evidence_rejects_invalid_urls_and_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            ProductEvidence(
                exact_product_model="Unsafe URL Product",
                source_url="file:///tmp/product.html",
                verification_status=VerificationStatus.VERIFIED,
            )

        with self.assertRaises(ValidationError):
            ProductEvidence(
                exact_product_model="Unexpected Field Product",
                source_url="https://example.com/product",
                verification_status=VerificationStatus.VERIFIED,
                invented_field="not allowed",
            )

    def test_product_search_result_accepts_at_most_five_products(self) -> None:
        with self.assertRaises(ValidationError):
            ProductSearchResult(
                requirements=sample_requirements(),
                products=[sample_product(index) for index in range(6)],
            )

    def test_product_search_handoff_is_json_serializable(self) -> None:
        result = ProductSearchResult(
            requirements=sample_requirements(),
            products=[sample_product()],
        )

        dumped = result.model_dump()

        self.assertIsInstance(dumped["products"][0]["source_url"], str)
        json.dumps(dumped, cls=CrewJSONEncoder)

    def test_jsonc_loader_resolves_each_output_model_and_callback(self) -> None:
        with TemporaryDirectory() as storage_directory:
            with patch.dict(
                os.environ,
                {
                    "CREWAI_STORAGE_DIR": "structured-output-test",
                    "DEEPSEEK_API_KEY": "test-deepseek",
                    "EXA_API_KEY": "test-exa",
                    "XDG_DATA_HOME": storage_directory,
                },
                clear=False,
            ):
                crew, _ = load_crew(ROOT / "crew.jsonc")

        self.assertIs(crew.tasks[0].output_pydantic, ProductSearchResult)
        self.assertIs(crew.tasks[1].output_pydantic, PriceComparisonResult)
        self.assertIsNone(crew.tasks[2].output_pydantic)
        self.assertEqual(
            crew.agents[2].llm.response_format,
            {"type": "json_object"},
        )
        self.assertIs(crew.tasks[2].callback, save_recommendation_report)


class RecommendationReportTests(unittest.TestCase):
    def test_renderer_preserves_required_section_order_and_escapes_tables(
        self,
    ) -> None:
        report = render_recommendation_report(sample_final_result())
        headings = [
            "## User Requirements",
            "## Final Recommendation",
            "## Top Alternatives",
            "## Advantages",
            "## Limitations and Unverified Information",
            "## Final Buying Checklist",
            "## Sources",
        ]

        self.assertTrue(report.startswith("# Smart Shopping Recommendation\n"))
        positions = [report.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("799.00 USD (promotion)", report)
        self.assertIn(r"Better GPU \| more memory", report)
        self.assertIn(
            "[Example Laptop 1](https://example.com/products/1)",
            report,
        )

    def test_final_task_callback_writes_markdown_from_pydantic_output(self) -> None:
        result = sample_final_result()
        output = TaskOutput(
            name="final_recommendation",
            description="Create a recommendation.",
            expected_output="Structured recommendation.",
            raw=result.model_dump_json(),
            pydantic=result,
            agent="Product Recommendation Advisor",
            output_format=OutputFormat.PYDANTIC,
        )

        with TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.md"
            with patch("tools.reporting.REPORT_PATH", report_path):
                save_recommendation_report(output)

            rendered = report_path.read_text(encoding="utf-8")

        self.assertTrue(rendered.startswith("# Smart Shopping Recommendation"))
        self.assertNotIn('"recommendation":', rendered)

    def test_final_task_callback_validates_deepseek_json_output(self) -> None:
        result = sample_final_result()
        output = TaskOutput(
            name="final_recommendation",
            description="Create a recommendation.",
            expected_output="JSON recommendation.",
            raw=result.model_dump_json(),
            agent="Product Recommendation Advisor",
            output_format=OutputFormat.RAW,
        )

        with TemporaryDirectory() as directory:
            report_path = Path(directory) / "report.md"
            with patch("tools.reporting.REPORT_PATH", report_path):
                save_recommendation_report(output)

            rendered = report_path.read_text(encoding="utf-8")

        self.assertTrue(rendered.startswith("# Smart Shopping Recommendation"))
        self.assertIn("Example Laptop 1", rendered)

    def test_final_task_callback_rejects_invalid_json_output(self) -> None:
        output = TaskOutput(
            name="final_recommendation",
            description="Create a recommendation.",
            expected_output="JSON recommendation.",
            raw='{"recommendation": "missing required fields"}',
            agent="Product Recommendation Advisor",
            output_format=OutputFormat.RAW,
        )

        with self.assertRaises(ValidationError):
            save_recommendation_report(output)


if __name__ == "__main__":
    unittest.main()

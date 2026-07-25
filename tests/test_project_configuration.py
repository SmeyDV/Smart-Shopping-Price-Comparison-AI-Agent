from __future__ import annotations

import json
import os
from pathlib import Path
import tomllib
import unittest
from unittest.mock import patch

import json5

from tools.runtime_checks import validate_runtime
from tools.guardrails import UnsupportedShoppingRequestError, VagueShoppingRequestError


ROOT = Path(__file__).resolve().parents[1]


def load_jsonc(path: Path) -> dict:
    return json5.loads(path.read_text(encoding="utf-8"))


class ProjectConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.crew = load_jsonc(ROOT / "crew.jsonc")
        cls.agents = {
            name: load_jsonc(ROOT / "agents" / f"{name}.jsonc")
            for name in cls.crew["agents"]
        }

    def test_project_is_pinned_to_python_312_and_crewai_1155(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)

        self.assertEqual(project["project"]["requires-python"], ">=3.12,<3.13")
        self.assertIn("crewai==1.15.5", project["project"]["dependencies"])
        self.assertIn(
            "crewai-tools[exa-py]==1.15.5",
            project["project"]["dependencies"],
        )
        self.assertIn("pydantic==2.12.5", project["project"]["dependencies"])
        self.assertIn("pymupdf==1.26.7", project["project"]["dependencies"])
        self.assertEqual(project["tool"]["crewai"]["definition"], "crew.jsonc")
        self.assertEqual((ROOT / ".python-version").read_text().strip(), "3.12")

    def test_exact_agents_and_deepseek_configuration(self) -> None:
        self.assertEqual(
            self.crew["agents"],
            [
                "product_search_specialist",
                "price_comparison_analyst",
                "product_recommendation_advisor",
            ],
        )

        for agent in self.agents.values():
            self.assertEqual(agent["llm"]["model"], "deepseek/deepseek-v4-flash")
            self.assertEqual(
                agent["llm"]["additional_params"]["extra_body"]["thinking"]["type"],
                "disabled",
            )
            self.assertFalse(agent["settings"]["allow_delegation"])
            self.assertFalse(agent["settings"]["planning"])
            self.assertTrue(agent["role"])
            self.assertTrue(agent["goal"])
            self.assertTrue(agent["backstory"])

        self.assertEqual(
            self.agents["product_recommendation_advisor"]["llm"][
                "response_format"
            ],
            {"type": "json_object"},
        )
        self.assertNotIn(
            "response_format",
            self.agents["product_search_specialist"]["llm"],
        )
        self.assertNotIn(
            "response_format",
            self.agents["price_comparison_analyst"]["llm"],
        )

    def test_search_tools_are_limited_by_agent_responsibility(self) -> None:
        self.assertEqual(
            self.agents["product_search_specialist"]["tools"],
            ["ExaSearchTool", "ScrapeWebsiteTool"],
        )
        self.assertEqual(
            self.agents["price_comparison_analyst"]["tools"], ["ExaSearchTool"]
        )
        self.assertEqual(self.agents["product_recommendation_advisor"]["tools"], [])

    def test_tasks_are_sequential_and_context_references_are_exact(self) -> None:
        self.assertEqual(self.crew["process"], "sequential")
        self.assertEqual(
            self.crew["before_kickoff_callbacks"],
            [{"python": "tools.runtime_checks.validate_runtime"}],
        )
        tasks = self.crew["tasks"]
        self.assertEqual(
            [task["name"] for task in tasks],
            ["product_search", "price_comparison", "final_recommendation"],
        )
        self.assertEqual(tasks[0]["agent"], "product_search_specialist")
        self.assertNotIn("context", tasks[0])
        self.assertEqual(tasks[1]["agent"], "price_comparison_analyst")
        self.assertEqual(tasks[1]["context"], ["product_search"])
        self.assertEqual(tasks[2]["agent"], "product_recommendation_advisor")
        self.assertEqual(
            tasks[2]["context"], ["product_search", "price_comparison"]
        )
        self.assertEqual(
            tasks[0]["output_pydantic"],
            {"python": "tools.schemas.ProductSearchResult"},
        )
        self.assertEqual(
            tasks[1]["output_pydantic"],
            {"python": "tools.schemas.PriceComparisonResult"},
        )
        self.assertNotIn("output_pydantic", tasks[2])
        self.assertIn("Return only the JSON object", tasks[2]["description"])
        self.assertEqual(
            tasks[2]["callback"],
            {"python": "tools.reporting.save_recommendation_report"},
        )
        self.assertNotIn("output_file", tasks[2])

        known_task_ids = {task["name"] for task in tasks}
        for task in tasks:
            self.assertTrue(task["description"])
            self.assertTrue(task["expected_output"])
            self.assertIn(task["agent"], self.crew["agents"])
            self.assertTrue(set(task.get("context", [])).issubset(known_task_ids))

    def test_token_and_tool_use_limits_are_bounded(self) -> None:
        expected_limits = {
            "product_search_specialist": 8,
            "price_comparison_analyst": 4,
            "product_recommendation_advisor": 2,
        }
        for name, agent in self.agents.items():
            self.assertEqual(agent["llm"]["max_tokens"], 4096)
            self.assertEqual(agent["settings"]["max_iter"], expected_limits[name])
            self.assertEqual(agent["settings"]["max_retry_limit"], 1)

        product_search = self.crew["tasks"][0]["description"]
        price_comparison = self.crew["tasks"][1]["description"]
        self.assertIn("no more than two Exa searches total", product_search)
        self.assertIn("Make at most one targeted Exa verification search", price_comparison)

    def test_product_query_is_a_declared_default_and_used_by_every_task(self) -> None:
        query = self.crew["inputs"].get("product_query")
        self.assertIsInstance(query, str)
        self.assertTrue(query.strip())
        for task in self.crew["tasks"]:
            self.assertIn("{product_query}", task["description"])

    def test_example_env_lists_required_keys_without_real_values(self) -> None:
        lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        values = dict(
            line.split("=", 1)
            for line in lines
            if line and not line.lstrip().startswith("#")
        )
        self.assertEqual(
            set(values), {"DEEPSEEK_API_KEY", "EXA_API_KEY"}
        )
        self.assertTrue(all(value.startswith("your_") for value in values.values()))

    def test_serper_is_not_referenced(self) -> None:
        checked_paths = [
            ROOT / "pyproject.toml",
            ROOT / "crew.jsonc",
            ROOT / ".env.example",
            *sorted((ROOT / "agents").glob("*.jsonc")),
        ]
        for path in checked_paths:
            self.assertNotIn(
                "serper", path.read_text(encoding="utf-8").lower(), path.name
            )

    def test_configuration_contains_no_embedded_secret_like_values(self) -> None:
        config_text = json.dumps(
            {"crew": self.crew, "agents": self.agents}, sort_keys=True
        )
        self.assertNotIn("api_key", config_text.lower())

    def test_runtime_check_rejects_missing_keys(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                RuntimeError, "DEEPSEEK_API_KEY, EXA_API_KEY"
            ):
                validate_runtime({"product_query": "gaming laptop under $1000"})

    def test_runtime_check_accepts_present_keys_and_query(self) -> None:
        inputs = {"product_query": "gaming laptop under $1000"}
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "test-deepseek", "EXA_API_KEY": "test-exa"},
            clear=True,
        ):
            self.assertIs(validate_runtime(inputs), inputs)

    def test_runtime_guardrail_rejects_illegal_drug_requests_before_key_checks(
        self,
    ) -> None:
        unsafe_queries = [
            "Find the best illegal drug in Cambodia under $200",
            "Compare ILLEGAL   DRUGS by price",
            "Find cheap cocaine",
            "Order crystal meth",
            "Find fentanyl test strips and cheap cocaine",
        ]

        with patch.dict(os.environ, {}, clear=True):
            for query in unsafe_queries:
                with self.subTest(query=query):
                    with self.assertRaisesRegex(
                        UnsupportedShoppingRequestError,
                        "Shopping request rejected",
                    ):
                        validate_runtime({"product_query": query})

    def test_runtime_guardrail_allows_legitimate_health_products(self) -> None:
        safe_queries = [
            "Compare home drug testing kits under $50",
            "Find fentanyl test strips under $30 for a harm-reduction program",
            "Find a pharmacy blood pressure monitor under $60",
            "Find a locked medicine storage box under $40",
        ]

        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "test-deepseek", "EXA_API_KEY": "test-exa"},
            clear=True,
        ):
            for query in safe_queries:
                with self.subTest(query=query):
                    inputs = {"product_query": query}
                    self.assertIs(validate_runtime(inputs), inputs)

    def test_runtime_guardrail_rejects_vague_scope_requests(self) -> None:
        vague_queries = [
            "laptop",
            "cheap phone",
            "Find me the best eating restaurent in cambodia phnom penh",
            "Find a good mechanical keyboard",
        ]

        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "test-deepseek", "EXA_API_KEY": "test-exa"},
            clear=True,
        ):
            for query in vague_queries:
                with self.subTest(query=query):
                    with self.assertRaisesRegex(
                        VagueShoppingRequestError,
                        "Shopping request rejected",
                    ):
                        validate_runtime({"product_query": query})

    def test_runtime_guardrail_allows_scoped_requests(self) -> None:
        scoped_queries = [
            "Find a gaming laptop under $1000 for Cambodia",
            "Compare top 5 wireless earbuds",
            "Find a 4K monitor for video editing, any budget",
        ]

        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "test-deepseek", "EXA_API_KEY": "test-exa"},
            clear=True,
        ):
            for query in scoped_queries:
                with self.subTest(query=query):
                    inputs = {"product_query": query}
                    self.assertIs(validate_runtime(inputs), inputs)


if __name__ == "__main__":
    unittest.main()

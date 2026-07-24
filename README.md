# Smart Shopping & Price-Comparison AI Agent

This CrewAI 1.15.5 project searches for products, verifies original product
pages, compares total costs, and produces an evidence-based recommendation.
The first two task handoffs exchange validated Pydantic data instead of
free-form reports. The final agent uses DeepSeek's supported JSON-object mode;
the callback validates that JSON as `FinalRecommendationResult` before a
deterministic renderer converts it to Markdown. The crew deliberately labels
information that cannot be verified instead of filling gaps with guesses.

## What the crew does

1. `product_search` finds at least five unique candidates when enough reliable
   results exist. It records source URLs and missing data.
2. `price_comparison` compares only the verified search results. It keeps
   currencies separate and does not count unknown shipping as zero.
3. `final_recommendation` recommends the best supported option and gives safe
   buying checks for a buyer in the requested location.

The workflow uses these structured contracts:

- `ProductSearchResult` contains interpreted requirements, product evidence,
  research issues, and any result-count shortfall.
- `PriceComparisonResult` contains per-product costs, value analysis,
  same-currency ranges, the optional best-value deal, and limitations.
- `FinalRecommendationResult` contains the recommendation, alternatives,
  confidence, buying checklist, and exact source references.

Internet access is deliberately limited:

- The Product Search Specialist uses `ExaSearchTool` to find current results
  and return source links.
- `ScrapeWebsiteTool` opens an HTTP(S) product page so its details can be
  checked.
- The Price Comparison Analyst has `ExaSearchTool`, but its task restricts it
  to targeted verification of a critical missing, stale, or conflicting fact.
- The Product Recommendation Advisor has no search tools and uses prior task
  context only.

## Setup

The project is pinned to Python 3.12 and CrewAI 1.15.5. `uv` will create and
use the local `.venv`; it does not modify the system Python installation.

```bash
cp .env.example .env
```

Add these values to `.env`:

```dotenv
DEEPSEEK_API_KEY=your_real_deepseek_api_key
EXA_API_KEY=your_real_exa_api_key
```

Then install the locked dependencies:

```bash
uv sync --locked
```

The crew checks that both required keys are present before starting paid model
work. The providers still decide whether the supplied keys are valid.

## Run

The default input is the requested Cambodia gaming-laptop test:

```bash
uv run crewai run
```

To ask a different shopping question:

```bash
uv run crewai run --inputs '{"product_query":"Find a reliable Android phone under $400 available in Cambodia."}'
```

The final agent uses `response_format: {"type":"json_object"}` because that is
the structured response type supported by DeepSeek. A task callback validates
the returned object with Pydantic, then overwrites `report.md` with the rendered
recommendation. Open that file in VS Code's Markdown Preview to view the
formatted report. It is ignored by Git because it is generated output and may
contain time-sensitive shopping information.

To control API cost and context growth, Product Search uses at most two focused
Exa searches and verifies at most five usable product pages plus one replacement.
Price Comparison can make at most one targeted verification search. Agent
iteration, retry, and output-token limits are also intentionally bounded.

## Check the configuration without spending API credits

```bash
uv run python -m unittest discover -s tests -v
```

## Project structure

```text
.
├── agents/
│   ├── price_comparison_analyst.jsonc
│   ├── product_recommendation_advisor.jsonc
│   └── product_search_specialist.jsonc
├── knowledge/
│   └── user_preference.txt
├── skills/
│   └── .gitkeep
├── tests/
│   ├── test_project_configuration.py
│   └── test_structured_outputs.py
├── tools/
│   ├── __init__.py
│   ├── reporting.py
│   ├── runtime_checks.py
│   └── schemas.py
├── .env.example
├── .gitignore
├── .python-version
├── crew.jsonc
├── pyproject.toml
└── uv.lock
```

The `.env`, `.venv`, and pre-fix backups are intentionally not committed.

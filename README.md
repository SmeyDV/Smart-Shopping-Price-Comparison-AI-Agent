# Smart Shopping & Price-Comparison AI Agent

This CrewAI 1.15.5 project searches for products, verifies original product
pages, compares total costs, and produces an evidence-based recommendation.
The first two task handoffs exchange validated Pydantic data instead of
free-form reports. The final agent uses DeepSeek's supported JSON-object mode;
the callback validates that JSON as `FinalRecommendationResult` before
deterministic renderers convert it to Markdown and PDF reports. The crew
deliberately labels information that cannot be verified instead of filling
gaps with guesses.

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

Before any search or model call, a deterministic input guardrail rejects
explicit shopping requests for illegal drugs or illicit controlled substances.
The run stops with a clear `Shopping request rejected` message, so unsafe
requests do not consume Exa or DeepSeek credits. Legitimate products such as
drug-testing kits, medicine storage, and pharmacy equipment remain supported.

A second guardrail rejects requests that are too vague to search and
compare: fewer than two descriptive words, or no budget, product count, or
explicit "any budget" opt-out. For example, `"laptop"` or `"best restaurant
in Phnom Penh"` are rejected, while `"gaming laptop under $1000"` or
`"compare top 5 wireless earbuds"` pass through.

The final agent uses `response_format: {"type":"json_object"}` because that is
the structured response type supported by DeepSeek. A task callback validates
the returned object with Pydantic, then creates:

- `outputs/report.md` for Markdown preview and editing.
- `outputs/report.pdf` for viewing, printing, or sharing.

Both files come from the same validated result, so PDF generation does not
require another agent or API request. The files are ignored by Git because they
are generated output and may contain time-sensitive shopping information.

To control API cost and context growth, Product Search uses at most two focused
Exa searches and verifies at most five usable product pages plus one replacement.
Price Comparison can make at most one targeted verification search. Agent
iteration, retry, and output-token limits are also intentionally bounded.

## Check the configuration without spending API credits

```bash
uv run python -m unittest discover -s tests -v
```

## Web interface

A Streamlit interface (`app.py`) wraps the same `crewai run` command described
above: it prompts for a product-shopping request, runs the crew as a
subprocess, and then renders `outputs/report.md` with download buttons for
`outputs/report.md` and `outputs/report.pdf`.

Install dependencies (Streamlit is a pinned dependency in `pyproject.toml`,
same as the rest of the project):

```bash
uv sync --locked
```

Launch the interface:

```bash
uv run streamlit run app.py
```

Streamlit opens the app in your browser, normally at
`http://localhost:8501`. Required environment variables are the same as
above — `DEEPSEEK_API_KEY` and `EXA_API_KEY` in `.env` — checked by the same
`validate_runtime` guardrail before any paid search or model call. Unsafe or
too-vague requests are rejected in the interface with the same messages the
CLI produces.

This first version is intended for a single local user: `outputs/report.md`
and `outputs/report.pdf` are shared, fixed-path files, so two concurrent runs
(or two browser tabs) would overwrite each other's report.

If a run fails, the interface shows a clean error message and also saves the
full (secret-redacted) crew output to `outputs/last_run_debug.log` for
troubleshooting. This is deliberate: a browser page reload starts a new
Streamlit session with fresh state, so an in-page error would otherwise be
lost if you refresh before reading it.

## Project structure

```text
.
├── agents/
│   ├── price_comparison_analyst.jsonc
│   ├── product_recommendation_advisor.jsonc
│   └── product_search_specialist.jsonc
├── knowledge/
│   └── user_preference.txt
├── outputs/
│   └── .gitkeep
├── skills/
│   └── .gitkeep
├── tests/
│   ├── test_app.py
│   ├── test_project_configuration.py
│   └── test_structured_outputs.py
├── tools/
│   ├── __init__.py
│   ├── guardrails.py
│   ├── reporting.py
│   ├── runtime_checks.py
│   └── schemas.py
├── .env.example
├── .gitignore
├── .python-version
├── app.py
├── crew.jsonc
├── pyproject.toml
└── uv.lock
```

The `.env`, `.venv`, pre-fix backups, and generated report files are
intentionally not committed.

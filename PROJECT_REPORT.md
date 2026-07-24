# Smart Shopping & Price-Comparison AI Agent

## 1. Project Overview

The Smart Shopping & Price-Comparison AI Agent is an autonomous multi-agent
system built with CrewAI. A user provides a short shopping request containing
the desired product, budget, preferences, and location. The system then
researches products, verifies available information, compares the candidates,
and produces a purchasing recommendation with source URLs.

## 2. Project Objective

The objective is to reduce the time and effort required to research products
across different online stores. The system completes a multi-step shopping
workflow with minimal human intervention while avoiding unsupported claims.

Example input:

> Find the best smartphone under $500 available in Cambodia.

## 3. Technologies and External Tools

- **CrewAI:** Orchestrates the agents, tasks, context, and sequential workflow.
- **DeepSeek V4 Flash:** Performs reasoning, comparison, and recommendation.
- **ExaSearchTool:** Searches the web for relevant products and source URLs.
- **ScrapeWebsiteTool:** Reads product pages to verify available information.
- **Pydantic:** Defines and validates the structured data exchanged by tasks.
- **Python and uv:** Provide the runtime and dependency management.

API keys are loaded from `.env` and are never hardcoded in the project.

## 4. Agent Workflow

The workflow contains three specialized agents:

1. **Product Search Specialist** searches for matching products with Exa and
   verifies selected product pages.
2. **Price Comparison Analyst** compares verified prices, specifications,
   sellers, warranties, availability, and delivery information. It performs
   only one additional targeted search when a critical fact requires
   verification.
3. **Product Recommendation Advisor** uses only the results of the first two
   tasks to select the best-supported option and alternatives.

The tasks run sequentially and exchange or validate structured objects:

```text
User request
    → ProductSearchResult
    → PriceComparisonResult
    → FinalRecommendationResult
    → Deterministic Markdown renderer
    → report.md
```

## 5. Reliability and Efficiency

The agents must include direct source URLs and must not fabricate prices,
sellers, availability, reviews, warranties, shipping details, or purchase
links. Missing evidence is labeled **Could not verify**.

Pydantic schemas give the inter-agent handoffs a fixed set of typed fields and
reject unexpected fields. The final agent uses DeepSeek's supported JSON-object
response mode, and the report callback validates that JSON against
`FinalRecommendationResult`. Prices use exact decimal values, product URLs must
use HTTP(S), and the product-search result accepts no more than five product
records. These structural checks complement the agents' evidence instructions;
they do not independently prove that every shopping claim is true.

To control API cost and token usage, product research is limited to two focused
Exa searches and five verified product pages plus one replacement. The price
analyst may make only one targeted verification search. Agent iteration,
retry, and output-token limits are also bounded.

## 6. Output

The final Markdown recommendation contains:

- User requirements
- Recommended product and reason
- Verified price, seller, and purchase URL
- Top alternatives
- Advantages and limitations
- Unverified information
- Safe-buying checklist
- Numbered source list

After the final structured result is validated, a Python callback renders the
fixed report sections and automatically saves the recommendation to
`report.md`.

## 7. Conclusion

This project satisfies the requirement for an autonomous AI agent that uses
CrewAI, external tools, multi-step reasoning, and workflow orchestration. With
one short user request, the system performs an end-to-end product-research and
recommendation task while preserving sources and clearly identifying
information that could not be verified.

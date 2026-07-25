"""Streamlit interface for the Smart Shopping & Price-Comparison AI Agent.

This is a thin front end over the existing crew: it shells out to the same
``uv run crewai run --inputs '{"product_query": "..."}'`` command described in
README.md, then displays ``outputs/report.md`` / ``outputs/report.pdf`` once
the run finishes. It does not change the agents, tasks, schemas, or
guardrails defined in crew.jsonc and tools/.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
MARKDOWN_REPORT_PATH = PROJECT_ROOT / "outputs" / "report.md"
PDF_REPORT_PATH = PROJECT_ROOT / "outputs" / "report.pdf"
# A page reload starts a brand-new Streamlit session (fresh st.session_state),
# so a failed run's details would otherwise vanish if the user refreshes
# before reading them. Persisting the last failure to disk keeps it
# inspectable regardless of what happens to the browser tab.
DEBUG_LOG_PATH = PROJECT_ROOT / "outputs" / "last_run_debug.log"

# The three-agent crew makes real Exa + DeepSeek calls across sequential
# tasks; ten minutes gives it room to finish without letting a stuck run
# block the app indefinitely.
DEFAULT_TIMEOUT_SECONDS = 600
SECRET_ENV_VAR_NAMES = ("DEEPSEEK_API_KEY", "EXA_API_KEY")
_OUTPUT_TAIL_LINES = 40

EXAMPLE_PROMPTS = [
    (
        "Phone under $400 (Cambodia)",
        "Find a reliable Android phone under $400 available in Cambodia.",
    ),
    (
        "Top 5 wireless earbuds",
        "Compare top 5 wireless earbuds under $100.",
    ),
    (
        "4K monitor, any budget",
        "Find a 4K monitor for video editing, any budget.",
    ),
]


@dataclass
class CrewRunResult:
    """Outcome of one ``crewai run`` subprocess invocation."""

    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool


def validate_query(product_query: str) -> str | None:
    """Return a validation error message, or None when the query is usable.

    This only catches an empty request. Vagueness and disallowed-product
    checks stay in tools/guardrails.py (via the crew's before_kickoff
    callback) so this UI never drifts from the rules the crew enforces.
    """

    if not product_query or not product_query.strip():
        return "Enter a product-shopping request before comparing products."
    return None


def build_crew_command(product_query: str) -> list[str]:
    """Build the equivalent of ``uv run crewai run --inputs '{"product_query": "..."}'``.

    Returned as an argument list (never a shell string) so the query text
    cannot be interpreted as shell syntax.
    """

    payload = json.dumps({"product_query": product_query})
    return ["uv", "run", "crewai", "run", "--inputs", payload]


def redact_secrets(text: str) -> str:
    """Replace any literal API key values with a placeholder, defense in depth.

    The crew's guardrails only ever report whether a key is present, never
    its value, so this should normally be a no-op. It exists so that a
    future error message referencing an env var value can never leak into
    the UI.
    """

    redacted = text
    for name in SECRET_ENV_VAR_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            redacted = redacted.replace(value, "[REDACTED]")
    return redacted


def run_crew(
    product_query: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    cwd: Path = PROJECT_ROOT,
) -> CrewRunResult:
    """Run the crew as a subprocess and capture its result.

    ``CREWAI_DMN=1`` forces the CLI's plain-text (non-interactive) output
    path instead of its Textual-based TUI, which requires a real terminal
    and hangs when launched from a subprocess without one.
    """

    env = os.environ.copy()
    env["CREWAI_DMN"] = "1"
    command = build_crew_command(product_query)

    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        return CrewRunResult(
            returncode=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            timed_out=True,
        )

    return CrewRunResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
    )


_GUARDRAIL_MESSAGE_RE = re.compile(
    r"Shopping request rejected:.*", re.MULTILINE
)
_MISSING_API_KEY_RE = re.compile(
    r"Missing required API key\(s\):.*", re.MULTILINE
)


def extract_guardrail_message(output: str) -> str | None:
    """Pull the deterministic guardrail message out of a failed run's output."""

    match = _GUARDRAIL_MESSAGE_RE.search(output)
    return match.group(0).strip() if match else None


def extract_missing_api_key_message(output: str) -> str | None:
    """Pull the missing-API-key message out of a failed run's output."""

    match = _MISSING_API_KEY_RE.search(output)
    return match.group(0).strip() if match else None


def tail_lines(text: str, max_lines: int = _OUTPUT_TAIL_LINES) -> str:
    """Return only the last few lines of text, for a compact debug view."""

    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[-max_lines:])


_VALIDATION_ERROR_RE = re.compile(r"pydantic(?:_core)?[.\w]*ValidationError")


def is_output_validation_error(output: str) -> bool:
    """Detect the final agent's JSON failing FinalRecommendationResult validation.

    tools/reporting.save_recommendation_report intentionally lets this
    propagate (see tests/test_structured_outputs.py) rather than silently
    accepting malformed data, so it surfaces as a plain crew failure. This
    only relabels that known failure mode with a clearer explanation; it
    does not change whether the run succeeds or what gets validated.
    """

    return bool(_VALIDATION_ERROR_RE.search(output))


def write_debug_log(text: str) -> None:
    """Persist redacted run output to disk so it survives a page reload."""

    DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEBUG_LOG_PATH.write_text(redact_secrets(text), encoding="utf-8")


def summarize_failure(result: CrewRunResult, timeout: int) -> tuple[str, str]:
    """Classify a failed/timed-out run into a (level, message) pair.

    ``level`` is one of "warning" (an expected guardrail rejection) or
    "error" (configuration problem or unexpected failure).
    """

    if result.timed_out:
        return (
            "error",
            f"The crew did not finish within {timeout} seconds and was "
            "stopped. Try a narrower request, or re-run later.",
        )

    combined = f"{result.stdout}\n{result.stderr}"

    guardrail_message = extract_guardrail_message(combined)
    if guardrail_message:
        return "warning", guardrail_message

    missing_key_message = extract_missing_api_key_message(combined)
    if missing_key_message:
        return (
            "error",
            f"{missing_key_message} Add valid values to .env using "
            ".env.example as the template, then try again.",
        )

    if is_output_validation_error(combined):
        return (
            "error",
            "The recommendation agent's response didn't match the expected "
            "report format (a data validation error). This can happen "
            "occasionally depending on the model's output — try running "
            "the same request again.",
        )

    return (
        "error",
        "The crew run failed unexpectedly. See the details below.",
    )


def render_result(result: CrewRunResult, timeout: int) -> None:
    """Render a finished run's outcome: success report or a clean error."""

    if result.timed_out or result.returncode != 0:
        level, message = summarize_failure(result, timeout)
        getattr(st, level)(message)

        if level == "error":
            full_output = f"{result.stdout}\n{result.stderr}".strip()
            if full_output:
                write_debug_log(full_output)
                st.caption(f"Full (redacted) output saved to `{DEBUG_LOG_PATH}`.")
                with st.expander("Run details (for troubleshooting)"):
                    st.code(redact_secrets(tail_lines(full_output)))
        return

    if not MARKDOWN_REPORT_PATH.exists():
        st.error(
            "The crew run finished, but outputs/report.md was not created. "
            "See the run details below."
        )
        write_debug_log(result.stdout)
        st.caption(f"Full (redacted) output saved to `{DEBUG_LOG_PATH}`.")
        with st.expander("Run details (for troubleshooting)"):
            st.code(redact_secrets(tail_lines(result.stdout)))
        return

    st.success("Comparison complete.")
    report_markdown = MARKDOWN_REPORT_PATH.read_text(encoding="utf-8")
    st.markdown(report_markdown)

    download_columns = st.columns(2)
    with download_columns[0]:
        st.download_button(
            "Download report.md",
            data=report_markdown,
            file_name="report.md",
            mime="text/markdown",
        )
    with download_columns[1]:
        if PDF_REPORT_PATH.exists():
            st.download_button(
                "Download report.pdf",
                data=PDF_REPORT_PATH.read_bytes(),
                file_name="report.pdf",
                mime="application/pdf",
            )
        else:
            st.info("outputs/report.pdf was not found.")


def main() -> None:
    st.set_page_config(page_title="Smart Shopping & Price Comparison", page_icon="🛒")
    st.title("🛒 Smart Shopping & Price-Comparison AI Agent")
    st.write(
        "Describe what you want to buy, and a three-agent crew will search "
        "for candidate products, compare verified prices, and produce an "
        "evidence-based recommendation report. Requests that are unsafe or "
        "too vague to search are rejected before any paid search or model "
        "call is made."
    )

    st.session_state.setdefault("product_query", "")
    st.session_state.setdefault("is_running", False)
    st.session_state.setdefault("last_result", None)

    st.caption("Try an example:")
    example_columns = st.columns(len(EXAMPLE_PROMPTS))
    for column, (label, example_query) in zip(example_columns, EXAMPLE_PROMPTS):
        if column.button(label, disabled=st.session_state.is_running):
            st.session_state.product_query = example_query
            st.rerun()

    st.text_area(
        "Product-shopping request",
        key="product_query",
        height=100,
        placeholder="e.g. Find a gaming laptop under $1000 for Cambodia.",
        disabled=st.session_state.is_running,
    )

    run_clicked = st.button(
        "Compare Products",
        type="primary",
        disabled=st.session_state.is_running,
    )

    if run_clicked:
        validation_error = validate_query(st.session_state.product_query)
        if validation_error:
            st.error(validation_error)
        else:
            st.session_state.is_running = True
            st.rerun()

    if st.session_state.is_running:
        with st.spinner(
            "Running the shopping crew... this can take several minutes."
        ):
            st.session_state.last_result = run_crew(st.session_state.product_query)
        st.session_state.is_running = False
        st.rerun()

    if st.session_state.last_result is not None:
        render_result(st.session_state.last_result, DEFAULT_TIMEOUT_SECONDS)

    render_guidance_card()


def render_guidance_card() -> None:
    """Show a fixed help card at the bottom of the page with usage guidance."""

    st.divider()
    with st.container(border=True):
        st.markdown("#### 💡 Tips for good results")
        st.markdown(
            "- Include a **budget** (e.g. \"under $500\") or a **product "
            "count** (e.g. \"compare 5 options\"), or say \"any budget\" — "
            "requests that are too vague to search are rejected before any "
            "search or model call runs.\n"
            "- Mention your **location** if delivery or availability "
            "matters (e.g. \"available in Cambodia\").\n"
            "- Requests for illegal drugs or controlled substances aren't "
            "supported; legitimate health products such as drug-testing "
            "kits are fine.\n"
            "- Each run does real product research and price verification "
            "across three agents, so expect it to take a few minutes, not "
            "seconds.\n"
            f"- If a run fails, the full (secret-redacted) output is also "
            f"saved to `{DEBUG_LOG_PATH.relative_to(PROJECT_ROOT)}` for "
            "troubleshooting.\n"
            "- This app is built for a single local user at a time — "
            "`outputs/report.md` and `outputs/report.pdf` are shared files, "
            "so concurrent runs will overwrite each other's report."
        )


if __name__ == "__main__":
    main()

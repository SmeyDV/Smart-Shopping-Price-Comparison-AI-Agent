"""Unit tests for the Streamlit app's helper functions.

These cover only the plain-Python helpers in app.py (command building,
validation, and output parsing). They never invoke uv, crewai, Exa, or
DeepSeek, so they run offline and at no API cost.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app import (
    CrewRunResult,
    build_crew_command,
    extract_guardrail_message,
    extract_missing_api_key_message,
    is_output_validation_error,
    redact_secrets,
    render_result,
    run_crew,
    summarize_failure,
    tail_lines,
    validate_query,
    write_debug_log,
)


class ValidateQueryTests(unittest.TestCase):
    def test_rejects_empty_and_whitespace_only_queries(self) -> None:
        self.assertIsNotNone(validate_query(""))
        self.assertIsNotNone(validate_query("   \n\t  "))

    def test_accepts_a_non_empty_query(self) -> None:
        self.assertIsNone(validate_query("gaming laptop under $1000"))


class BuildCrewCommandTests(unittest.TestCase):
    def test_command_is_an_argument_list_with_no_shell_involved(self) -> None:
        command = build_crew_command("gaming laptop under $1000")

        self.assertEqual(
            command[:4], ["uv", "run", "crewai", "run"]
        )
        self.assertEqual(command[4], "--inputs")

    def test_query_is_serialized_as_json_and_round_trips(self) -> None:
        tricky_query = "laptop under $1000; rm -rf / && echo \"pwned\" `whoami`"
        command = build_crew_command(tricky_query)
        payload = json.loads(command[-1])

        self.assertEqual(payload, {"product_query": tricky_query})

    def test_query_is_never_split_into_extra_argv_entries(self) -> None:
        command = build_crew_command("a b c")
        self.assertEqual(len(command), 6)


class RedactSecretsTests(unittest.TestCase):
    def test_replaces_known_secret_env_values_with_a_placeholder(self) -> None:
        with patch.dict(
            os.environ,
            {"DEEPSEEK_API_KEY": "sk-super-secret", "EXA_API_KEY": "exa-secret"},
            clear=False,
        ):
            text = "error near token sk-super-secret and exa-secret in log"
            redacted = redact_secrets(text)

        self.assertNotIn("sk-super-secret", redacted)
        self.assertNotIn("exa-secret", redacted)
        self.assertIn("[REDACTED]", redacted)

    def test_leaves_ordinary_text_unchanged_when_no_keys_are_set(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            text = "no secrets to see here"
            self.assertEqual(redact_secrets(text), text)


class ExtractMessageTests(unittest.TestCase):
    def test_extracts_guardrail_rejection_message(self) -> None:
        output = (
            "Traceback (most recent call last):\n"
            "  ...\n"
            "tools.guardrails.VagueShoppingRequestError: Shopping request "
            "rejected: too vague to search and compare.\n"
        )
        message = extract_guardrail_message(output)

        self.assertIsNotNone(message)
        assert message is not None
        self.assertTrue(message.startswith("Shopping request rejected:"))

    def test_returns_none_when_no_guardrail_message_present(self) -> None:
        self.assertIsNone(extract_guardrail_message("some unrelated failure"))

    def test_extracts_missing_api_key_message(self) -> None:
        output = (
            "RuntimeError: Missing required API key(s): DEEPSEEK_API_KEY, "
            "EXA_API_KEY. Add valid values to .env using .env.example as "
            "the template.\n"
        )
        message = extract_missing_api_key_message(output)

        self.assertIsNotNone(message)
        assert message is not None
        self.assertIn("DEEPSEEK_API_KEY", message)

    def test_returns_none_when_no_missing_key_message_present(self) -> None:
        self.assertIsNone(extract_missing_api_key_message("some unrelated failure"))


class TailLinesTests(unittest.TestCase):
    def test_returns_full_text_when_under_the_limit(self) -> None:
        text = "line1\nline2"
        self.assertEqual(tail_lines(text, max_lines=5), text)

    def test_truncates_to_the_last_n_lines(self) -> None:
        text = "\n".join(f"line{i}" for i in range(10))
        result = tail_lines(text, max_lines=3)

        self.assertEqual(result, "line7\nline8\nline9")


class SummarizeFailureTests(unittest.TestCase):
    def test_timeout_produces_an_error_level_message(self) -> None:
        result = CrewRunResult(returncode=None, stdout="", stderr="", timed_out=True)
        level, message = summarize_failure(result, timeout=600)

        self.assertEqual(level, "error")
        self.assertIn("600 seconds", message)

    def test_guardrail_rejection_produces_a_warning_level_message(self) -> None:
        result = CrewRunResult(
            returncode=1,
            stdout="",
            stderr=(
                "tools.guardrails.UnsupportedShoppingRequestError: Shopping "
                "request rejected: this agent cannot search for illegal drugs."
            ),
            timed_out=False,
        )
        level, message = summarize_failure(result, timeout=600)

        self.assertEqual(level, "warning")
        self.assertTrue(message.startswith("Shopping request rejected:"))

    def test_missing_api_key_produces_an_error_level_message(self) -> None:
        result = CrewRunResult(
            returncode=1,
            stdout="",
            stderr="RuntimeError: Missing required API key(s): EXA_API_KEY.",
            timed_out=False,
        )
        level, message = summarize_failure(result, timeout=600)

        self.assertEqual(level, "error")
        self.assertIn("EXA_API_KEY", message)
        self.assertIn(".env.example", message)

    def test_unrecognized_failure_falls_back_to_a_generic_error(self) -> None:
        result = CrewRunResult(
            returncode=1,
            stdout="",
            stderr="Traceback: something unexpected exploded",
            timed_out=False,
        )
        level, message = summarize_failure(result, timeout=600)

        self.assertEqual(level, "error")
        self.assertIn("failed unexpectedly", message)

    def test_output_validation_error_gets_a_clearer_message(self) -> None:
        result = CrewRunResult(
            returncode=1,
            stdout="",
            stderr=(
                "  File \".../tools/reporting.py\", line 482, in "
                "save_recommendation_report\n"
                "    result = FinalRecommendationResult.model_validate(...)\n"
                "pydantic_core._pydantic_core.ValidationError: 1 validation "
                "error for FinalRecommendationResult\n"
            ),
            timed_out=False,
        )
        level, message = summarize_failure(result, timeout=600)

        self.assertEqual(level, "error")
        self.assertIn("didn't match the expected report format", message)


class IsOutputValidationErrorTests(unittest.TestCase):
    def test_detects_pydantic_core_validation_error(self) -> None:
        text = "pydantic_core._pydantic_core.ValidationError: 1 validation error"
        self.assertTrue(is_output_validation_error(text))

    def test_detects_plain_pydantic_validation_error(self) -> None:
        text = "pydantic.ValidationError: 2 validation errors for Money"
        self.assertTrue(is_output_validation_error(text))

    def test_returns_false_for_unrelated_output(self) -> None:
        self.assertFalse(is_output_validation_error("connection refused"))


class WriteDebugLogTests(unittest.TestCase):
    def test_writes_redacted_text_to_the_debug_log_path(self) -> None:
        with TemporaryDirectory() as directory:
            log_path = Path(directory) / "outputs" / "last_run_debug.log"
            with (
                patch("app.DEBUG_LOG_PATH", log_path),
                patch.dict(os.environ, {"DEEPSEEK_API_KEY": "sk-secret"}, clear=False),
            ):
                write_debug_log("failure near sk-secret token")

            content = log_path.read_text(encoding="utf-8")

        self.assertNotIn("sk-secret", content)
        self.assertIn("[REDACTED]", content)


class RunCrewTests(unittest.TestCase):
    def test_run_crew_forces_dmn_mode_and_disables_shell(self) -> None:
        captured_kwargs: dict = {}

        def fake_run(command, **kwargs):
            captured_kwargs.update(kwargs)
            captured_kwargs["command"] = command
            return subprocess.CompletedProcess(
                args=command, returncode=0, stdout="ok", stderr=""
            )

        with patch("app.subprocess.run", side_effect=fake_run):
            result = run_crew("gaming laptop under $1000", timeout=5)

        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertEqual(captured_kwargs["shell"], False)
        self.assertEqual(captured_kwargs["env"]["CREWAI_DMN"], "1")
        self.assertEqual(captured_kwargs["timeout"], 5)

    def test_run_crew_reports_a_timeout_without_raising(self) -> None:
        def fake_run(command, **kwargs):
            raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs["timeout"])

        with patch("app.subprocess.run", side_effect=fake_run):
            result = run_crew("gaming laptop under $1000", timeout=1)

        self.assertTrue(result.timed_out)
        self.assertIsNone(result.returncode)


class RenderResultOutputPathTests(unittest.TestCase):
    """Cover the pure file-existence branches without a real Streamlit session."""

    def test_success_path_requires_markdown_report_to_exist(self) -> None:
        with TemporaryDirectory() as directory:
            missing_markdown_path = Path(directory) / "outputs" / "report.md"
            debug_log_path = Path(directory) / "outputs" / "last_run_debug.log"
            result = CrewRunResult(returncode=0, stdout="", stderr="", timed_out=False)

            with (
                patch("app.MARKDOWN_REPORT_PATH", missing_markdown_path),
                patch("app.DEBUG_LOG_PATH", debug_log_path),
                patch("app.st") as mock_st,
            ):
                render_result(result, timeout=600)

            mock_st.error.assert_called_once()
            mock_st.success.assert_not_called()
            self.assertTrue(debug_log_path.exists())


if __name__ == "__main__":
    unittest.main()

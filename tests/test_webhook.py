"""Unit tests for webhook notification service."""

import asyncio
import json
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from pydantic import ValidationError

from src.models import (
    ClassificationResult,
    ContentAnalysis,
    ContentArtifact,
    ContentBlock,
    ContentItem,
    ProcessingResult,
    SourceType,
    WebhookConfig,
)
from src.services.webhook import (
    WebhookNotifier,
    WebhookDeliveryResult,
    WebhookDeliveryStatus,
    _format_markdown_for_webhook,
    _prepare_variables_for_body,
    _render,
    _truncate,
    _isjson,
    _extract_headers,
    redact_headers,
    redact_url,
)
from src.ai.summarizer import DailySummarizer

_TEST_URL_ENV = "TEST_WEBHOOK_URL"
_TEST_URL = "https://example.com/webhook"


# ── Template variable replacement ──


class TestRender:
    def test_simple_replacement(self):
        template = "Hello #{name}, today is #{date}"
        variables = {"name": "Horizon", "date": "2026-04-24"}
        assert _render(template, variables) == "Hello Horizon, today is 2026-04-24"

    def test_no_matching_vars(self):
        template = "Hello #{unknown}"
        variables = {"name": "Horizon"}
        assert _render(template, variables) == "Hello #{unknown}"

    def test_empty_template(self):
        assert _render("", {"date": "2026-04-24"}) == ""

    def test_empty_vars(self):
        assert _render("Hello #{name}", {}) == "Hello #{name}"

    def test_numeric_values(self):
        template = "#{item_count} items, #{timestamp} seconds"
        variables = {"item_count": 15, "timestamp": 1745500000}
        assert _render(template, variables) == "15 items, 1745500000 seconds"

    def test_summary_with_multiline_content(self):
        template = '{"text": "#{summary}"}'
        summary = "## Title\n\nLine 1\nLine 2"
        variables = {"summary": summary}
        result = _render(template, variables)
        assert summary in result


class TestRenderDictAndList:
    def test_simple_dict(self):
        obj = {"title": "Horizon #{date}", "count": "#{item_count} items"}
        variables = {"date": "2026-04-24", "item_count": 15}
        result = _render(obj, variables)
        assert result == {"title": "Horizon 2026-04-24", "count": "15 items"}

    def test_nested_dict(self):
        obj = {
            "msg_type": "interactive",
            "card": {
                "schema": "2.0",
                "header": {"title": "Horizon #{date}"},
                "body": {"elements": [{"tag": "markdown", "content": "#{summary}"}]},
            },
        }
        variables = {"date": "2026-04-24", "summary": "## AI News\nLine 1"}
        result = _render(obj, variables)
        assert result["card"]["header"]["title"] == "Horizon 2026-04-24"
        assert result["card"]["body"]["elements"][0]["content"] == "## AI News\nLine 1"

    def test_list(self):
        obj = ["#{date}", "#{result}", "static"]
        variables = {"date": "2026-04-24", "result": "success"}
        result = _render(obj, variables)
        assert result == ["2026-04-24", "success", "static"]

    def test_non_string_values_preserved(self):
        obj = {"count": 10, "flag": True, "extra": None, "text": "#{date}"}
        variables = {"date": "2026-04-24"}
        result = _render(obj, variables)
        assert result["count"] == 10
        assert result["flag"] is True
        assert result["extra"] is None
        assert result["text"] == "2026-04-24"

    def test_no_matching_vars(self):
        obj = {"key": "#{unknown}"}
        result = _render(obj, {"name": "test"})
        assert result == {"key": "#{unknown}"}

    def test_summary_with_quotes_safely_replaced(self):
        """Verify that quotes in summary don't break the JSON structure."""
        obj = {"content": "#{summary}"}
        summary = 'AI called "GPT-5" is great'
        result = _render(obj, {"summary": summary})
        # When serialized to JSON, the quotes should be properly escaped
        serialized = json.dumps(result)
        parsed_back = json.loads(serialized)
        assert parsed_back["content"] == summary


class TestTruncate:
    def test_short_value_not_truncated(self):
        value = "hello"
        result = _truncate(value, limit=100, split="---")
        assert result == value

    def test_truncate_by_segments(self):
        # "aaa---bbb---ccc" → segments: "aaa"(3), "bbb"(3+3=6), "ccc"(3+3=6)
        # limit=10 → keep "aaa"(3) + "bbb"(6) = 9 ≤ 10, drop "ccc"
        value = "aaa---bbb---ccc"
        result = _truncate(value, limit=10, split="---")
        assert result == "aaa---bbb"

    def test_single_segment_exceeds_limit_still_kept(self):
        # First segment alone exceeds limit, but we always keep it
        value = "abcdefghij---xyz"
        result = _truncate(value, limit=5, split="---")
        assert result == "abcdefghij"
        assert "xyz" not in result

    def test_no_split_delimiter_in_value(self):
        # Value doesn't contain the split delimiter — returned as-is
        value = "abcdefghij"
        result = _truncate(value, limit=5, split="---")
        # Without delimiter, entire value is one segment, always kept
        assert result == value

    def test_empty_value(self):
        result = _truncate("", limit=10, split="---")
        assert result == ""

    def test_exact_limit_with_join(self):
        # "aaa---bbb" → seg1=3, seg2=3+3(join)=6, total=9
        # limit=9 → exact fit, keep both
        value = "aaa---bbb"
        result = _truncate(value, limit=9, split="---")
        assert result == value

    def test_one_char_over_limit(self):
        # "aaa---bbb" → total=9 chars, limit=8 → drop "bbb"
        value = "aaa---bbb"
        result = _truncate(value, limit=8, split="---")
        assert result == "aaa"


class TestRenderParameterized:
    def test_plain_key_without_params(self):
        """#{summary} without params works as before."""
        template = "#{summary}"
        result = _render(template, {"summary": "hello world"})
        assert result == "hello world"

    def test_key_with_limit_and_split(self):
        """#{summary?limit=10&split=---} truncates by character count."""
        # "aaa---bbb---ccc" → keep "aaa---bbb" (9 chars ≤ 10), drop "ccc"
        summary = "aaa---bbb---ccc"
        template = "#{summary?limit=10&split=---}"
        result = _render(template, {"summary": summary})
        assert result == "aaa---bbb"

    def test_key_with_limit_no_truncation_needed(self):
        """When value fits within limit, no truncation occurs."""
        summary = "short text"
        template = "#{summary?limit=100&split=---}"
        result = _render(template, {"summary": summary})
        assert result == summary

    def test_missing_variable_with_params(self):
        """#{unknown?limit=5&split=---} with missing key leaves placeholder."""
        template = "#{unknown?limit=5&split=---}"
        result = _render(template, {"date": "2026-04-24"})
        assert result == "#{unknown?limit=5&split=---}"

    def test_param_in_dict_body(self):
        """#{summary?limit=10&split=---} works inside dict request_body."""
        obj = {"content": "#{summary?limit=10&split=---}", "title": "#{date}"}
        summary = "aaa---bbb---ccc"
        result = _render(obj, {"summary": summary, "date": "2026-04-24"})
        assert result["title"] == "2026-04-24"
        assert result["content"] == "aaa---bbb"

    def test_mix_of_plain_and_parameterized(self):
        """Plain #{date} and parameterized #{summary?...} in same template."""
        template = "#{date}: #{summary?limit=20&split=---}"
        summary = "aaa---bbb---ccc"
        result = _render(template, {"date": "2026-04-24", "summary": summary})
        assert result == "2026-04-24: aaa---bbb---ccc"


class TestWebhookMarkdownFormatting:
    def test_details_references_are_flattened_for_webhook(self):
        summary = """## Item

<a id="item-1"></a>
<details><summary>参考链接</summary>
<ul>
<li><a href="https://example.com/a">Example A</a></li>
<li><a href="https://example.com/b">Example B</a></li>
</ul>
</details>
"""

        result = _format_markdown_for_webhook(summary)

        assert "<details>" not in result
        assert "<summary>" not in result
        assert '<a id="item-1"></a>' not in result
        assert "**参考链接**" in result
        assert "- [Example A](https://example.com/a)" in result
        assert "- [Example B](https://example.com/b)" in result

    def test_details_references_with_unsafe_href_remain_plain_text(self):
        summary = """## Item

<details><summary>References</summary>
<ul>
<li><a href="javascript:alert(1)">click [me](https://evil.example)</a></li>
</ul>
</details>
"""

        result = _format_markdown_for_webhook(summary)

        assert "javascript:alert(1)" not in result
        assert "[click](javascript:alert(1))" not in result
        assert "- click \\[me\\]\\(https://evil.example\\)" in result

    def test_details_references_with_malformed_http_href_remain_plain_text(self):
        summary = """## Item

<details><summary>References</summary>
<ul>
<li><a href="https://safe.example/) [bad](javascript:alert(1))">click</a></li>
</ul>
</details>
"""

        result = _format_markdown_for_webhook(summary)

        assert "javascript:alert(1)" not in result
        assert "[click](https://safe.example/)" not in result
        assert "- click" in result

    def test_details_references_allow_balanced_parentheses_in_href(self):
        summary = """## Item

<details><summary>References</summary>
<ul>
<li><a href="https://en.wikipedia.org/wiki/Colossus_(supercomputer)">Colossus</a></li>
</ul>
</details>
"""

        result = _format_markdown_for_webhook(summary)

        assert (
            "- [Colossus](https://en.wikipedia.org/wiki/Colossus_(supercomputer))"
            in result
        )

    def test_prepare_variables_changes_summary_for_any_post_body(self):
        summary = "<details><summary>References</summary><ul><li>Plain item</li></ul></details>"
        variables = {"summary": summary, "date": "2026-04-24"}
        body = {"text": "#{summary}"}

        result = _prepare_variables_for_body(body, variables)

        assert result is not variables
        assert result["summary"] == "**References**\n\n- Plain item"
        assert variables["summary"] == summary

    def test_prepare_variables_keeps_summary_unchanged_without_body(self):
        summary = "<details><summary>References</summary><ul><li>Plain item</li></ul></details>"
        variables = {"summary": summary}

        result = _prepare_variables_for_body(None, variables)

        assert result is variables
        assert result["summary"] == summary


class TestWebhookPreview:
    def test_build_preview_uses_same_summary_formatting_as_send_path(self):
        os.environ[_TEST_URL_ENV] = _TEST_URL
        config = WebhookConfig(
            enabled=True,
            url_env=_TEST_URL_ENV,
            request_body={
                "msg_type": "interactive",
                "card": {
                    "body": {
                        "elements": [{"tag": "markdown", "content": "#{summary}"}]
                    },
                },
            },
        )
        notifier = WebhookNotifier(config)

        preview = notifier.build_preview(
            {
                "summary": '<details><summary>References</summary><ul><li><a href="https://example.com">Example</a></li></ul></details>',
            }
        )

        assert preview["url"] == _TEST_URL
        assert "**References**" in preview["body"]
        assert "<details>" not in preview["body"]
        del os.environ[_TEST_URL_ENV]

    def test_build_preview_uses_request_body_override(self):
        os.environ[_TEST_URL_ENV] = "https://example.com/webhook?token=secret"
        config = WebhookConfig(
            enabled=True,
            url_env=_TEST_URL_ENV,
            request_body={"content": "configured"},
            headers="Authorization: Bearer secret\nX-Trace: ok",
        )
        notifier = WebhookNotifier(config)

        preview = notifier.build_preview(
            {
                "_request_body_override": {"content": "override"},
            }
        )

        parsed = json.loads(preview["body"])
        assert parsed["content"] == "override"
        assert preview["url"] == _TEST_URL
        assert preview["headers"]["Authorization"] == "<redacted>"
        assert preview["headers"]["X-Trace"] == "ok"
        assert preview["headers"]["Content-Type"] == "application/json"
        del os.environ[_TEST_URL_ENV]


# ── JSON prefix detection ──


class TestIsJson:
    def test_object(self):
        assert _isjson('{"key": "value"}') is True

    def test_array(self):
        assert _isjson("[1, 2, 3]") is True

    def test_whitespace_before_brace(self):
        assert _isjson('  {"key": 1}') is True

    def test_plain_string(self):
        assert _isjson("hello world") is False

    def test_form_data(self):
        assert _isjson("key=value&foo=bar") is False

    def test_empty(self):
        assert _isjson("") is False


# ── Header parsing ──


class TestExtractHeaders:
    def test_single_header(self):
        assert _extract_headers("Content-Type: application/json") == {
            "Content-Type": "application/json"
        }

    def test_multiple_headers(self):
        result = _extract_headers("Authorization: Bearer abc\nX-Custom: value")
        assert result == {"Authorization": "Bearer abc", "X-Custom": "value"}

    def test_empty_string(self):
        assert _extract_headers("") == {}

    def test_none(self):
        assert _extract_headers(None) == {}

    def test_blank_lines(self):
        result = _extract_headers("Key: val\n\nAnother: val2")
        assert result == {"Key": "val", "Another": "val2"}

    def test_invalid_line(self):
        result = _extract_headers("NoColonHere\nValid: yes")
        assert result == {"Valid": "yes"}


class TestWebhookRedaction:
    def test_redact_url_removes_query_and_fragment(self):
        assert (
            redact_url("https://example.com/hook?token=secret#frag")
            == "https://example.com/hook"
        )

    def test_redact_headers_masks_sensitive_values(self):
        assert redact_headers({"Authorization": "Bearer secret", "X-Trace": "ok"}) == {
            "Authorization": "<redacted>",
            "X-Trace": "ok",
        }


# ── WebhookNotifier ──


def _run_async(coro):
    """Helper to run async coroutine in tests."""
    return asyncio.run(coro)


class TestWebhookNotifier:
    def test_disabled_skips(self):
        config = WebhookConfig(enabled=False, url_env=_TEST_URL_ENV)
        os.environ[_TEST_URL_ENV] = _TEST_URL
        notifier = WebhookNotifier(config)
        assert notifier.config.enabled is False
        del os.environ[_TEST_URL_ENV]

    def test_disabled_webhook_skips_notification(self):
        os.environ[_TEST_URL_ENV] = _TEST_URL
        config = WebhookConfig(enabled=False, url_env=_TEST_URL_ENV)
        notifier = WebhookNotifier(config)
        with patch("httpx.AsyncClient") as mock_client:
            result = _run_async(notifier.notify({"date": "2026-04-24"}))
            mock_client.assert_not_called()
            assert result.status == WebhookDeliveryStatus.DISABLED
            assert result.sent is False
        del os.environ[_TEST_URL_ENV]

    def test_empty_url_env_skips_notification(self):
        # url_env not set in environment
        config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
        notifier = WebhookNotifier(config)
        assert notifier.url is None
        with patch("httpx.AsyncClient") as mock_client:
            result = _run_async(notifier.notify({"date": "2026-04-24"}))
            mock_client.assert_not_called()
            assert result.status == WebhookDeliveryStatus.SKIPPED
            assert result.sent is False

    def test_get_request_when_no_body(self):
        os.environ[_TEST_URL_ENV] = "https://example.com/webhook?date=#{date}"
        config = WebhookConfig(
            enabled=True,
            url_env=_TEST_URL_ENV,
        )
        notifier = WebhookNotifier(config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            _run_async(notifier.notify({"date": "2026-04-24", "result": "success"}))
            mock_client.get.assert_called_once()
            call_url = mock_client.get.call_args[0][0]
            assert "2026-04-24" in call_url
        del os.environ[_TEST_URL_ENV]

    def test_post_request_with_json_body(self):
        os.environ[_TEST_URL_ENV] = _TEST_URL
        config = WebhookConfig(
            enabled=True,
            url_env=_TEST_URL_ENV,
            request_body='{"msg_type": "post", "content": "Horizon #{date} #{item_count} items"}',
        )
        notifier = WebhookNotifier(config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            _run_async(notifier.notify({"date": "2026-04-24", "item_count": 15}))
            mock_client.post.assert_called_once()

            call_kwargs = mock_client.post.call_args[1]
            assert call_kwargs["headers"]["Content-Type"] == "application/json"

            body_bytes = call_kwargs["content"]
            body_str = body_bytes.decode("utf-8")
            parsed = json.loads(body_str)
            assert parsed["content"] == "Horizon 2026-04-24 15 items"
        del os.environ[_TEST_URL_ENV]

    def test_post_request_with_json_str_body_containing_summary(self):
        """String JSON body with #{summary} that contains special characters.

        Note: when request_body is a string, #{summary} is replaced via
        simple string substitution. If #{summary} contains unescaped quotes
        or newlines, the resulting JSON string may become invalid. This test
        documents that known limitation — use dict request_body for safe
        handling of #{summary}.
        """
        os.environ[_TEST_URL_ENV] = _TEST_URL
        config = WebhookConfig(
            enabled=True,
            url_env=_TEST_URL_ENV,
            request_body='{"msg_type": "post", "content": "#{summary}"}',
        )
        notifier = WebhookNotifier(config)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            # summary without special chars — should parse fine
            summary = "Horizon daily report: 10 items"
            _run_async(notifier.notify({"summary": summary}))
            mock_client.post.assert_called_once()

            call_kwargs = mock_client.post.call_args[1]
            body_str = call_kwargs["content"].decode("utf-8")
            parsed = json.loads(bod…7810 tokens truncated…xample.com/webhook"
        config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
        notifier = WebhookNotifier(config)
        assert notifier.url == "https://example.com/webhook"
        del os.environ[_TEST_URL_ENV]

    def test_valid_http_url_passes(self):
        os.environ[_TEST_URL_ENV] = "http://example.com:8080/hook"
        config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
        notifier = WebhookNotifier(config)
        assert notifier.url == "http://example.com:8080/hook"
        del os.environ[_TEST_URL_ENV]

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost/hook",
            "http://api.localhost/hook",
            "https://user:password@example.com/hook",
        ],
    )
    def test_unsafe_url_raises_value_error(self, url):
        os.environ[_TEST_URL_ENV] = url
        config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
        try:
            with pytest.raises(ValueError):
                WebhookNotifier(config)
        finally:
            del os.environ[_TEST_URL_ENV]

    def test_no_hostname_raises_value_error(self):
        """URLs without a hostname raise ValueError."""
        os.environ[_TEST_URL_ENV] = "http://"
        config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
        with pytest.raises(ValueError, match="no hostname"):
            WebhookNotifier(config)
        del os.environ[_TEST_URL_ENV]

    def test_wrong_scheme_raises_value_error(self):
        """URLs with non-http/https scheme raise ValueError."""
        for bad_url in ["ftp://example.com", "not-a-url", "://"]:
            os.environ[_TEST_URL_ENV] = bad_url
            config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
            try:
                with pytest.raises(ValueError, match="http or https"):
                    WebhookNotifier(config)
            finally:
                del os.environ[_TEST_URL_ENV]

    def test_invalid_port_raises_value_error(self):
        """httpx.URL catches structurally invalid ports like 'abc'."""
        os.environ[_TEST_URL_ENV] = "http://example.com:abc"
        config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
        with pytest.raises(ValueError, match="structurally invalid"):
            WebhookNotifier(config)
        del os.environ[_TEST_URL_ENV]

    def test_empty_env_var_value_raises_value_error(self):
        """Env var exists but is empty string → ValueError."""
        os.environ[_TEST_URL_ENV] = ""
        config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
        with pytest.raises(ValueError, match="empty"):
            WebhookNotifier(config)
        del os.environ[_TEST_URL_ENV]

    def test_env_var_not_set_sets_url_none(self):
        """url_env configured but env var doesn't exist → url=None + console warning."""
        config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
        os.environ.pop(_TEST_URL_ENV, None)
        notifier = WebhookNotifier(config)
        assert notifier.url is None

    def test_url_env_null_sets_url_none(self):
        """url_env=None in config → url=None + console warning."""
        config = WebhookConfig(enabled=True, url_env=None)
        notifier = WebhookNotifier(config)
        assert notifier.url is None

    def test_whitespace_url_stripped_and_validated(self):
        """URL with surrounding whitespace is stripped before validation."""
        os.environ[_TEST_URL_ENV] = "  https://example.com/webhook  "
        config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
        notifier = WebhookNotifier(config)
        assert notifier.url == "https://example.com/webhook"
        del os.environ[_TEST_URL_ENV]

    def test_shell_escape_artifacts_stripped(self):
        """Shell escape artifacts like \\? and \\= are auto-stripped from URL."""
        os.environ[_TEST_URL_ENV] = "https://oapi.dingtalk.com/robot/send\\?access_token\\=abc123"
        config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
        notifier = WebhookNotifier(config)
        assert notifier.url == "https://oapi.dingtalk.com/robot/send?access_token=abc123"
        del os.environ[_TEST_URL_ENV]


# ── HTTP status code handling ──


class TestHTTPStatusHandling:
    def _make_notifier(self):
        os.environ[_TEST_URL_ENV] = _TEST_URL
        config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
        notifier = WebhookNotifier(config)
        return notifier

    def _cleanup(self):
        del os.environ[_TEST_URL_ENV]

    def test_2xx_success_prints_response(self):
        notifier = self._make_notifier()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"code":0,"msg":"ok"}'

        mock_console = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            notifier.console = mock_console
            result = _run_async(notifier.notify({"date": "2026-04-24"}))

            printed = " ".join(str(c) for c in mock_console.print.call_args_list)
            assert "status=200" in printed
            assert '"code":0' not in printed
            # Success response should be green, not yellow
            assert "[green]" in printed
            assert result.status == WebhookDeliveryStatus.SUCCESS
            assert result.sent is True
            assert result.status_code == 200
        self._cleanup()

    def test_2xx_feishu_error_code_prints_yellow_warning(self):
        """Feishu returns HTTP 200 with code=19001 in body — should be yellow warning."""
        notifier = self._make_notifier()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"code":19001,"msg":"param invalid: incoming webhook access token invalid"}'

        mock_console = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            notifier.console = mock_console
            result = _run_async(notifier.notify({"date": "2026-04-24"}))

            printed = " ".join(str(c) for c in mock_console.print.call_args_list)
            assert "19001" in printed
            assert "Feishu/Lark" in printed
            assert "[yellow]" in printed
            assert result.status == WebhookDeliveryStatus.PLATFORM_FAILURE
            assert result.sent is False
            assert result.status_code == 200
        self._cleanup()

    def test_2xx_dingtalk_error_code_prints_yellow_warning(self):
        """DingTalk returns HTTP 200 with errcode=400 in body — should be yellow warning."""
        notifier = self._make_notifier()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"errcode":400,"errmsg":"invalid token"}'

        mock_console = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            notifier.console = mock_console
            result = _run_async(notifier.notify({"date": "2026-04-24"}))

            printed = " ".join(str(c) for c in mock_console.print.call_args_list)
            assert "errcode=400" in printed
            assert "DingTalk" in printed
            assert "[yellow]" in printed
        self._cleanup()

    def test_2xx_slack_ok_false_prints_yellow_warning(self):
        """Slack returns HTTP 200 with ok=false — should be yellow warning."""
        notifier = self._make_notifier()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"ok":false,"error":"invalid_token"}'

        mock_console = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            notifier.console = mock_console
            _run_async(notifier.notify({"date": "2026-04-24"}))

            printed = " ".join(str(c) for c in mock_console.print.call_args_list)
            assert "Slack/Discord" in printed
            assert "[yellow]" in printed
        self._cleanup()

    def test_2xx_non_json_body_prints_green(self):
        """Non-JSON 2xx response body prints as green (no error code check possible)."""
        notifier = self._make_notifier()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"

        mock_console = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            notifier.console = mock_console
            _run_async(notifier.notify({"date": "2026-04-24"}))

            printed = " ".join(str(c) for c in mock_console.print.call_args_list)
            assert "status=200" in printed
            assert "[green]" in printed
        self._cleanup()

    def test_3xx_redirect_prints_warning(self):
        notifier = self._make_notifier()
        mock_response = MagicMock()
        mock_response.status_code = 301
        mock_response.text = ""
        mock_response.headers = {"location": "https://new-url.com"}

        mock_console = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            notifier.console = mock_console
            _run_async(notifier.notify({"date": "2026-04-24"}))

            printed = " ".join(str(c) for c in mock_console.print.call_args_list)
            assert "redirect" in printed.lower()
        self._cleanup()

    def test_4xx_client_error_prints_warning(self):
        notifier = self._make_notifier()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"

        mock_console = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            notifier.console = mock_console
            result = _run_async(notifier.notify({"date": "2026-04-24"}))

            printed = " ".join(str(c) for c in mock_console.print.call_args_list)
            assert "client error" in printed.lower()
            assert result.status == WebhookDeliveryStatus.HTTP_FAILURE
            assert result.status_code == 400
        self._cleanup()

    def test_5xx_server_error_prints_warning(self):
        notifier = self._make_notifier()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal server error"

        mock_console = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            notifier.console = mock_console
            result = _run_async(notifier.notify({"date": "2026-04-24"}))

            printed = " ".join(str(c) for c in mock_console.print.call_args_list)
            assert "server error" in printed.lower()
            assert result.status == WebhookDeliveryStatus.HTTP_FAILURE
            assert result.status_code == 500
        self._cleanup()


# ── Exception classification ──


class TestExceptionClassification:
    def _make_notifier(self):
        os.environ[_TEST_URL_ENV] = _TEST_URL
        config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
        notifier = WebhookNotifier(config)
        return notifier

    def _cleanup(self):
        del os.environ[_TEST_URL_ENV]

    def test_connect_error_prints_warning(self):
        notifier = self._make_notifier()
        mock_console = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            notifier.console = mock_console
            result = _run_async(notifier.notify({"date": "2026-04-24"}))

            printed = " ".join(str(c) for c in mock_console.print.call_args_list)
            assert "connection failed" in printed.lower()
            assert result.status == WebhookDeliveryStatus.NETWORK_FAILURE
            assert result.error_type == "connect"
        self._cleanup()

    def test_timeout_exception_prints_warning(self):
        notifier = self._make_notifier()
        mock_console = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timed out"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            notifier.console = mock_console
            result = _run_async(notifier.notify({"date": "2026-04-24"}))

            printed = " ".join(str(c) for c in mock_console.print.call_args_list)
            assert "timed out" in printed.lower()
            assert result.status == WebhookDeliveryStatus.NETWORK_FAILURE
            assert result.error_type == "timeout"
        self._cleanup()

    def test_invalid_url_exception_prints_warning(self):
        notifier = self._make_notifier()
        mock_console = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.InvalidURL("Bad URL"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            notifier.console = mock_console
            _run_async(notifier.notify({"date": "2026-04-24"}))

            printed = " ".join(str(c) for c in mock_console.print.call_args_list)
            assert "invalid" in printed.lower()
        self._cleanup()

    def test_generic_exception_prints_type_name(self):
        notifier = self._make_notifier()
        mock_console = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=RuntimeError("Something unexpected"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            notifier.console = mock_console
            _run_async(notifier.notify({"date": "2026-04-24"}))

            printed = " ".join(str(c) for c in mock_console.print.call_args_list)
            assert "RuntimeError" in printed
            assert "unexpectedly" in printed.lower()
        self._cleanup()


# ── Config field validation ──


class TestWebhookConfigFieldValidation:
    def test_invalid_delivery_raises_validation_error(self):
        with pytest.raises(ValidationError, match="delivery"):
            WebhookConfig(enabled=True, delivery="invalid_mode")

    def test_invalid_platform_raises_validation_error(self):
        with pytest.raises(ValidationError, match="platform"):
            WebhookConfig(enabled=True, platform="unknown_platform")

    def test_invalid_layout_raises_validation_error(self):
        with pytest.raises(ValidationError, match="layout"):
            WebhookConfig(enabled=True, layout="html")

    def test_invalid_fallback_layout_raises_validation_error(self):
        with pytest.raises(ValidationError, match="fallback_layout"):
            WebhookConfig(enabled=True, fallback_layout="html")

    def test_invalid_overview_position_raises_validation_error(self):
        with pytest.raises(ValidationError, match="overview_position"):
            WebhookConfig(enabled=True, overview_position="middle")

    def test_all_valid_values_pass(self):
        config = WebhookConfig(
            enabled=True,
            delivery="summary_and_items",
            platform="feishu",
            layout="collapsible",
            fallback_layout="markdown",
            overview_position="last",
        )
        assert config.delivery == "summary_and_items"
        assert config.platform == "feishu"
        assert config.layout == "collapsible"
        assert config.fallback_layout == "markdown"
        assert config.overview_position == "last"

    def test_each_valid_platform(self):
        for p in ["generic", "feishu", "lark", "dingtalk", "slack", "discord"]:
            config = WebhookConfig(enabled=True, platform=p)
            assert config.platform == p


# ── Skip console output ──


class TestSkipConsoleOutput:
    def test_disabled_webhook_prints_warning(self):
        """When webhook is disabled, notify() prints a yellow warning."""
        os.environ[_TEST_URL_ENV] = _TEST_URL
        config = WebhookConfig(enabled=False, url_env=_TEST_URL_ENV)
        notifier = WebhookNotifier(config)
        mock_console = MagicMock()
        notifier.console = mock_console

        _run_async(notifier.notify({"date": "2026-04-24"}))

        mock_console.print.assert_called_once()
        printed = str(mock_console.print.call_args)
        assert "disabled" in printed.lower()
        del os.environ[_TEST_URL_ENV]

    def test_empty_url_prints_warning(self):
        """When URL is empty (env var not set), notify() prints a yellow warning."""
        config = WebhookConfig(enabled=True, url_env=_TEST_URL_ENV)
        os.environ.pop(_TEST_URL_ENV, None)
        notifier = WebhookNotifier(config)
        mock_console = MagicMock()
        notifier.console = mock_console

        _run_async(notifier.notify({"date": "2026-04-24"}))

        # notify() prints warning when URL is empty
        assert mock_console.print.call_count >= 1
        printed = " ".join(str(c) for c in mock_console.print.call_args_list)
        assert "not set" in printed.lower() or "empty" in printed.lower()

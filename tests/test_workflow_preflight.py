from pathlib import Path


def test_preflight_workflow_strips_paid_and_delivery_secrets() -> None:
    workflow = Path(".github/workflows/ai-fde-radar.yml").read_text(encoding="utf-8")

    guard = "unset DEEPSEEK_API_KEY HORIZON_WEBHOOK_URL"
    invocation = "args+=(--preflight-only --dry-run)"
    assert guard in workflow
    assert invocation in workflow
    assert workflow.index(guard) < workflow.index(invocation)


def test_required_column_exit_code_is_not_retried() -> None:
    workflow = Path(".github/workflows/ai-fde-radar.yml").read_text(encoding="utf-8")

    assert 'if [[ "$status" == "2" ]]' in workflow
    assert "non-retryable required-column failure" in workflow
    assert workflow.index('if [[ "$status" == "2" ]]') < workflow.index(
        'if [[ "$attempt" == "1" ]]'
    )

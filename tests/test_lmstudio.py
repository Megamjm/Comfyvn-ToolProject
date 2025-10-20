import os

import pytest

from comfyvn.lmstudio_client import healthcheck


@pytest.mark.skipif(
    not os.getenv("LMSTUDIO_URL"),
    reason="LM Studio URL not configured in environment",
)
def test_lmstudio_health() -> None:
    status = healthcheck()
    assert status["ok"]
    assert isinstance(status.get("models"), list)

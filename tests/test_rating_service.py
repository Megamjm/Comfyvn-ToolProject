from __future__ import annotations

from pathlib import Path

from comfyvn.rating.classifier_stub import RatingService, RatingStore


def _service(tmp_path: Path) -> RatingService:
    store_path = tmp_path / "overrides.json"
    return RatingService(store=RatingStore(store_path))


def test_classifier_defaults_to_conservative_teen(tmp_path):
    service = _service(tmp_path)
    result = service.classify("scene:demo", {"text": "A calm picnic in the park."})
    assert result.rating == "T"
    assert result.nsfw is False
    assert "fallback" in result.reasons[0]


def test_adult_payload_requires_ack_and_persists(tmp_path):
    service = _service(tmp_path)
    gate = service.evaluate(
        "prompt:test",
        {"text": "Explicit adult content with nudity."},
        mode="sfw",
        action="unit.test",
    )
    assert gate["requires_ack"] is True
    assert gate["allowed"] is False
    token = gate["ack_token"]
    assert token

    ack_entry = service.acknowledge(token, "qa")
    assert ack_entry["token"] == token
    assert ack_entry["user"] == "qa"

    gate_after = service.evaluate(
        "prompt:test",
        {"text": "Explicit adult content with nudity."},
        mode="sfw",
        acknowledged=True,
        ack_token=token,
        action="unit.test",
    )
    assert gate_after["allowed"] is True
    assert gate_after["ack_status"] == "verified"


def test_override_short_circuits_classifier(tmp_path):
    service = _service(tmp_path)
    override = service.put_override(
        "export:demo",
        "E",
        "reviewer",
        "educational content",
        scope="export",
    )
    assert override.rating == "E"
    result = service.classify("export:demo", {"text": "Explicit adult content."})
    assert result.rating == "E"
    assert result.source == "override"
    assert result.reviewer == "reviewer"

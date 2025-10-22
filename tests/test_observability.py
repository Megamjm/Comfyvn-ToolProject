from __future__ import annotations

from importlib import reload


def _reload_anonymize(monkeypatch, tmp_path):
    monkeypatch.setenv("COMFYVN_RUNTIME_ROOT", str(tmp_path))
    import comfyvn.obs.anonymize as anonymize

    return reload(anonymize)


def _reload_telemetry(monkeypatch, tmp_path):
    monkeypatch.setenv("COMFYVN_RUNTIME_ROOT", str(tmp_path))
    import comfyvn.obs.telemetry as telemetry

    return reload(telemetry)


def test_hash_identifier_stable(monkeypatch, tmp_path):
    anonymize = _reload_anonymize(monkeypatch, tmp_path)
    digest_a = anonymize.hash_identifier("hello-world")
    digest_b = anonymize.hash_identifier("hello-world")
    digest_c = anonymize.hash_identifier("hello-world", namespace="alt")

    assert digest_a == digest_b
    assert digest_a != digest_c

    payload = {"user_id": "secret-user", "scene": "intro"}
    scrubbed = anonymize.anonymize_payload(payload)
    assert scrubbed["user_id"] != "secret-user"
    assert scrubbed["scene"] == "intro"


def test_telemetry_respects_feature_flags(monkeypatch, tmp_path):
    telemetry = _reload_telemetry(monkeypatch, tmp_path)

    import comfyvn.config.feature_flags as feature_flags

    def _flag_router(name: str, **_: object) -> bool:
        return name in {
            telemetry.TELEMETRY_FEATURE_FLAG,
            telemetry.CRASH_UPLOADS_FEATURE_FLAG,
        }

    monkeypatch.setattr(feature_flags, "is_enabled", _flag_router)

    store = telemetry.TelemetryStore(app_version="test")
    store.update_settings(
        telemetry_opt_in=True, crash_opt_in=True, diagnostics_opt_in=True
    )

    assert store.telemetry_allowed()
    assert store.record_feature("modder-hook")
    assert store.record_event("custom-event", {"hook_id": "abc123"})

    bundle = store.export_bundle()
    assert bundle.exists()

    # Disable telemetry feature flag; recordings should now be ignored.
    monkeypatch.setattr(feature_flags, "is_enabled", lambda name, **_: False)
    assert store.telemetry_allowed() is False
    assert store.record_feature("modder-hook") is False

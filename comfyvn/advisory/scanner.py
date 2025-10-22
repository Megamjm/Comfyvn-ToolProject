"""High-level advisory scanner facade with extensible plugin heuristics."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from comfyvn.core.advisory import AdvisoryIssue, log_issue

LOGGER = logging.getLogger("comfyvn.advisory.scanner")

if TYPE_CHECKING:  # pragma: no cover - type checking helper
    from comfyvn.core.advisory_hooks import BundleContext

BundleDict = Mapping[str, Any]
ScannerHook = Callable[
    ["BundleContext"], Iterable[Union[AdvisoryIssue, Mapping[str, Any]]]
]
ClassifierHook = Callable[["BundleContext"], Iterable[Mapping[str, Any]]]


@dataclass
class RegisteredPlugin:
    name: str
    handler: ScannerHook
    optional: bool = False


_PLUGINS: list[RegisteredPlugin] = []
_NSF_CLASSIFIER: Optional[ClassifierHook] = None


def register_scanner_plugin(
    name: str,
    handler: ScannerHook,
    *,
    optional: bool = False,
    replace: bool = False,
) -> None:
    """Register a scanner plugin. Existing entry with the same name is replaced when requested."""

    existing = next((p for p in _PLUGINS if p.name == name), None)
    if existing:
        if not replace:
            LOGGER.debug("Scanner plugin %s already registered", name)
            return
        _PLUGINS.remove(existing)
    _PLUGINS.append(RegisteredPlugin(name=name, handler=handler, optional=optional))
    LOGGER.debug("Scanner plugin registered name=%s optional=%s", name, optional)


def iter_scanner_plugins() -> List[RegisteredPlugin]:
    return list(_PLUGINS)


def register_nsfw_classifier(hook: Optional[ClassifierHook]) -> None:
    """Register (or clear) the optional NSFW classifier hook."""

    global _NSF_CLASSIFIER
    _NSF_CLASSIFIER = hook
    if hook:
        LOGGER.info("NSFW classifier hook registered")
    else:
        LOGGER.info("NSFW classifier hook cleared")


def _as_path(value: Any) -> Path | None:
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value.strip():
        return Path(value).expanduser()
    return None


def _coerce_assets(payload: Any) -> Sequence[Tuple[str, Path | None]]:
    assets: List[Tuple[str, Path | None]] = []
    if isinstance(payload, Mapping):
        payload = payload.values()
    if not isinstance(payload, Iterable):
        return assets

    for entry in payload:
        rel: str | None = None
        source: Path | None = None
        if isinstance(entry, (tuple, list)) and entry:
            rel = str(entry[0])
            if len(entry) > 1:
                source = _as_path(entry[1])
        elif isinstance(entry, Mapping):
            rel = (
                entry.get("path")
                or entry.get("relpath")
                or entry.get("id")
                or entry.get("name")
            )
            source = _as_path(entry.get("source") or entry.get("absolute_path"))
        elif isinstance(entry, str):
            rel = entry
        if rel:
            assets.append((str(rel), source))
    return assets


def _coerce_mapping(payload: Any, key_field: str = "id") -> Dict[str, dict]:
    if isinstance(payload, Mapping):
        return {
            str(k): dict(v) if isinstance(v, Mapping) else v for k, v in payload.items()
        }  # type: ignore[arg-type]
    result: Dict[str, dict] = {}
    if not isinstance(payload, Iterable):
        return result
    for entry in payload:
        if not isinstance(entry, Mapping):
            continue
        key = entry.get(key_field) or entry.get("scene_id") or entry.get("name")
        if not key:
            continue
        result[str(key)] = dict(entry)
    return result


def _coerce_scene_sources(bundle: BundleDict) -> Dict[str, Path]:
    sources: Dict[str, Path] = {}
    raw_sources = bundle.get("scene_sources")
    if isinstance(raw_sources, Mapping):
        for key, value in raw_sources.items():
            path = _as_path(value)
            if path is not None:
                sources[str(key)] = path
    scenes = bundle.get("scenes")
    if isinstance(scenes, Iterable):
        for entry in scenes:
            if not isinstance(entry, Mapping):
                continue
            key = (
                entry.get("id")
                or entry.get("scene_id")
                or entry.get("name")
                or entry.get("label")
            )
            path = entry.get("path") or entry.get("source")
            if key and path and str(key) not in sources:
                candidate = _as_path(path)
                if candidate is not None:
                    sources[str(key)] = candidate
    return sources


def _bundle_context_from_dict(bundle: BundleDict) -> "BundleContext":
    from comfyvn.core.advisory_hooks import BundleContext  # local import to avoid cycle

    project_id = bundle.get("project_id") or bundle.get("project")
    timeline_id = bundle.get("timeline_id") or bundle.get("timeline")
    metadata = bundle.get("metadata")
    metadata_dict: Dict[str, Any] = {}
    if isinstance(metadata, Mapping):
        metadata_dict = dict(metadata)

    scenes = _coerce_mapping(bundle.get("scenes") or {}, key_field="id")
    characters = _coerce_mapping(bundle.get("characters") or {}, key_field="id")
    licenses = bundle.get("licenses")
    if isinstance(licenses, Sequence) and not isinstance(licenses, (str, bytes)):
        licenses_seq: Sequence[Any] = licenses
    elif isinstance(licenses, Iterable) and not isinstance(licenses, (str, bytes)):
        licenses_seq = list(licenses)
    else:
        licenses_seq = []

    assets = _coerce_assets(bundle.get("assets") or [])
    scene_sources = _coerce_scene_sources(bundle)

    return BundleContext(
        project_id=str(project_id) if project_id else None,
        timeline_id=str(timeline_id) if timeline_id else None,
        scenes=scenes,
        scene_sources=scene_sources,
        characters=characters,
        licenses=licenses_seq,  # type: ignore[arg-type]
        assets=assets,
        metadata=metadata_dict,
    )


def _context_target(context: "BundleContext", suffix: str) -> str:
    base = (
        f"project:{context.project_id}"
        if getattr(context, "project_id", None)
        else "project:unknown"
    )
    return f"{base}:{suffix}"


_SPDX_CANONICAL = {
    "APACHE-2.0": "Apache-2.0",
    "BSD-2-CLAUSE": "BSD-2-Clause",
    "BSD-3-CLAUSE": "BSD-3-Clause",
    "GPL-3.0": "GPL-3.0",
    "GPL-3.0-ONLY": "GPL-3.0-only",
    "GPL-3.0-OR-LATER": "GPL-3.0-or-later",
    "LGPL-3.0": "LGPL-3.0",
    "LGPL-2.1": "LGPL-2.1",
    "MIT": "MIT",
    "MPL-2.0": "MPL-2.0",
    "AGPL-3.0": "AGPL-3.0",
    "CC0-1.0": "CC0-1.0",
    "CC-BY-4.0": "CC-BY-4.0",
    "CC-BY-SA-4.0": "CC-BY-SA-4.0",
    "CC-BY-NC-4.0": "CC-BY-NC-4.0",
    "CC-BY-NC-SA-4.0": "CC-BY-NC-SA-4.0",
    "CC-BY-ND-4.0": "CC-BY-ND-4.0",
    "UNLICENSE": "Unlicense",
    "ZLIB": "Zlib",
}
_SPDX_WARN = {
    "GPL-3.0",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "LGPL-3.0",
    "LGPL-2.1",
    "AGPL-3.0",
    "CC-BY-NC-4.0",
    "CC-BY-NC-SA-4.0",
    "CC-BY-ND-4.0",
}
_LICENSE_WARN_TERMS = {
    "non-commercial",
    "non commercial",
    "personal use",
    "no derivatives",
    "nc",
    "nd",
}
_LICENSE_BLOCK_TERMS = {
    "all rights reserved",
    "proprietary",
    "no redistribution",
    "no redistribution",
    "not for distribution",
    "do not distribute",
}
_SPACES_HYPHEN = re.compile(r"[\s_]+")
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\.-]+")


def _normalise_spdx(value: str) -> str:
    return _SPACES_HYPHEN.sub("-", value.strip()).upper()


def _match_spdx(token: str | None) -> Optional[str]:
    if not token:
        return None
    candidate = _normalise_spdx(token)
    if candidate in _SPDX_CANONICAL:
        return _SPDX_CANONICAL[candidate]
    return None


def _extract_spdx(text: str | None) -> Optional[str]:
    if not text:
        return None
    direct = _match_spdx(text)
    if direct:
        return direct
    for match in _TOKEN_PATTERN.findall(text):
        candidate = _match_spdx(match)
        if candidate:
            return candidate
    return None


def _normalize_license_entry(
    entry: Any,
) -> tuple[str, Optional[str], Mapping[str, Any]]:
    meta: Mapping[str, Any]
    if isinstance(entry, Mapping):
        meta = entry
    else:
        meta = {"value": entry}

    label_candidates = [
        "spdx_id",
        "spdx",
        "id",
        "code",
        "name",
        "title",
        "label",
        "short_name",
    ]
    label = ""
    for key in label_candidates:
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            label = value.strip()
            break
    if not label and isinstance(entry, str):
        label = entry.strip()

    if not label and isinstance(meta.get("value"), str):
        label = str(meta["value"]).strip()

    text_field = meta.get("text") or meta.get("description")
    spdx = _extract_spdx(label) or (
        _extract_spdx(text_field) if isinstance(text_field, str) else None
    )
    return label, spdx, meta


def _license_plugin(context: "BundleContext") -> Iterable[AdvisoryIssue]:
    licenses = context.licenses or []
    findings: List[AdvisoryIssue] = []
    if not licenses:
        return findings

    seen: set[str] = set()
    source = (context.metadata or {}).get("source", "bundle")

    for index, entry in enumerate(licenses):
        label, spdx, meta = _normalize_license_entry(entry)
        if not label:
            continue
        dedupe_key = (spdx or label).lower()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        detail: Dict[str, Any] = {
            "plugin": "spdx_license",
            "label": label,
            "index": index,
            "source": source,
        }
        if meta:
            detail["raw"] = dict(meta)
        severity = "info"
        if spdx:
            detail["spdx"] = spdx
            if spdx in _SPDX_WARN:
                severity = "warn"
                message = (
                    f"License '{spdx}' may impose share-alike or non-commercial terms."
                )
            else:
                message = f"SPDX license '{spdx}' detected."
        else:
            label_lower = label.lower()
            if any(term in label_lower for term in _LICENSE_BLOCK_TERMS):
                severity = "error"
                message = f"License '{label}' forbids redistribution."
            elif any(term in label_lower for term in _LICENSE_WARN_TERMS):
                severity = "warn"
                message = f"License '{label}' may restrict usage."
            else:
                severity = "warn"
                message = (
                    f"Unrecognised license entry '{label}' requires manual review."
                )
        issue = AdvisoryIssue(
            target_id=_context_target(context, "license"),
            kind="policy",
            message=message,
            severity=severity,
            detail=detail,
        )
        findings.append(issue)
    return findings


_IP_TERMS: Dict[str, set[str]] = {
    "Nintendo": {"nintendo", "mario", "zelda", "pokemon", "metroid"},
    "Disney": {"disney", "pixar", "marvel", "star wars", "lucasfilm"},
    "Warner": {"warner", "dc comics", "harry potter", "hogwarts"},
    "Sony": {"playstation", "spider-man", "uncharted", "last of us"},
    "Universal": {"jurassic", "dreamworks", "minions", "fast & furious"},
}


def _collect_text_segments(payload: Any) -> Iterable[str]:
    if isinstance(payload, str):
        yield payload
    elif isinstance(payload, Mapping):
        for value in payload.values():
            yield from _collect_text_segments(value)
    elif isinstance(payload, Iterable) and not isinstance(payload, (str, bytes)):
        for item in payload:
            yield from _collect_text_segments(item)


def _ip_match_plugin(context: "BundleContext") -> Iterable[AdvisoryIssue]:
    segments: List[str] = []
    for scene in (context.scenes or {}).values():
        if isinstance(scene, Mapping):
            segments.extend(
                str(scene.get(key) or "")
                for key in ("title", "summary", "description")
                if scene.get(key)
            )
            segments.extend(
                str(x) for x in _collect_text_segments(scene.get("dialogue"))
            )
            segments.extend(str(x) for x in _collect_text_segments(scene.get("lines")))
    for character in (context.characters or {}).values():
        if isinstance(character, Mapping):
            segments.extend(
                str(character.get(key) or "")
                for key in ("name", "alias", "display_name", "franchise", "ip")
                if character.get(key)
            )
            aliases = character.get("aliases")
            if isinstance(aliases, Iterable) and not isinstance(aliases, (str, bytes)):
                segments.extend(str(alias) for alias in aliases if alias)
    metadata = context.metadata or {}
    for value in metadata.values():
        if isinstance(value, str):
            segments.append(value)

    haystack = "\n".join(seg for seg in segments if isinstance(seg, str)).lower()
    if not haystack.strip():
        return []

    matches: Dict[str, set[str]] = {}
    for owner, tokens in _IP_TERMS.items():
        for token in tokens:
            if token in haystack:
                matches.setdefault(owner, set()).add(token)
    if not matches:
        return []

    detail = {
        "plugin": "ip_match",
        "matches": [
            {"owner": owner, "tokens": sorted(tokens)}
            for owner, tokens in sorted(matches.items())
        ],
        "source": metadata.get("source"),
    }
    message = "Possible third-party IP references: " + ", ".join(sorted(matches))
    issue = AdvisoryIssue(
        target_id=_context_target(context, "ip"),
        kind="copyright",
        message=message,
        severity="warn",
        detail=detail,
    )
    return [issue]


def _severity_from_classifier(score: Optional[float], severity: Optional[str]) -> str:
    if severity:
        level = severity.lower()
        if level in {"info", "warn", "error"}:
            return level
        if level == "block":
            return "error"
    if score is None:
        return "warn"
    if score >= 0.9:
        return "error"
    if score >= 0.6:
        return "warn"
    return "info"


def _nsfw_plugin(context: "BundleContext") -> Iterable[AdvisoryIssue]:
    if _NSF_CLASSIFIER is None or not context.assets:
        return []

    try:
        classifications = list(_NSF_CLASSIFIER(context))
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("NSFW classifier hook failed: %s", exc)
        return []

    if not classifications:
        return []

    path_lookup: Dict[Path, str] = {}
    for rel, source in context.assets:
        if source:
            try:
                path_lookup[source.resolve()] = rel
            except (OSError, RuntimeError):  # pragma: no cover - best effort
                path_lookup[source] = rel

    findings: List[AdvisoryIssue] = []
    source = (context.metadata or {}).get("source")
    for entry in classifications:
        if not isinstance(entry, Mapping):
            continue
        asset_id = entry.get("id") or entry.get("asset") or entry.get("path")
        if not isinstance(asset_id, str) or not asset_id.strip():
            continue
        score_raw = entry.get("score")
        score: Optional[float] = None
        if score_raw is not None:
            try:
                score = float(score_raw)
            except (TypeError, ValueError):  # pragma: no cover - defensive
                score = None
        severity = _severity_from_classifier(score, entry.get("severity"))
        label = entry.get("label") if isinstance(entry.get("label"), str) else None
        try:
            rel = path_lookup.get(Path(asset_id).resolve(), asset_id)
        except (OSError, RuntimeError, ValueError):
            rel = asset_id
        detail = {
            "plugin": "nsfw_classifier",
            "asset": rel,
            "score": score,
            "label": label,
            "source": source,
        }
        message = entry.get("message")
        if not isinstance(message, str) or not message.strip():
            message = (
                f"Classifier flagged '{rel}' (score {score:.2f})."
                if score is not None
                else f"Classifier flagged '{rel}'."
            )
        issue = AdvisoryIssue(
            target_id=f"asset:{rel}",
            kind="nsfw",
            message=message,
            severity=severity,
            detail={k: v for k, v in detail.items() if v is not None},
        )
        findings.append(issue)
    return findings


def _coerce_issue(
    payload: Union[AdvisoryIssue, Mapping[str, Any]], plugin: str
) -> Optional[AdvisoryIssue]:
    if isinstance(payload, AdvisoryIssue):
        payload.detail.setdefault("plugin", plugin)
        return payload
    if not isinstance(payload, Mapping):
        LOGGER.warning(
            "Scanner plugin %s returned unsupported payload type: %s",
            plugin,
            type(payload).__name__,
        )
        return None
    try:
        issue = AdvisoryIssue(
            target_id=str(payload["target_id"]),
            kind=str(payload.get("kind") or "advisory"),
            message=str(payload.get("message") or ""),
            severity=str(payload.get("severity") or "info").lower(),
            detail=dict(payload.get("detail") or {}),
        )
        issue.detail.setdefault("plugin", plugin)
        return issue
    except KeyError as exc:  # pragma: no cover - defensive
        LOGGER.warning("Scanner plugin %s returned payload missing %s", plugin, exc)
        return None


def _run_plugin(
    plugin: RegisteredPlugin, context: "BundleContext"
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    try:
        issues_iter = plugin.handler(context)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.exception("Scanner plugin %s crashed: %s", plugin.name, exc)
        return entries

    for payload in issues_iter or []:
        issue = _coerce_issue(payload, plugin.name)
        if not issue:
            continue
        issue.detail.setdefault("source", (context.metadata or {}).get("source"))
        entry = log_issue(issue)
        entries.append(entry)
    return entries


def run_bundle_plugins(context: "BundleContext") -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    for plugin in list(_PLUGINS):
        if plugin.name == "nsfw_classifier" and _NSF_CLASSIFIER is None:
            continue
        plugin_entries = _run_plugin(plugin, context)
        if plugin_entries:
            LOGGER.debug(
                "Scanner plugin %s produced %s findings",
                plugin.name,
                len(plugin_entries),
            )
            findings.extend(plugin_entries)
    return findings


def _dedupe_findings(entries: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    dedup: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        issue_id = str(entry.get("issue_id") or "")
        if issue_id:
            dedup[issue_id] = dict(entry)
        else:
            dedup[str(len(dedup))] = dict(entry)
    return list(dedup.values())


def _normalise_entry(entry: Mapping[str, Any]) -> Dict[str, Any]:
    severity = str(entry.get("severity") or "").lower()
    if severity in {"error", "critical", "block"}:
        level = "block"
    elif severity == "warn":
        level = "warn"
    else:
        level = "info"
    detail = (
        entry.get("detail") if isinstance(entry.get("detail"), MutableMapping) else {}
    )
    plugin = detail.get("plugin") if isinstance(detail, Mapping) else None
    return {
        "level": level,
        "severity": severity or level,
        "code": entry.get("kind") or "ADVISORY",
        "message": entry.get("message") or "",
        "detail": detail or {},
        "issue_id": entry.get("issue_id"),
        "plugin": plugin,
        "raw": dict(entry),
    }


def scan(bundle: BundleDict | "BundleContext") -> List[Dict[str, Any]]:
    """
    Run the advisory scanner for ``bundle`` and normalise severity levels.

    The return payload matches the CLI expectations: ``level`` is one of
    ``info``/``warn``/``block``.
    """

    from comfyvn.core.advisory_hooks import BundleContext
    from comfyvn.core.advisory_hooks import scan as _scan_bundle

    if isinstance(bundle, BundleContext):
        context = bundle
    else:
        context = _bundle_context_from_dict(bundle)

    raw_findings = _scan_bundle(context)
    combined = _dedupe_findings(raw_findings)
    return [_normalise_entry(entry) for entry in combined]


# Register built-in plugins at import time.
register_scanner_plugin("spdx_license", _license_plugin)
register_scanner_plugin("ip_match", _ip_match_plugin)
register_scanner_plugin("nsfw_classifier", _nsfw_plugin, optional=True)

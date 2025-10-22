from __future__ import annotations

"""
Hugging Face Hub public connector.

Provides health/search/metadata helpers plus a guarded pull planner so Studio
tools can reason about repository contents without downloading artifacts until
contributors opt in with a personal access token and license acknowledgement.
"""

from datetime import datetime, timezone
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TypedDict,
    cast,
)

from . import provider_secrets, resolve_credential

try:  # pragma: no cover - optional dependency
    from huggingface_hub import (
        DatasetFilter,
        HfApi,
        HfHubHTTPError,
        ModelFilter,
        SpaceFilter,
    )
    from huggingface_hub.errors import (
        RepositoryNotFoundError,  # type: ignore[attr-defined]
    )
except Exception:  # pragma: no cover - defensive fallback when dependency missing
    DatasetFilter = None  # type: ignore[assignment]
    HfApi = None  # type: ignore[assignment]
    HfHubHTTPError = Exception  # type: ignore[assignment]
    ModelFilter = None  # type: ignore[assignment]
    RepositoryNotFoundError = Exception  # type: ignore[assignment]
    SpaceFilter = None  # type: ignore[assignment]

PROVIDER_ID = "hf_hub"
DISPLAY_NAME = "Hugging Face Hub"
FEATURE_FLAG = "enable_public_model_hubs"
DOCS_URL = "https://huggingface.co/docs/hub/index"
API_URL = "https://huggingface.co/docs/hub/api"
LAST_CHECKED = "2025-02-19"

ENV_KEYS: Tuple[str, ...] = (
    "HF_TOKEN",
    "HF_API_TOKEN",
    "HUGGINGFACEHUB_API_TOKEN",
    "HUGGINGFACEHUB_TOKEN",
)
SECRET_KEYS: Tuple[str, ...] = ("token", "api_token", "hf_token", "huggingface_token")

DEFAULT_KIND = "model"
SEARCH_LIMIT_DEFAULT = 10
SEARCH_LIMIT_MAX = 50
LARGE_FILE_BYTES = 1_073_741_824  # 1 GiB threshold for warning contributors

CardData = Mapping[str, Any]


class ProviderError(RuntimeError):
    """
    Canonical error raised by this module so routes can map status codes.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = dict(payload or {})


class FilePlan(TypedDict, total=False):
    path: str
    size: int
    is_large: bool
    lfs: bool
    download_url: str


def metadata() -> Dict[str, Any]:
    """
    Basic connector metadata for docs, UI affordances, and feature flags.
    """

    return {
        "id": PROVIDER_ID,
        "name": DISPLAY_NAME,
        "docs_url": DOCS_URL,
        "api_docs": API_URL,
        "last_checked": LAST_CHECKED,
        "feature_flag": FEATURE_FLAG,
        "env_keys": list(ENV_KEYS),
        "supports": ["search", "metadata", "gated_pull_plan"],
        "dry_run": True,
    }


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _config_with_defaults(config: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    data.update(provider_secrets(PROVIDER_ID))
    if isinstance(config, Mapping):
        data.update(dict(config))
    return data


def _token_from(config: Mapping[str, Any] | None = None) -> str:
    resolved = resolve_credential(
        PROVIDER_ID,
        env_keys=ENV_KEYS,
        secret_keys=SECRET_KEYS,
    )
    if resolved:
        return resolved.strip()
    if not config:
        return ""
    for key in ("token", "api_token", "hf_token", "huggingface_token", "hf_api_token"):
        raw = config.get(key)
        if raw:
            return str(raw).strip()
    return ""


def _ensure_client(token: Optional[str] = None):
    if HfApi is None:
        raise ProviderError(
            "huggingface_hub not installed; `pip install huggingface_hub` to enable",
            status_code=503,
        )
    return HfApi(token=token or None)


def _normalise_license(card: CardData | None, fallback: Optional[str]) -> Optional[str]:
    if isinstance(card, Mapping):
        for key in ("license", "model:license", "dataset:license", "license_name"):
            value = card.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return None


def _normalise_tags(item_tags: Iterable[Any], card: CardData | None) -> List[str]:
    tags: List[str] = []
    for tag in item_tags:
        if not tag:
            continue
        tags.append(str(tag).strip())
    if isinstance(card, Mapping):
        extra = card.get("tags")
        if isinstance(extra, (list, tuple, set)):
            for tag in extra:
                if tag:
                    tags.append(str(tag).strip())
    cleaned = sorted({tag for tag in tags if tag})
    return cleaned


def _summarise_card(card: CardData | None) -> Dict[str, Any]:
    if not isinstance(card, Mapping):
        return {}
    summary: Dict[str, Any] = {}
    for field in (
        "summary",
        "license",
        "pipeline_tag",
        "language",
        "library_name",
        "datasets",
        "base_model",
    ):
        value = card.get(field)
        if value:
            summary[field] = value
    model_index = card.get("model-index")
    if isinstance(model_index, list) and model_index:
        summary["model_index_count"] = len(model_index)
    return summary


def _file_record(entry: Any) -> FilePlan:
    path = (
        getattr(entry, "rfilename", None)
        or getattr(entry, "path", None)
        or getattr(entry, "filename", None)
    )
    path = str(path or "")
    size = getattr(entry, "size", None)
    try:
        size_int = int(size) if size is not None else 0
    except (TypeError, ValueError):
        size_int = 0
    is_large = bool(size_int and size_int >= LARGE_FILE_BYTES)
    lfs = bool(getattr(entry, "lfs", False))
    download_url = getattr(entry, "download_url", None) or ""
    return FilePlan(
        path=path,
        size=size_int,
        is_large=is_large,
        lfs=lfs,
        download_url=download_url,
    )


def _files_payload(entries: Iterable[Any]) -> Tuple[List[FilePlan], int, int]:
    files: List[FilePlan] = []
    total = 0
    flagged = 0
    for entry in entries:
        record = _file_record(entry)
        files.append(record)
        total += record.get("size", 0)
        if record.get("is_large"):
            flagged += 1
    return files, total, flagged


def _repo_payload(
    repo: Any,
    *,
    kind: str,
) -> Dict[str, Any]:
    card: CardData | None = getattr(repo, "cardData", None)
    tags = _normalise_tags(getattr(repo, "tags", []) or [], card)
    license_name = _normalise_license(card, getattr(repo, "license", None))
    files, total_bytes, flagged = _files_payload(getattr(repo, "siblings", []) or [])
    last_modified = getattr(repo, "lastModified", None)
    last_modified_iso = None
    if last_modified:
        try:
            last_modified_iso = last_modified.isoformat()  # type: ignore[call-arg]
        except AttributeError:
            last_modified_iso = str(last_modified)
    payload: Dict[str, Any] = {
        "id": getattr(repo, "id", getattr(repo, "repoId", None)),
        "name": getattr(repo, "modelId", getattr(repo, "id", None)),
        "type": kind,
        "private": bool(getattr(repo, "private", False)),
        "gated": bool(getattr(repo, "gated", False)),
        "likes": getattr(repo, "likes", None),
        "downloads": getattr(repo, "downloads", None),
        "updated_at": last_modified_iso,
        "tags": tags,
        "files": files,
        "card": _summarise_card(card),
        "total_size": total_bytes,
        "large_file_count": flagged,
        "license": license_name,
        "sha": getattr(repo, "sha", None),
        "card_exists": bool(card),
    }
    if getattr(repo, "author", None):
        payload["author"] = getattr(repo, "author")
    if getattr(repo, "language", None):
        payload["language"] = getattr(repo, "language")
    if getattr(repo, "task", None):
        payload["task"] = getattr(repo, "task")
    return payload


def _build_filter(kind: str, search: Optional[str]) -> Any:
    if kind == "dataset" and DatasetFilter:
        return DatasetFilter(search=search)
    if kind == "space" and SpaceFilter:
        return SpaceFilter(search=search)
    if kind == "model" and ModelFilter:
        return ModelFilter(search=search)
    return None


def health(config: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    cfg = _config_with_defaults(config)
    try:
        token = _token_from(cfg)
    except Exception:  # pragma: no cover - defensive
        token = ""
    ok = HfApi is not None
    payload = {
        "ok": ok,
        "dry_run": True,
        "reason": None if ok else "huggingface_hub missing",
        "docs_url": DOCS_URL,
        "api_docs": API_URL,
        "last_checked": LAST_CHECKED,
        "token_present": bool(token),
        "timestamp": _now_iso(),
    }
    return {**metadata(), **payload}


def search(
    query: str,
    *,
    kind: str = DEFAULT_KIND,
    limit: int = SEARCH_LIMIT_DEFAULT,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if not query.strip():
        raise ProviderError("query required", status_code=400)
    kind = kind or DEFAULT_KIND
    kind = kind.lower()
    limit = max(1, min(int(limit or SEARCH_LIMIT_DEFAULT), SEARCH_LIMIT_MAX))
    client = _ensure_client(token)
    search_term = query.strip()
    filter_obj = _build_filter(kind, search_term)
    try:
        if kind == "dataset":
            results = client.list_datasets(
                search=search_term, limit=limit, filter=filter_obj, cardData=True
            )
        elif kind == "space":
            results = client.list_spaces(
                search=search_term, limit=limit, filter=filter_obj, cardData=True
            )
        else:
            results = client.list_models(
                search=search_term, limit=limit, filter=filter_obj, cardData=True
            )
    except HfHubHTTPError as exc:  # pragma: no cover - network failure path
        raise ProviderError("hugging face hub search failed", status_code=502) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise ProviderError("unexpected search failure", status_code=500) from exc

    items = [_repo_payload(repo, kind=kind) for repo in results]
    return {
        "ok": True,
        "count": len(items),
        "items": items,
        "query": search_term,
        "kind": kind,
        "limit": limit,
        "timestamp": _now_iso(),
        "dry_run": True,
    }


def model_metadata(
    repo_id: str,
    *,
    kind: str = DEFAULT_KIND,
    revision: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    if not repo_id.strip():
        raise ProviderError("repository id required", status_code=400)
    kind = (kind or DEFAULT_KIND).lower()
    client = _ensure_client(token)
    try:
        if kind == "dataset":
            info = client.dataset_info(
                repo_id, revision=revision, token=token, files_metadata=True
            )
        elif kind == "space":
            info = client.space_info(
                repo_id, revision=revision, token=token, files_metadata=True
            )
        else:
            info = client.model_info(
                repo_id, revision=revision, token=token, files_metadata=True
            )
    except RepositoryNotFoundError as exc:
        raise ProviderError("repository not found", status_code=404) from exc
    except HfHubHTTPError as exc:  # pragma: no cover - network failure path
        if (
            getattr(exc, "response", None)
            and getattr(exc.response, "status_code", None) == 401
        ):
            raise ProviderError("authentication required", status_code=401) from exc
        raise ProviderError(
            "hugging face hub metadata lookup failed", status_code=502
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise ProviderError("unexpected metadata failure", status_code=500) from exc

    payload = _repo_payload(info, kind=kind)
    payload["requires_token"] = bool(payload.get("private") or payload.get("gated"))
    payload["card"] = {
        **payload.get("card", {}),
        "raw_sha": getattr(info, "cardDataSha", None),
    }
    payload["siblings_count"] = len(payload.get("files") or [])
    payload["sha"] = getattr(info, "sha", payload.get("sha"))

    return {
        "ok": True,
        "item": payload,
        "repo_id": repo_id,
        "kind": kind,
        "revision": revision,
        "timestamp": _now_iso(),
        "dry_run": True,
    }


def pull_plan(
    repo_id: str,
    *,
    kind: str = DEFAULT_KIND,
    revision: Optional[str] = None,
    files: Optional[Sequence[str]] = None,
    token: Optional[str] = None,
    ack_license: bool = False,
) -> Dict[str, Any]:
    if not ack_license:
        raise ProviderError("license acknowledgement required", status_code=412)
    if not repo_id.strip():
        raise ProviderError("repository id required", status_code=400)
    kind = (kind or DEFAULT_KIND).lower()

    metadata_result = model_metadata(
        repo_id,
        kind=kind,
        revision=revision,
        token=token,
    )
    item = metadata_result["item"]
    if item.get("requires_token") and not token:
        raise ProviderError(
            "hugging face token required for gated or private repos", status_code=401
        )

    requested = {str(name).strip() for name in files or [] if str(name).strip()}
    available_files = item.get("files") or []
    planned_files: List[FilePlan] = []
    total_bytes = 0
    large_files = 0
    for file_entry in available_files:
        path = file_entry.get("path", "")
        if requested and path not in requested:
            continue
        planned_files.append(cast(FilePlan, file_entry))
        total_bytes += int(file_entry.get("size", 0) or 0)
        if file_entry.get("is_large"):
            large_files += 1

    if requested and not planned_files:
        raise ProviderError("requested files not found", status_code=404)

    plan = {
        "repo_id": repo_id,
        "kind": kind,
        "revision": revision or item.get("sha"),
        "files": planned_files,
        "estimated_bytes": total_bytes,
        "large_file_count": large_files,
        "requires_token": item.get("requires_token"),
        "acknowledged_license": True,
        "dry_run": True,
    }
    return {
        "ok": True,
        "plan": plan,
        "timestamp": _now_iso(),
        "metadata": metadata_result,
    }


def prepare_pull(
    repo_id: str,
    *,
    kind: str = DEFAULT_KIND,
    revision: Optional[str] = None,
    files: Optional[Sequence[str]] = None,
    config: Mapping[str, Any] | None = None,
    ack_license: bool = False,
) -> Dict[str, Any]:
    cfg = _config_with_defaults(config)
    token = _token_from(cfg)
    if not token:
        token = str(cfg.get("token") or "").strip()
    if not token:
        raise ProviderError("hugging face token required", status_code=401)
    return pull_plan(
        repo_id,
        kind=kind,
        revision=revision,
        files=files,
        token=token,
        ack_license=ack_license,
    )


__all__ = [
    "API_URL",
    "DOCS_URL",
    "ENV_KEYS",
    "FEATURE_FLAG",
    "LAST_CHECKED",
    "LARGE_FILE_BYTES",
    "PROVIDER_ID",
    "ProviderError",
    "health",
    "metadata",
    "model_metadata",
    "prepare_pull",
    "pull_plan",
    "search",
]

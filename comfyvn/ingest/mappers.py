from __future__ import annotations

"""
Helpers that translate third-party asset metadata into the internal schema.

The ingest API accepts payloads sourced from FurAffinity, Civitai, HuggingFace,
or ad-hoc local drops.  Each provider exposes slightly different fields; this
module normalises the payloads so downstream consumers only deal with a single
shape.  The resulting metadata is safe to persist inside the asset registry and
sidecars.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

_IMAGE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".gif",
    ".tif",
    ".tiff",
}
_AUDIO_SUFFIXES = {".wav", ".wave", ".mp3", ".ogg", ".flac", ".aac"}
_MODEL_SUFFIXES = {".ckpt", ".safetensors", ".pt", ".bin"}
_VIDEO_SUFFIXES = {".mp4", ".webm", ".avi", ".mov"}
_TEXTURE_SUFFIXES = {".dds", ".ktx", ".tga"}


def _lower_strip(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    return candidate if candidate else None


def _dedupe(seq: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    ordered: List[str] = []
    for item in seq:
        key = item.strip()
        if not key:
            continue
        lowered = key.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(key)
    return ordered


def _normalise_tags(*candidates: Iterable[str]) -> List[str]:
    tags: List[str] = []
    for iterable in candidates:
        for tag in iterable:
            if not tag:
                continue
            tags.append(str(tag).strip("# ").lower())
    return _dedupe(tags)


def _normalise_authors(entries: Iterable[str | Dict[str, Any]]) -> List[str]:
    authors: List[str] = []
    for entry in entries:
        if isinstance(entry, dict):
            name = entry.get("name") or entry.get("username")
            if name:
                authors.append(str(name))
            continue
        if isinstance(entry, str):
            authors.append(entry)
    return _dedupe(authors)


def _guess_asset_type_from_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return "images"
    if suffix in _AUDIO_SUFFIXES:
        return "audio"
    if suffix in _MODEL_SUFFIXES:
        return "models"
    if suffix in _VIDEO_SUFFIXES:
        return "video"
    if suffix in _TEXTURE_SUFFIXES:
        return "textures"
    if suffix == ".json":
        return "json"
    return "generic"


@dataclass(slots=True)
class NormalisedAssetMetadata:
    """Canonical metadata payload produced by :func:`normalise_metadata`."""

    title: Optional[str]
    description: Optional[str]
    tags: List[str] = field(default_factory=list)
    license: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    rating: Optional[str] = None
    source_url: Optional[str] = None
    asset_type: Optional[str] = None
    nsfw: Optional[bool] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "authors": list(self.authors),
        }
        if self.license:
            payload["license"] = self.license
        if self.rating:
            payload["rating"] = self.rating
        if self.source_url:
            payload["source"] = self.source_url
        if self.asset_type:
            payload["asset_type"] = self.asset_type
        if self.nsfw is not None:
            payload["nsfw"] = self.nsfw
        if self.extra:
            payload["extra"] = dict(self.extra)
        return payload

    def merge(self, other: Optional[Dict[str, Any]]) -> None:
        if not other:
            return
        title = _lower_strip(other.get("title")) if isinstance(other, dict) else None
        if title:
            self.title = title
        description = (
            _lower_strip(other.get("description")) if isinstance(other, dict) else None
        )
        if description:
            self.description = description
        tags = list(other.get("tags", [])) if isinstance(other, dict) else []
        if tags:
            self.tags = _dedupe(self.tags + [str(tag) for tag in tags])
        license_tag = (
            _lower_strip(other.get("license")) if isinstance(other, dict) else None
        )
        if license_tag:
            self.license = license_tag
        authors = []
        if isinstance(other, dict):
            raw_authors = other.get("authors") or other.get("creators")
            if isinstance(raw_authors, Sequence) and not isinstance(
                raw_authors, (str, bytes)
            ):
                authors = [str(entry) for entry in raw_authors]
        if authors:
            self.authors = _dedupe(self.authors + authors)
        rating = _lower_strip(other.get("rating")) if isinstance(other, dict) else None
        if rating:
            self.rating = rating
        asset_type = (
            _lower_strip(other.get("asset_type")) if isinstance(other, dict) else None
        )
        if asset_type:
            self.asset_type = asset_type
        if isinstance(other, dict):
            extra = dict(other.get("extra", {}))
            if extra:
                merged = dict(self.extra)
                merged.update(extra)
                self.extra = merged


def normalise_metadata(
    provider: str,
    payload: Dict[str, Any] | None,
    *,
    fallback_asset_type: Optional[str] = None,
    source_url: str | None = None,
) -> NormalisedAssetMetadata:
    """
    Return a normalised metadata payload for ``provider``.

    Unknown providers fall back to pass-through behaviour while still applying
    basic tag and author normalisation.  Callers may supply
    ``fallback_asset_type`` when they already know the bucket (e.g. portraits).
    """

    provider_key = (provider or "generic").strip().lower()
    data = payload or {}
    meta = NormalisedAssetMetadata(
        title=_lower_strip(data.get("title")),
        description=_lower_strip(data.get("description")),
        tags=_normalise_tags(data.get("tags", [])),
        license=_lower_strip(data.get("license") or data.get("license_tag")),
        authors=_normalise_authors(data.get("authors") or data.get("creators") or []),
        rating=_lower_strip(data.get("rating")),
        source_url=source_url or _lower_strip(data.get("source") or data.get("url")),
        asset_type=_lower_strip(data.get("asset_type")),
        nsfw=bool(data.get("nsfw")) if "nsfw" in data else None,
        extra=(
            dict(data.get("extra", {})) if isinstance(data.get("extra"), dict) else {}
        ),
    )

    if provider_key in {"furaffinity", "fa"}:
        tags = data.get("tags") or data.get("keywords") or []
        meta.tags = _normalise_tags(tags)
        rating = _lower_strip(data.get("rating") or data.get("content_rating"))
        if rating:
            meta.rating = rating
        meta.extra.setdefault("submission_id", data.get("submission_id"))
        fa_author = data.get("author") or data.get("artist")
        if fa_author:
            meta.authors = _dedupe(meta.authors + [str(fa_author)])
        if meta.source_url is None and data.get("link"):
            meta.source_url = _lower_strip(data.get("link"))
        license_guess = _lower_strip(data.get("license") or data.get("usage"))
        if license_guess:
            meta.license = license_guess
    elif provider_key in {"civitai", "civit"}:
        model_info = data.get("model") or {}
        version = model_info.get("version") or {}
        meta.tags = _normalise_tags(
            data.get("tags", []),
            model_info.get("tags", []),
            version.get("trainedWords", []),
        )
        if not meta.license:
            meta.license = _lower_strip(
                version.get("baseModel") or model_info.get("type")
            )
        if not meta.authors:
            creator = model_info.get("creator") or {}
            meta.authors = _normalise_authors([creator.get("username")])
        if meta.source_url is None:
            meta.source_url = _lower_strip(model_info.get("url"))
        meta.extra.setdefault("model_id", model_info.get("id"))
        meta.extra.setdefault("version_id", version.get("id"))
    elif provider_key in {"huggingface", "hf"}:
        card = data.get("card_data") or {}
        meta.tags = _normalise_tags(data.get("tags", []), card.get("tags", []))
        if not meta.authors:
            authors = []
            maintainers = card.get("maintainers")
            if isinstance(maintainers, Sequence):
                authors.extend(str(name) for name in maintainers)
            meta.authors = _normalise_authors(authors or [data.get("author")])
        if not meta.source_url:
            meta.source_url = _lower_strip(data.get("repo_url") or data.get("url"))
        license_tag = _lower_strip(card.get("license") or data.get("license"))
        if license_tag:
            meta.license = license_tag
        meta.extra.setdefault("repo_id", data.get("repo_id"))
    else:
        meta.tags = _normalise_tags(meta.tags, data.get("keywords", []))
        meta.authors = _normalise_authors(meta.authors)

    if not meta.asset_type and fallback_asset_type:
        meta.asset_type = fallback_asset_type

    return meta


def guess_asset_type(path: Path, meta: NormalisedAssetMetadata | Dict[str, Any]) -> str:
    """
    Determine the asset registry bucket for ``path``.

    If metadata already supplies an ``asset_type`` value the helper uses it
    directly; otherwise the suffix is inspected and mapped to a bucket.
    """

    if isinstance(meta, NormalisedAssetMetadata):
        asset_type = meta.asset_type
    else:
        asset_type = (
            str(meta.get("asset_type")).strip().lower()
            if isinstance(meta, dict) and meta.get("asset_type")
            else None
        )
    if asset_type:
        return asset_type
    return _guess_asset_type_from_suffix(path)


def build_provenance_payload(
    *,
    provider: str,
    source_url: str | None,
    digest: str,
    extra: Dict[str, Any] | None = None,
    terms_acknowledged: bool | None = None,
) -> Dict[str, Any]:
    """Construct a provenance payload for the asset registry."""

    payload: Dict[str, Any] = {
        "provider": provider,
        "digest": digest,
    }
    if source_url:
        payload["source_url"] = source_url
    if extra:
        payload["provider_meta"] = dict(extra)
    if terms_acknowledged is not None:
        payload["terms_acknowledged"] = bool(terms_acknowledged)
    return payload

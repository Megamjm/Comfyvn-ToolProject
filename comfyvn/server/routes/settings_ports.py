from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Body
from pydantic import BaseModel, Field, validator

from comfyvn.config import ports as ports_config

LOGGER = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings/ports", tags=["Settings"])


class PortsPayload(BaseModel):
    host: str = Field(default="127.0.0.1", description="Server bind host.")
    ports: list[int] = Field(
        default_factory=lambda: [8001, 8000],
        description="Preferred server ports (first free wins).",
    )
    public_base: str | None = Field(
        default=None, description="Optional externally reachable base URL."
    )

    @validator("host")
    def _validate_host(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Host cannot be blank.")
        return value.strip()

    @validator("ports")
    def _validate_ports(cls, value: list[int]) -> list[int]:
        seen: set[int] = set()
        cleaned: list[int] = []
        for port in value:
            if port in seen:
                continue
            if not 0 < int(port) < 65536:
                raise ValueError(f"Invalid TCP port: {port}")
            seen.add(int(port))
            cleaned.append(int(port))
        if not cleaned:
            raise ValueError("At least one port must be provided.")
        return cleaned


class PortsStateResponse(PortsPayload):
    stamp: str = Field(description="Hash stamp for the configuration.")


class PortsProbePayload(BaseModel):
    host: str | None = Field(
        default=None, description="Override host for probing (defaults to config)."
    )
    ports: list[int] | None = Field(
        default=None,
        description="Override ports for probing (defaults to config order).",
    )
    path: str = Field(
        default="/health",
        description="Relative path to probe (defaults to /health).",
    )
    timeout: float = Field(
        default=1.5,
        ge=0.1,
        le=10.0,
        description="HTTP timeout per probe request.",
    )


class PortsProbeAttempt(BaseModel):
    url: str
    status_code: int | None = None
    error: str | None = None


class PortsProbeResponse(BaseModel):
    ok: bool
    host: str | None = None
    port: int | None = None
    base_url: str | None = None
    status_code: int | None = None
    attempts: list[PortsProbeAttempt] = Field(default_factory=list)
    stamp: str | None = None


def _connect_host(host: str) -> str:
    lowered = host.strip().lower()
    if lowered in {"0.0.0.0", "0", "*"}:
        return "127.0.0.1"
    if lowered in {"::", "[::]", "::0"}:
        return "localhost"
    return host


def _ensure_path(path: str) -> str:
    if not path.startswith("/"):
        return "/" + path
    return path


@router.get("/get", response_model=PortsStateResponse)
async def get_ports_config() -> PortsStateResponse:
    config = ports_config.get_config()
    return PortsStateResponse(
        host=str(config.get("host") or "127.0.0.1"),
        ports=[int(p) for p in config.get("ports", [])],
        public_base=(config.get("public_base") or None),
        stamp=ports_config.stamp(),
    )


@router.post("/set", response_model=PortsStateResponse)
async def set_ports_config(payload: PortsPayload) -> PortsStateResponse:
    saved = ports_config.set_config(payload.host, payload.ports, payload.public_base)
    stamp = ports_config.stamp()
    LOGGER.info(
        "Server ports updated via API",
        extra={
            "event": "api.settings.ports.set",
            "host": saved.get("host"),
            "ports": saved.get("ports"),
            "public_base": saved.get("public_base"),
            "stamp": stamp,
        },
    )
    return PortsStateResponse(
        host=str(saved.get("host") or payload.host),
        ports=[int(p) for p in saved.get("ports", payload.ports)],
        public_base=(saved.get("public_base") or payload.public_base),
        stamp=stamp,
    )


@router.post("/probe", response_model=PortsProbeResponse)
async def probe_ports(
    payload: PortsProbePayload = Body(default_factory=PortsProbePayload),
) -> PortsProbeResponse:
    config = ports_config.get_config()
    host = payload.host or str(config.get("host") or "127.0.0.1")
    ports = payload.ports or [int(p) for p in config.get("ports", [])]
    public_base = config.get("public_base")
    if not ports:
        ports = [8001, 8000]
    target_host = _connect_host(host)
    path = _ensure_path(payload.path or "/health")
    attempts: list[PortsProbeAttempt] = []

    async with httpx.AsyncClient(timeout=payload.timeout) as client:
        for port in ports:
            url = f"http://{target_host}:{port}{path}"
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                attempts.append(
                    PortsProbeAttempt(url=url, error=str(exc), status_code=None)
                )
                continue
            attempts.append(
                PortsProbeAttempt(url=url, status_code=response.status_code)
            )
            if 200 <= response.status_code < 500:
                base_url = (
                    str(public_base).rstrip("/")
                    if public_base
                    else f"http://{target_host}:{port}"
                )
                ports_config.record_runtime_state(
                    host=host,
                    ports=ports,
                    active_port=int(port),
                    base_url=base_url,
                    public_base=str(public_base) if public_base else None,
                )
                LOGGER.info(
                    "Server port probe succeeded",
                    extra={
                        "event": "api.settings.ports.probe",
                        "host": host,
                        "port": port,
                        "base_url": base_url,
                    },
                )
                return PortsProbeResponse(
                    ok=True,
                    host=host,
                    port=int(port),
                    base_url=base_url,
                    status_code=response.status_code,
                    attempts=attempts,
                    stamp=ports_config.stamp(),
                )

    LOGGER.info(
        "Server port probe failed",
        extra={
            "event": "api.settings.ports.probe",
            "host": host,
            "ports": ports,
        },
    )
    return PortsProbeResponse(
        ok=False,
        host=host,
        port=None,
        base_url=None,
        status_code=None,
        attempts=attempts,
        stamp=ports_config.stamp(),
    )


__all__ = ["router"]

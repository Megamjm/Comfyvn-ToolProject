from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, MutableMapping, Sequence


class RNGError(RuntimeError):
    """Raised when deterministic RNG encounters invalid usage."""


@dataclass
class RNGState:
    seed: int
    value: int
    uses: int


class DeterministicRNG:
    """
    Lightweight linear congruential generator (LCG) for deterministic branching.

    State can be fully reconstructed from ``seed`` and ``value`` so the runner
    can hop between requests without keeping an instance alive in memory.
    """

    _MOD: int = 2**32
    _MULT: int = 1664525
    _INC: int = 1013904223

    def __init__(self, seed: int, value: int | None = None, uses: int = 0) -> None:
        self._state = RNGState(
            seed=self._coerce_uint32(seed),
            value=self._coerce_uint32(value if value is not None else seed),
            uses=int(uses) if uses >= 0 else 0,
        )

    @staticmethod
    def _coerce_uint32(raw: int) -> int:
        return int(raw) % DeterministicRNG._MOD

    @property
    def seed(self) -> int:
        return self._state.seed

    @property
    def uses(self) -> int:
        return self._state.uses

    @property
    def value(self) -> int:
        return self._state.value

    def _next(self) -> int:
        nxt = (self._MULT * self._state.value + self._INC) % self._MOD
        self._state.value = nxt
        self._state.uses += 1
        return nxt

    def random(self) -> float:
        """Return a deterministic float in [0, 1)."""
        return self._next() / self._MOD

    def weighted_index(self, weights: Sequence[float]) -> int:
        """
        Choose an index using relative weights (all weights must be >= 0).
        Deterministic because the underlying RNG is deterministic.
        """
        if not weights:
            raise RNGError("weighted_index requires at least one weight")

        cleaned = []
        total = 0.0
        for w in weights:
            weight = float(w)
            if weight < 0:
                raise RNGError("weights must be non-negative")
            cleaned.append(weight)
            total += weight

        if total <= 0:
            raise RNGError("weights must sum to a positive value")

        threshold = self.random() * total
        cursor = 0.0
        for idx, weight in enumerate(cleaned):
            cursor += weight
            if threshold < cursor:
                return idx
        return len(cleaned) - 1

    def advance_stream(self, steps: int) -> None:
        """Skip forward without consuming the actual draws for caller logic."""
        for _ in range(max(0, int(steps))):
            self._next()

    def to_state(self) -> dict[str, int]:
        return {
            "seed": self.seed,
            "value": self.value,
            "uses": self.uses,
        }

    @classmethod
    def from_state(cls, state: MutableMapping[str, object]) -> "DeterministicRNG":
        if state is None:
            raise RNGError("state is required to rebuild RNG")
        try:
            seed = int(state.get("seed"))  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover - defensive
            raise RNGError("rng.state.seed missing or invalid") from exc
        value_raw = state.get("value", seed)
        uses_raw = state.get("uses", 0)
        return cls(seed=seed, value=int(value_raw), uses=int(uses_raw))

    @classmethod
    def from_seed(cls, seed: int) -> "DeterministicRNG":
        return cls(seed=seed)

    @classmethod
    def sync_sequence(
        cls, seed: int, weights_iter: Iterable[Sequence[float]]
    ) -> list[int]:
        """
        Convenience helper: generate a deterministic index series without
        mutating caller state (used in tests).
        """
        rng = cls.from_seed(seed)
        return [rng.weighted_index(weights) for weights in weights_iter]

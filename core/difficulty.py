"""ASERT (aserti3-2d) per Vulcan: difficolta' a ogni blocco, solo interi.

La formula segue l'ASERT di Bitcoin Cash. Per un blocco di altezza ``h`` con
parent di timestamp ``t_parent`` e ancora ``(h_a, t_a, target_a)``::

    exponent = ((t_parent - t_a) - TARGET_SPACING * (h - h_a - 1))
               * 65536 // HALF_LIFE

Il termine ``- TARGET_SPACING`` rispetto alla formula "ingenua" compensa il
fatto che il timestamp disponibile e' quello del parent: un blocco che arriva
esattamente ogni ``TARGET_SPACING`` secondi lascia il target invariato.

La divisione e' troncata verso zero (come il ``/`` C di Bitcoin Cash), non
arrotondata per difetto come il ``//`` di Python per i negativi.
L'esponente e' in virgola fissa 16.16: la parte intera e' uno shift, quella
frazionaria un polinomio cubico a coefficienti interi.
"""

from __future__ import annotations

from dataclasses import dataclass

from .params import (
    GENESIS_POW_LIMIT,
    HALF_LIFE,
    MAX_TARGET,
    MIN_TARGET,
    TARGET_SPACING,
)

# Costanti del polinomio di aserti3-2d (approssimano 2^(frac/65536)).
POLY_C1 = 195_766_423_245_049
POLY_C2 = 971_821_376
POLY_C3 = 5_127
POLY_ROUND = 1 << 47
POLY_SHIFT = 48

FIXED_POINT = 1 << 16
UINT32_MAX = 0xFFFFFFFF
UINT64_MAX = 0xFFFFFFFFFFFFFFFF


class DifficultyError(ValueError):
    """Ancora o parametri di difficolta' non validi."""


def _check_int(value: int, name: str, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise DifficultyError(f"{name} must be an int")
    if value < 0 or value > maximum:
        raise DifficultyError(f"{name} out of range")
    return value


def _trunc_div(numerator: int, denominator: int) -> int:
    """Divisione intera troncata verso zero (non floor come ``//``)."""
    if denominator <= 0:
        raise DifficultyError("denominator must be positive")
    quotient = abs(numerator) // denominator
    return quotient if numerator >= 0 else -quotient


@dataclass(frozen=True, slots=True)
class ASERTAnchor:
    """Punto di riferimento fisso: genesis (altezza, timestamp, target)."""

    height: int
    timestamp: int
    target: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "height", _check_int(self.height, "anchor height", UINT32_MAX))
        object.__setattr__(
            self, "timestamp", _check_int(self.timestamp, "anchor timestamp", UINT64_MAX)
        )
        object.__setattr__(self, "target", _check_int(self.target, "anchor target", MAX_TARGET))
        if self.target < MIN_TARGET:
            raise DifficultyError("anchor target below MIN_TARGET")


def asert_target(
    height: int,
    parent_timestamp: int,
    anchor: ASERTAnchor,
    *,
    pow_limit: int = GENESIS_POW_LIMIT,
    target_spacing: int = TARGET_SPACING,
    half_life: int = HALF_LIFE,
) -> int:
    """Target per il blocco ``height`` dato il timestamp del suo parent.

    Il risultato e' sempre compreso tra ``MIN_TARGET`` e ``pow_limit``.
    Funzione pura e deterministica: nessun orologio, nessun float.
    """
    if not isinstance(anchor, ASERTAnchor):
        raise DifficultyError("anchor must be an ASERTAnchor")
    height = _check_int(height, "height", UINT32_MAX)
    parent_timestamp = _check_int(parent_timestamp, "parent_timestamp", UINT64_MAX)
    pow_limit = _check_int(pow_limit, "pow_limit", MAX_TARGET)
    target_spacing = _check_int(target_spacing, "target_spacing", UINT32_MAX)
    half_life = _check_int(half_life, "half_life", UINT32_MAX)
    if pow_limit < MIN_TARGET:
        raise DifficultyError("pow_limit below MIN_TARGET")
    if target_spacing == 0:
        raise DifficultyError("target_spacing must be positive")
    if half_life == 0:
        raise DifficultyError("half_life must be positive")
    if anchor.target > pow_limit:
        raise DifficultyError("anchor target above pow limit")
    if height < anchor.height:
        raise DifficultyError("height below anchor height")

    # Il genesis e' la sua stessa difficolta': non c'e' un parent precedente.
    if height == anchor.height:
        return anchor.target

    height_delta = height - anchor.height
    # Riferimento spostato di uno spacing: il timestamp e' quello del parent.
    numerator = (
        parent_timestamp
        - anchor.timestamp
        - target_spacing * (height_delta - 1)
    )
    exponent = _trunc_div(numerator * FIXED_POINT, half_life)

    shifts = exponent >> 16
    fractional = exponent - shifts * FIXED_POINT  # sempre in [0, 65535]

    # Guardie contro shift enormi: evitano interi giganteschi e sono
    # equivalenti al clamp, perche' il target e' limitato a pow_limit.
    if shifts > pow_limit.bit_length() + 1:
        return pow_limit
    if shifts < -(anchor.target.bit_length() + 2):
        return MIN_TARGET

    factor = (
        POLY_C1 * fractional
        + POLY_C2 * fractional * fractional
        + POLY_C3 * fractional * fractional * fractional
        + POLY_ROUND
    ) >> POLY_SHIFT
    factor += FIXED_POINT

    target = anchor.target * factor
    if shifts >= 0:
        target <<= shifts
    else:
        target >>= -shifts
    target >>= 16

    if target < MIN_TARGET:
        return MIN_TARGET
    if target > pow_limit:
        return pow_limit
    return target

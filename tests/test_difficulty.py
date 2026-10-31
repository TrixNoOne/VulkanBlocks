"""Test ASERT: solo interi, ancora fissa, nessun drift, clamp deterministici."""

import pytest

from core.difficulty import (
    ASERTAnchor,
    DifficultyError,
    _trunc_div,
    asert_target,
)
from core.params import (
    GENESIS_POW_LIMIT,
    HALF_LIFE,
    MAX_TARGET,
    MIN_TARGET,
    TARGET_SPACING,
)

UINT64_MAX = 0xFFFFFFFFFFFFFFFF


def anchor_at(
    target: int | None = None,
    *,
    height: int = 0,
    timestamp: int = 1_793_318_400,
) -> ASERTAnchor:
    return ASERTAnchor(
        height,
        timestamp,
        GENESIS_POW_LIMIT if target is None else target,
    )


def scheduled_parent(anchor: ASERTAnchor, height: int) -> int:
    """Timestamp del parent se i blocchi arrivano esattamente ogni 120 s."""
    return anchor.timestamp + (height - anchor.height - 1) * TARGET_SPACING


def test_anchor_block_returns_anchor_target():
    anchor = anchor_at(target=GENESIS_POW_LIMIT // 4)
    assert asert_target(anchor.height, 0, anchor) == anchor.target
    assert asert_target(anchor.height, UINT64_MAX, anchor) == anchor.target


def test_on_schedule_blocks_keep_target_unchanged():
    anchor = anchor_at(target=GENESIS_POW_LIMIT // 4)
    for height in (1, 2, 3, 10, 100, 1_000, 10_000):
        parent = scheduled_parent(anchor, height)
        assert asert_target(height, parent, anchor) == anchor.target


def test_late_block_raises_target_and_early_block_lowers_it():
    anchor = anchor_at(target=GENESIS_POW_LIMIT // 8)
    on_time = scheduled_parent(anchor, 1)

    late = asert_target(1, on_time + 3_600, anchor)
    early = asert_target(1, on_time - 3_600, anchor)

    assert late > anchor.target
    assert early < anchor.target
    assert MIN_TARGET <= early < anchor.target < late <= GENESIS_POW_LIMIT


@pytest.mark.parametrize("height", [1, 2, 500, 5_000])
def test_exact_half_life_doubles_and_halves(height):
    anchor = anchor_at(target=GENESIS_POW_LIMIT // 4)
    on_time = scheduled_parent(anchor, height)

    doubled = asert_target(height, on_time + HALF_LIFE, anchor)
    halved = asert_target(height, on_time - HALF_LIFE, anchor)

    assert doubled == anchor.target * 2
    assert halved == anchor.target // 2


def test_small_delays_are_monotonic():
    anchor = anchor_at(target=GENESIS_POW_LIMIT // 4)
    on_time = scheduled_parent(anchor, 7)
    deltas = [-(HALF_LIFE + 1), -HALF_LIFE, -3_600, -1, 0, 1, 3_600, HALF_LIFE]
    targets = [asert_target(7, on_time + delta, anchor) for delta in deltas]
    assert targets == sorted(targets)


def test_clamps_to_min_and_pow_limit():
    anchor = anchor_at(target=GENESIS_POW_LIMIT // 4)

    # Parent molto antecedente: il target scenderebbe sotto il minimo.
    assert asert_target(10, 0, anchor) == MIN_TARGET
    # Parent nel futuro estremo: il target supererebbe il pow-limit.
    assert asert_target(10, UINT64_MAX, anchor) == GENESIS_POW_LIMIT
    # Anche con shift enorme non si costruiscono interi giganteschi.
    assert asert_target(100, UINT64_MAX, anchor) == GENESIS_POW_LIMIT
    assert asert_target(100, 0, anchor) == MIN_TARGET


def test_target_always_within_bounds_for_non_monotonic_timestamps():
    anchor = anchor_at(target=GENESIS_POW_LIMIT // 4)
    timestamps = [
        anchor.timestamp + 240,
        anchor.timestamp - 120,
        anchor.timestamp + 60,
        anchor.timestamp - 60,
        anchor.timestamp + 1,
        anchor.timestamp,
    ]
    for height in range(1, len(timestamps) + 1):
        for timestamp in timestamps:
            target = asert_target(height, timestamp, anchor)
            assert MIN_TARGET <= target <= GENESIS_POW_LIMIT
            # Purezza: stesso input, stesso output.
            assert target == asert_target(height, timestamp, anchor)


def test_constant_offset_does_not_drift_over_a_long_sequence():
    anchor = anchor_at(target=GENESIS_POW_LIMIT // 3)
    expected = asert_target(1, scheduled_parent(anchor, 1) + 60, anchor)
    for height in range(1, 20_001):
        parent = scheduled_parent(anchor, height) + 60
        assert asert_target(height, parent, anchor) == expected


def test_long_on_schedule_sequence_has_no_drift():
    anchor = anchor_at(target=GENESIS_POW_LIMIT // 3)
    for height in range(1, 20_001):
        assert asert_target(height, scheduled_parent(anchor, height), anchor) == anchor.target


def test_truncating_division_toward_zero():
    assert _trunc_div(1, 2) == 0
    assert _trunc_div(-1, 2) == 0  # floor darebbe -1
    assert _trunc_div(3, 2) == 1
    assert _trunc_div(-3, 2) == -1
    with pytest.raises(DifficultyError):
        _trunc_div(1, 0)


def reference_asert(
    anchor: ASERTAnchor, height: int, parent_timestamp: int, pow_limit: int
) -> int:
    """Riscrittura indipendente del pseudo-codice aserti3-2d.

    Serve come oracolo: in particolare verifica l'ordine corretto tra shift e
    divisione finale per 2^16.
    """
    time_delta = parent_timestamp - (anchor.timestamp - TARGET_SPACING)
    height_delta = height - anchor.height
    numerator = (time_delta - TARGET_SPACING * height_delta) * 65536
    quotient = abs(numerator) // HALF_LIFE
    exponent = quotient if numerator >= 0 else -quotient

    shifts = exponent >> 16
    frac = exponent - shifts * 65536
    factor = (
        195_766_423_245_049 * frac
        + 971_821_376 * frac**2
        + 5_127 * frac**3
        + (1 << 47)
    ) >> 48
    factor += 65536

    target = anchor.target * factor
    target = target << shifts if shifts >= 0 else target >> (-shifts)
    target >>= 16
    return max(MIN_TARGET, min(target, pow_limit))


@pytest.mark.parametrize(
    ("height", "delay"),
    [
        (1, HALF_LIFE + 30_000),
        (2, 2 * HALF_LIFE + 12_345),
        (50, 3 * HALF_LIFE + 1),
        (1, -HALF_LIFE - 30_000),
        (500, -2 * HALF_LIFE - 12_345),
        (10_000, 4 * HALF_LIFE + 777),
    ],
)
def test_matches_reference_aserti3_2d_with_fractional_shifts(height, delay):
    anchor = anchor_at(target=GENESIS_POW_LIMIT // 32)
    parent = scheduled_parent(anchor, height) + delay
    assert asert_target(height, parent, anchor) == reference_asert(
        anchor, height, parent, GENESIS_POW_LIMIT
    )
    # Il caso esercita davvero shift positivi/negativi con parte frazionaria.
    exponent = ((delay) * 65536) // HALF_LIFE if delay >= 0 else -(
        (-delay * 65536) // HALF_LIFE
    )
    assert abs(exponent) >= 65536
    assert exponent % 65536 != 0


def test_slightly_early_block_uses_truncated_exponent():
    anchor = anchor_at(target=GENESIS_POW_LIMIT // 4)
    target = asert_target(1, anchor.timestamp - 1, anchor)
    assert MIN_TARGET < target < anchor.target


def test_anchor_validation():
    with pytest.raises(DifficultyError):
        ASERTAnchor(-1, 0, GENESIS_POW_LIMIT)
    with pytest.raises(DifficultyError):
        ASERTAnchor(0, -1, GENESIS_POW_LIMIT)
    with pytest.raises(DifficultyError):
        ASERTAnchor(0, 0, 0)
    with pytest.raises(DifficultyError):
        ASERTAnchor(0, 0, MAX_TARGET + 1)
    with pytest.raises(DifficultyError):
        ASERTAnchor(True, 0, GENESIS_POW_LIMIT)


def test_anchor_is_required():
    with pytest.raises(DifficultyError):
        asert_target(1, 0, object())  # type: ignore[arg-type]


def test_argument_validation():
    anchor = anchor_at(target=GENESIS_POW_LIMIT // 4)
    with pytest.raises(DifficultyError):
        asert_target(-1, anchor.timestamp, anchor)
    with pytest.raises(DifficultyError):
        asert_target(1, -1, anchor)
    with pytest.raises(DifficultyError):
        asert_target(1, True, anchor)  # type: ignore[arg-type]
    with pytest.raises(DifficultyError):
        asert_target(1, anchor.timestamp, anchor, pow_limit=0)
    with pytest.raises(DifficultyError):
        asert_target(1, anchor.timestamp, anchor, target_spacing=0)
    with pytest.raises(DifficultyError):
        asert_target(1, anchor.timestamp, anchor, half_life=0)
    with pytest.raises(DifficultyError):
        asert_target(1, anchor.timestamp, anchor, pow_limit=anchor.target - 1)


def test_height_below_anchor_rejected():
    anchor = anchor_at(height=10)
    with pytest.raises(DifficultyError, match="below anchor"):
        asert_target(9, anchor.timestamp, anchor)

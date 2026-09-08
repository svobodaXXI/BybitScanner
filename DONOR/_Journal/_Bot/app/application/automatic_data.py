"""Generic read primitives for future factor-aware statistics."""

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from app.core.automatic_data import (
    AutomaticFactorBucketPolicy,
    AutomaticFactorRegistry,
    AutomaticFactorQuality,
    DEFAULT_AUTOMATIC_FACTOR_REGISTRY,
)


class AutomaticFactorQueryService:
    """Filter/group/coverage/bucket observations without factor-specific methods."""

    def __init__(self, repository, registry: AutomaticFactorRegistry):
        self.repository = repository
        self.registry = registry

    async def filter(self, factor_id: str, *, trade_ids=(), predicate=None):
        trade_ids = tuple(trade_ids)
        self.registry.require(factor_id)
        observations = await self.repository.list(factor_id, trade_ids)
        return tuple(item for item in observations if predicate is None or predicate(item.value))

    async def group(self, factor_id: str, *, trade_ids=()):
        return _group(await self.filter(factor_id, trade_ids=trade_ids))

    async def coverage(self, factor_id: str, *, trade_ids=()):
        trade_ids = tuple(trade_ids)
        observations = await self.filter(factor_id, trade_ids=trade_ids)
        eligible = len(trade_ids)
        calculated = sum(1 for item in observations if item.value is not None and getattr(item.quality_status, "value", item.quality_status) != "MISSING")
        return {"factor_id": factor_id, "eligible": eligible, "calculated": calculated, "missing": max(eligible - calculated, 0), "coverage_rate": Decimal(calculated) / Decimal(eligible) if eligible else None}

    async def bucket(self, factor_id: str, *, trade_ids=(), policy=AutomaticFactorBucketPolicy.FIXED_BINS, bins=()):
        observations = await self.filter(factor_id, trade_ids=trade_ids)
        if policy in (AutomaticFactorBucketPolicy.FIXED_BINS, AutomaticFactorBucketPolicy.CUSTOM_BINS):
            if not bins:
                raise ValueError("bins are required for fixed/custom bucket policies")
            return _fixed_bins(observations, tuple(Decimal(str(item)) for item in bins))
        raise NotImplementedError(f"bucket policy is reserved for a later analytics phase: {policy}")


def resolve_current_observations(
    observations,
    registry: AutomaticFactorRegistry = DEFAULT_AUTOMATIC_FACTOR_REGISTRY,
):
    """Select one display observation per active factor without rewriting history.

    A registry-matching identity is preferred, including its missing state. If
    no observation exists for the current identity, the newest valid version
    is selected. Ties are resolved by capture/source timestamps and value so a
    read remains deterministic even for legacy repositories without ordering.
    """
    by_factor = defaultdict(list)
    for observation in observations:
        by_factor[observation.factor_id].append(observation)

    selected = []
    for definition in registry.list(active_only=True):
        candidates = by_factor.get(definition.factor_id, ())
        if not candidates:
            continue
        current = tuple(
            item for item in candidates
            if item.definition_version == definition.definition_version
            and item.calculation_version == definition.calculation_version
            and item.capture_semantics == definition.capture_semantics
        )
        pool = current or tuple(candidates)
        valid = tuple(
            item for item in pool
            if item.value is not None and item.quality_status is AutomaticFactorQuality.VALID
        )
        selected.append(max(valid or pool, key=_observation_display_key))
    return tuple(selected)


def _observation_display_key(observation):
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    return (
        observation.definition_version,
        _version_key(observation.calculation_version),
        observation.captured_at or minimum,
        observation.source_timestamp or minimum,
        str(observation.value),
    )


def _version_key(value):
    parts = []
    for part in str(value).replace("-", ".").split("."):
        parts.append((0, int(part)) if part.isdigit() else (1, part))
    return tuple(parts)


def _group(observations):
    result = defaultdict(list)
    for item in observations:
        result[str(item.value)].append(item)
    return {key: tuple(value) for key, value in result.items()}


def _fixed_bins(observations, bins):
    ordered = tuple(sorted(bins))
    result = defaultdict(list)
    for item in observations:
        if not isinstance(item.value, (Decimal, int, float)) or isinstance(item.value, bool):
            continue
        value = Decimal(str(item.value))
        index = next((index for index, edge in enumerate(ordered) if value <= edge), len(ordered))
        result[index].append(item)
    return {key: tuple(value) for key, value in result.items()}

"""GEO-U1 Slice G0: Geometry calibration-population eligibility gate.

DIAGNOSTIC ONLY; nothing in production imports it and it calibrates nothing.
Eligibility depends solely on pinned public Bybit instrument metadata
(``contractType``, ``quoteCoin``, ``symbolType``) - never on a ticker's
appearance, terminal width trend or any SHADOW/production result.

Policy v1 (target = crypto Bybit USDT linear perpetuals):
- CRYPTO_LINEAR_PERPETUAL (symbolType "" or "innovation") -> eligible;
- EQUITY_LINKED_LINEAR (symbolType "stock" or "ETF") and OTHER_LINEAR
  ("commodity", "forex") -> separate populations, not eligible for the crypto
  calibration (their evidence is kept and reported, not deleted);
- UNKNOWN (missing metadata, non-USDT, non-perpetual, unseen symbolType)
  -> fails closed.
"""

from dataclasses import dataclass

from .consensus_evidence_readiness import assess_geometry_evidence_readiness

CRYPTO_LINEAR_PERPETUAL = "CRYPTO_LINEAR_PERPETUAL"
EQUITY_LINKED_LINEAR = "EQUITY_LINKED_LINEAR"
OTHER_LINEAR = "OTHER_LINEAR"
UNKNOWN = "UNKNOWN"

_SYMBOL_TYPE_CLASS = {
    "": CRYPTO_LINEAR_PERPETUAL,
    "innovation": CRYPTO_LINEAR_PERPETUAL,
    "stock": EQUITY_LINKED_LINEAR,
    "ETF": EQUITY_LINKED_LINEAR,
    "commodity": OTHER_LINEAR,
    "forex": OTHER_LINEAR,
}


@dataclass(frozen=True)
class GeometryCalibrationPopulationPolicy:
    policy_version: str
    target_market: str
    eligible_instrument_classes: tuple[str, ...]
    excluded_instrument_classes: tuple[str, ...]
    unknown_handling: str
    rationale: str
    source: str


POLICY_V1 = GeometryCalibrationPopulationPolicy(
    policy_version="GEO-U1-POP-1",
    target_market="Bybit USDT linear perpetuals on crypto underlyings",
    eligible_instrument_classes=(CRYPTO_LINEAR_PERPETUAL,),
    excluded_instrument_classes=(EQUITY_LINKED_LINEAR, OTHER_LINEAR),
    unknown_handling="UNKNOWN is never eligible (fail closed)",
    rationale=(
        "Equity/ETF-linked and commodity/forex perpetuals track TradFi "
        "underlyings with their own session and microstructure; they are kept "
        "as separate evidence populations instead of being mixed into the "
        "crypto calibration. The rule is per instrument class and is applied "
        "identically to every case regardless of its terminal trend."
    ),
    source=("Bybit v5 public instruments-info symbolType/contractType/quoteCoin, "
            "pinned in tests/fixtures/geometry_gold/instrument_metadata_v1.json"),
)


def instrument_class(metadata):
    """Class from one instrument-info record; anything unproven is UNKNOWN."""
    if not metadata:
        return UNKNOWN
    if (metadata.get("contractType") != "LinearPerpetual"
            or metadata.get("quoteCoin") != "USDT"
            or "symbolType" not in metadata):
        return UNKNOWN
    return _SYMBOL_TYPE_CLASS.get(metadata["symbolType"], UNKNOWN)


def classify_cases(case_instruments, instruments, policy=POLICY_V1):
    """{case_id: {...class, eligible}} from pinned metadata only."""
    result = {}
    for entry in case_instruments:
        metadata = instruments.get(entry["instrument_symbol"])
        klass = instrument_class(metadata)
        result[entry["case_id"]] = {
            "case_id": entry["case_id"],
            "instrument_symbol": entry["instrument_symbol"],
            "symbol_resolution": entry["method"],
            "symbol_type": None if metadata is None else metadata.get("symbolType"),
            "instrument_class": klass,
            "calibration_eligible": klass in policy.eligible_instrument_classes,
        }
    return result


def readiness_by_population(facts, classification, *, newly_recovered_case_ids,
                            provenance_complete_case_ids, unrecoverable_targets,
                            reproduced_case_ids):
    """ALL_LINEAR (historical) and TARGET_POPULATION readiness, side by side.

    Uses the unchanged fixed readiness rule; the target population is a
    class-only filter of the same pinned facts.
    """
    missing = [f["case_id"] for f in facts if f["case_id"] not in classification]
    if missing:
        raise ValueError(f"unclassified cases: {missing}")
    common = dict(newly_recovered_case_ids=newly_recovered_case_ids,
                  provenance_complete_case_ids=provenance_complete_case_ids,
                  unrecoverable_targets=unrecoverable_targets,
                  reproduced_case_ids=reproduced_case_ids)
    target = [f for f in facts if classification[f["case_id"]]["calibration_eligible"]]
    return {
        "ALL_LINEAR": assess_geometry_evidence_readiness(facts, **common),
        "TARGET_POPULATION": assess_geometry_evidence_readiness(target, **common),
    }

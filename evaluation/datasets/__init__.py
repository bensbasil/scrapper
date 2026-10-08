"""
evaluation/datasets/__init__.py
-------------------------------
Synthetic test fixtures and evaluation datasets.
"""

from evaluation.datasets.fixtures import (
    get_strong_evidence_good_reasoning_fixture,
    get_strong_evidence_poor_reasoning_fixture,
    get_unsupported_hallucination_fixture,
    get_opportunity_consistent_outreach_inconsistent_fixture,
    get_insufficient_evidence_fixture,
    get_deterministic_fallback_fixture,
    get_all_synthetic_fixtures,
)

__all__ = [
    "get_strong_evidence_good_reasoning_fixture",
    "get_strong_evidence_poor_reasoning_fixture",
    "get_unsupported_hallucination_fixture",
    "get_opportunity_consistent_outreach_inconsistent_fixture",
    "get_insufficient_evidence_fixture",
    "get_deterministic_fallback_fixture",
    "get_all_synthetic_fixtures",
]

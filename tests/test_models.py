from datetime import date, datetime, timezone

from app.domain import Classification, Confidence
from app.storage.models import Recommendation, Snapshot


def test_snapshot_roundtrip(session_factory):
    with session_factory() as s:
        s.add(
            Snapshot(
                run_date=date(2026, 7, 10),
                kind="holdings",
                source="mock",
                payload=[{"tradingsymbol": "TCS", "quantity": 20}],
                fetched_at=datetime.now(timezone.utc),
            )
        )
        s.commit()

    with session_factory() as s:
        snap = s.query(Snapshot).one()
        assert snap.source == "mock"
        assert snap.payload[0]["tradingsymbol"] == "TCS"  # JSON survives the roundtrip


def test_recommendation_uses_bounded_vocabulary(session_factory):
    with session_factory() as s:
        s.add(
            Recommendation(
                run_date=date(2026, 7, 10),
                symbol="INFY",
                classification=Classification.WATCH.value,
                confidence=Confidence.MEDIUM.value,
                reason="Guidance uncertainty; monitor next results.",
                evidence=[{"type": "results", "url": "https://example.com"}],
                prev_classification=Classification.HOLD.value,
            )
        )
        s.commit()

    with session_factory() as s:
        rec = s.query(Recommendation).one()
        assert rec.classification == "Watch"
        assert rec.prev_classification == "Hold"  # enables the "what changed" diff

"""Deterministic price exits, and the partial-update semantics that keep them alive."""

from app.reasoning.scoring import price_trigger


def test_price_trigger_boundaries():
    meta = {"stop_below": 275, "take_above": 450}
    assert price_trigger(meta, 286.85) is None          # JAINREC as bought — no trigger
    assert price_trigger(meta, 275.01) is None
    assert "stop" in price_trigger(meta, 275)           # inclusive at the stop
    assert "stop" in price_trigger(meta, 274.99)
    assert "target" in price_trigger(meta, 450)         # inclusive at the target
    assert "target" in price_trigger(meta, 451)


def test_stop_outranks_target_if_both_somehow_trip():
    # Nonsensical config (stop above target) must still prefer capital preservation.
    assert "stop" in price_trigger({"stop_below": 500, "take_above": 100}, 300)


def test_price_trigger_is_inert_without_thresholds_or_price():
    assert price_trigger(None, 100) is None
    assert price_trigger({}, 100) is None
    assert price_trigger({"exit_if": ["something"]}, 100) is None   # free text alone never fires
    assert price_trigger({"stop_below": 275}, None) is None
    assert price_trigger({"stop_below": "not-a-number"}, 100) is None
    assert price_trigger({"stop_below": 275}, "not-a-number") is None


def test_triggered_stop_forces_exit_candidate_without_an_llm():
    """The whole point: this must not depend on the LLM layer running at all."""
    from app.domain import Classification
    from app.reasoning.scoring import score_holding

    meta = {"thesis": "copper recycling", "stop_below": 275, "take_above": 450, "exit_if": []}
    res = score_holding({"symbol": "JAINREC", "ltp": 270.0, "weight_pct": 20.0},
                        None, None, None, meta, None, {})
    assert res["classification"] == Classification.EXIT.value
    assert any("OVERRIDE" in r and "stop" in r for r in res["reasons"])

    # ...and stays quiet when the price is inside the band.
    ok = score_holding({"symbol": "JAINREC", "ltp": 286.85, "weight_pct": 20.0},
                       None, None, None, meta, None, {})
    assert not any("OVERRIDE → Exit: price" in r for r in ok["reasons"])


def test_editing_thesis_text_does_not_wipe_the_stop(tmp_path):
    """The dangerous case: the iOS app PUTs the fields it knows about. A replace-everything
    upsert would null stop_below every time someone edited the thesis text."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.reasoning.theses import load_theses_from_db, upsert_thesis
    from app.storage.models import Base

    engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine)

    upsert_thesis(sf, "JAINREC", {"thesis": "copper recycling", "stop_below": 275,
                                  "take_above": 450, "exit_if": ["a"]})
    # An app-style edit that knows nothing about the thresholds:
    upsert_thesis(sf, "JAINREC", {"thesis": "copper recycling, revised", "exit_if": ["a", "b"]})

    meta = load_theses_from_db(sf)["JAINREC"]
    assert meta["thesis"] == "copper recycling, revised"
    assert meta["exit_if"] == ["a", "b"]
    assert meta["stop_below"] == 275, "editing the thesis text silently wiped the stop loss"
    assert meta["take_above"] == 450

    # Explicitly passing None still clears it.
    upsert_thesis(sf, "JAINREC", {"stop_below": None})
    assert load_theses_from_db(sf)["JAINREC"]["stop_below"] is None


def test_export_theses_round_trips_through_yaml(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.reasoning.theses import export_theses_to_yaml, load_theses, seed_theses_from_yaml
    from app.storage.models import Base

    engine = create_engine(f"sqlite:///{tmp_path}/t.db")
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine)
    upsert_thesis = __import__("app.reasoning.theses", fromlist=["upsert_thesis"]).upsert_thesis
    upsert_thesis(sf, "JAINREC", {"thesis": "copper recycling ₹500", "bought_reason": "a friend",
                                  "conviction": "medium", "exit_if": ["below 275"],
                                  "stop_below": 275, "take_above": 450})
    upsert_thesis(sf, "TCS", {"thesis": "", "exit_if": []})

    out = tmp_path / "theses.yaml"
    assert export_theses_to_yaml(sf, out) == 2

    y = load_theses(out)
    assert set(y) == {"JAINREC", "TCS"}
    assert y["JAINREC"]["stop_below"] == 275 and y["JAINREC"]["take_above"] == 450
    assert "₹500" in y["JAINREC"]["thesis"]          # unicode survives
    assert "stop_below" not in y["TCS"]              # unset thresholds stay out of the file

    # and it re-seeds a fresh DB faithfully
    engine2 = create_engine(f"sqlite:///{tmp_path}/t2.db")
    Base.metadata.create_all(engine2)
    sf2 = sessionmaker(bind=engine2)
    assert seed_theses_from_yaml(sf2, out) == 2
    from app.reasoning.theses import load_theses_from_db
    assert load_theses_from_db(sf2)["JAINREC"]["exit_if"] == ["below 275"]

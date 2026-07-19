"""Offline smoke test: schema creation + scoring on mock snapshots (no network).

Run: python scripts/smoke_test.py
Uses a temporary SQLite DB so it never touches your real data.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# temp sqlite DB before importing anything that reads settings
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.db.models import App, AppSnapshot, Category  # noqa: E402
from src.db.session import init_db, session_scope  # noqa: E402
from src.scraper.ingest import ensure_categories  # noqa: E402
from src.analysis.opportunity import compute_and_store  # noqa: E402


def seed_mock_data() -> None:
    init_db()
    with session_scope() as s:
        ensure_categories(s)

    # Two contrasting niches:
    #  6007 Productivity: high demand, MEDIOCRE ratings -> big opportunity
    #  6011 Music: high demand, GREAT ratings + fortresses -> low opportunity
    mock = {
        6007: [(4.9, 800000), (3.1, 40000), (3.4, 25000), (2.9, 12000), (3.0, 9000)],
        6011: [(4.8, 900000), (4.7, 500000), (4.9, 600000), (4.6, 300000), (4.8, 250000)],
    }
    with session_scope() as s:
        app_id = 1000
        for genre_id, rows in mock.items():
            for rating, count in rows:
                app_id += 1
                s.add(App(id=app_id, name=f"App {app_id}", genre_id=genre_id))
                s.add(
                    AppSnapshot(
                        app_id=app_id,
                        genre_id=genre_id,
                        chart_type="topfreeapplications",
                        rank=1,
                        rating_avg=rating,
                        rating_count=count,
                    )
                )


def main() -> int:
    seed_mock_data()
    scored = compute_and_store()
    assert scored, "No scores computed!"
    print("\n=== Opportunity ranking (mock data) ===")
    for s in scored:
        print(
            f"{s.aggregate.name:20s} opp={s.opportunity_score:6.2f} "
            f"gap={s.quality_gap_score:.2f} sat={s.low_saturation_score:.2f} "
            f"success={s.marketing.success_probability:.2f} "
            f"installs/mo={s.marketing.est_installs_month}"
        )

    prod = next(s for s in scored if s.aggregate.genre_id == 6007)
    music = next(s for s in scored if s.aggregate.genre_id == 6011)
    assert prod.opportunity_score > music.opportunity_score, (
        "Productivity (weak incumbents) should outrank Music (fortresses)!"
    )
    assert prod.quality_gap_score > music.quality_gap_score
    print("\nSMOKE TEST PASSED: weak-incumbent niche correctly ranked above fortress niche.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

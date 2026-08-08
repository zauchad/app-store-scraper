"""SQLAlchemy models.

Design principle: every table is here to feed a *business conclusion*, not just
to store raw data. Notes on each table explain the analytical purpose.

Kept intentionally DB-agnostic (no Postgres-only types) so the exact same models
run on local SQLite and on Supabase Postgres.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Category(Base):
    """App Store category (Apple genre).

    Analytical purpose: the unit of niche discovery. `enabled=False` lets us
    exclude capital-heavy verticals (e.g. Games) from opportunity ranking.
    """

    __tablename__ = "categories"

    genre_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    is_games: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Base cost-per-install benchmark (USD) for this vertical -> marketing math.
    base_cpi_usd: Mapped[float] = mapped_column(Float, default=3.0)

    apps: Mapped[list["App"]] = relationship(back_populates="category")


class App(Base):
    """An app we track. Identity that persists across daily snapshots."""

    __tablename__ = "apps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # Apple track id
    name: Mapped[str] = mapped_column(String(512))
    developer: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    genre_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("categories.genre_id"), nullable=True, index=True
    )
    price: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    icon_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    # Free signals from Lookup: app age + update cadence ("abandoned fort").
    release_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    current_version_release_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    # Publisher identity -> developer-concentration analysis (1 firm w/ 10 apps
    # is a very different niche than 10 independent firms).
    artist_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # All genres the app ranks in -> cross-category positioning ("styk kategorii").
    genre_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Supported languages -> localization-gap analysis (English-only = opening).
    language_codes: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    screenshot_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ipad_screenshot_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_size_mb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    minimum_os_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    content_rating: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # What the incumbent just shipped (competitive feature velocity).
    release_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    category: Mapped[Optional[Category]] = relationship(back_populates="apps")
    snapshots: Mapped[list["AppSnapshot"]] = relationship(back_populates="app")


class AppSnapshot(Base):
    """Point-in-time metrics for an app in a chart.

    Analytical purpose: THIS is the time series. Comparing snapshots day over day
    gives us *momentum* (rank change, review velocity) - the single best signal
    to separate a real emerging niche from static noise.
    """

    __tablename__ = "app_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("apps.id"), index=True)
    genre_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    chart_type: Mapped[str] = mapped_column(String(48))
    # Chart membership this run (an app can rank in several charts; chart_type
    # keeps only the best-rank one). Grossing membership = the free
    # "people actually PAY for this" monetization proxy.
    in_free_chart: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    in_grossing_chart: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rating_avg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rating_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Current-version rating vs lifetime: the freshest free "app is getting
    # worse/better RIGHT NOW" signal, no history needed.
    rating_avg_current: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rating_count_current: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Update cadence at scan time -> lets us compute "days since last update".
    current_version_release_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), index=True
    )

    app: Mapped[App] = relationship(back_populates="snapshots")


class Review(Base):
    """A customer review. Raw fuel for the LLM intelligence layer.

    Analytical purpose: pain points, missing features and sentiment are mined
    from here (esp. 1-3 star reviews) to produce actionable product direction.
    """

    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # Apple review id
    app_id: Mapped[int] = mapped_column(ForeignKey("apps.id"), index=True)
    author: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rating: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    review_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class CategoryScore(Base):
    """Quantitative opportunity metrics per category, per run (Level 1).

    Analytical purpose: the daily, LLM-free heatmap. Answers "where is demand
    high AND incumbent quality low AND saturation low AND momentum positive?"
    Plus the marketing feasibility layer (can my budget realistically compete?).
    """

    __tablename__ = "category_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    genre_id: Mapped[int] = mapped_column(ForeignKey("categories.genre_id"), index=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), index=True
    )

    # Raw aggregates (auditable)
    num_apps: Mapped[int] = mapped_column(Integer, default=0)
    avg_rating_top: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_rating_count: Mapped[int] = mapped_column(Integer, default=0)
    median_rating_count: Mapped[int] = mapped_column(Integer, default=0)
    num_strong_incumbents: Mapped[int] = mapped_column(Integer, default=0)
    num_mega_incumbents: Mapped[int] = mapped_column(Integer, default=0)
    # Update cadence: how many top incumbents look "abandoned" (>12m no update)
    # and the median days-since-update across the niche. Stale forts = openings.
    num_stale_incumbents: Mapped[int] = mapped_column(Integer, default=0)
    median_days_since_update: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    # Publisher concentration: distinct developers + share of ratings held by
    # the single biggest publisher (near 1.0 = one firm owns the niche).
    num_developers: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    top_dev_share: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Localization gap: share of sizeable incumbents shipping English-only.
    english_only_share: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # How many sizeable incumbents rate visibly worse on the CURRENT version
    # than lifetime (users souring right now = fresh opening).
    num_declining_incumbents: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    # Monetization proxies: share of top-free apps that ALSO rank in
    # top-grossing (freemium works here), and share of paid apps in the top.
    monetization_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    paid_share: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Market fluidity: share of top apps released in the last ~2 years.
    # High = newcomers break in; low = ossified, incumbent-locked market.
    newcomer_share: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Normalised 0..1 component scores
    demand_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_gap_score: Mapped[float] = mapped_column(Float, default=0.0)
    low_saturation_score: Mapped[float] = mapped_column(Float, default=0.0)
    momentum_score: Mapped[float] = mapped_column(Float, default=0.0)
    # Avg rank improvement across the niche (breakout pressure); needs history.
    rank_momentum: Mapped[float] = mapped_column(Float, default=0.0)
    # 0..1 multiplier: can a lean founder realistically compete here?
    contestability: Mapped[float] = mapped_column(Float, default=1.0)

    # Final 0..100
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    # Marketing feasibility
    est_cpi_pln: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    est_installs_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    marketing_cost_pln: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    success_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Keyword(Base):
    """A candidate micro-niche expressed as an App Store search term.

    Analytical purpose: top charts are owned by giants, so real openings live at
    the keyword / long-tail level. A keyword is a *hypothesis* ("sleep tracker
    for shift workers") that we then validate quantitatively via the Search API.
    """

    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term: Mapped[str] = mapped_column(String(256), index=True)
    genre_id: Mapped[Optional[int]] = mapped_column(Integer, index=True, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="manual")  # manual|llm|seed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class KeywordScore(Base):
    """Quantitative micro-niche score for a keyword, per run.

    Same model as categories (Opportunity = attractiveness x contestability) but
    computed on the apps that actually rank for the term - so it answers: "is
    THIS specific niche winnable by a lean founder?"
    """

    __tablename__ = "keyword_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), index=True)
    term: Mapped[str] = mapped_column(String(256), index=True)  # denormalised
    genre_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), index=True
    )

    num_results: Mapped[int] = mapped_column(Integer, default=0)
    avg_rating_top: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    median_rating_count: Mapped[int] = mapped_column(Integer, default=0)
    total_rating_count: Mapped[int] = mapped_column(Integer, default=0)
    num_strong_incumbents: Mapped[int] = mapped_column(Integer, default=0)
    num_mega_incumbents: Mapped[int] = mapped_column(Integer, default=0)

    demand_score: Mapped[float] = mapped_column(Float, default=0.0)
    quality_gap_score: Mapped[float] = mapped_column(Float, default=0.0)
    low_saturation_score: Mapped[float] = mapped_column(Float, default=0.0)
    contestability: Mapped[float] = mapped_column(Float, default=1.0)
    # 0..1 search-interest proxy (autocomplete popularity); None if unknown.
    search_interest: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # 0..1 ASO difficulty of out-ranking apps already on this term.
    difficulty: Mapped[float] = mapped_column(Float, default=0.0)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    est_cpi_pln: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    est_installs_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    marketing_cost_pln: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    success_probability: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Snapshot of the top competing apps (name, developer, rating, count).
    top_apps: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)


class CategoryInsight(Base):
    """LLM-generated synthesis per category (Level 2 - the expensive step).

    Analytical purpose: turns hundreds of reviews into an Executive Summary,
    clustered pain points, missing features and a concrete suggested direction
    for *your* app. This is the deliverable the dashboard shows.
    """

    __tablename__ = "category_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    genre_id: Mapped[int] = mapped_column(ForeignKey("categories.genre_id"), index=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), index=True
    )
    llm_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reviews_analyzed: Mapped[int] = mapped_column(Integer, default=0)

    executive_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    market_saturation_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_direction: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Lists of {label, description, frequency/severity}
    pain_points: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    missing_features: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

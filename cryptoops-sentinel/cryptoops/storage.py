"""SQLAlchemy snapshot store (SQLite locally; PostgreSQL via Docker)."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Integer, Numeric, String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from cryptoops.config import DATABASE_URL, MAX_SNAPSHOT_AGE_SECONDS

# Persisted ingestion is initially configured for the three demo portfolio assets.
MONITORED_SYMBOLS = ("BTC", "ETH", "SOL")


class Base(DeclarativeBase):
    pass


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(12), index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    price_usd: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    bid_usd: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    ask_usd: Mapped[Decimal] = mapped_column(Numeric(30, 10))
    volume_base_24h: Mapped[Decimal] = mapped_column(Numeric(30, 10))


engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def initialize_database() -> None:
    Base.metadata.create_all(engine)


def save_tickers(tickers: list[dict[str, Any]], *, captured_at: datetime | None = None) -> int:
    """Persist one refresh batch with a single commit; never delete prior snapshots."""
    now = captured_at or datetime.now(UTC)
    with Session(engine) as session:
        for ticker in tickers:
            session.add(
                MarketSnapshot(
                    symbol=ticker["symbol"],
                    source=ticker["source"],
                    captured_at=now,
                    price_usd=Decimal(str(ticker["price_usd"])),
                    bid_usd=Decimal(str(ticker["bid_usd"])),
                    ask_usd=Decimal(str(ticker["ask_usd"])),
                    volume_base_24h=Decimal(str(ticker["volume_base_24h"])),
                )
            )
        session.commit()
    return len(tickers)


def get_operations_status() -> dict[str, Any]:
    now = datetime.now(UTC)
    with Session(engine) as session:
        count = session.scalar(select(func.count()).select_from(MarketSnapshot)) or 0
        latest = []
        for symbol in MONITORED_SYMBOLS:
            snap = session.scalar(
                select(MarketSnapshot)
                .where(MarketSnapshot.symbol == symbol)
                .order_by(MarketSnapshot.captured_at.desc(), MarketSnapshot.id.desc())
                .limit(1)
            )
            if snap is None:
                latest.append({"symbol": symbol, "status": "NOT_STARTED", "age_seconds": None})
                continue
            captured = snap.captured_at
            if captured.tzinfo is None:
                captured = captured.replace(tzinfo=UTC)
            age = max(0, int((now - captured).total_seconds()))
            latest.append(
                {
                    "symbol": symbol,
                    "status": "FRESH" if age <= MAX_SNAPSHOT_AGE_SECONDS else "STALE",
                    "age_seconds": age,
                    "last_ingested_at_utc": captured.isoformat(),
                    "last_stored_price_usd": float(snap.price_usd),
                }
            )
    statuses = {item["status"] for item in latest}
    overall_status = (
        "NOT_STARTED"
        if "NOT_STARTED" in statuses
        else "STALE" if "STALE" in statuses else "FRESH"
    )
    return {
        "overall_status": overall_status,
        "total_snapshot_records": count,
        "max_snapshot_age_seconds": MAX_SNAPSHOT_AGE_SECONDS,
        "data_source": "Kraken public Spot REST API",
        "latest_by_symbol": latest,
        "note": (
            "Age describes locally persisted ingestion records, not exchange feed availability. "
            "Run `python -m cryptoops.ingest --once` to capture snapshots. "
            "The MVP does not run an automatic scheduler."
        ),
    }

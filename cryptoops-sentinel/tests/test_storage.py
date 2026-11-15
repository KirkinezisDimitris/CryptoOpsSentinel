from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine

from cryptoops import storage


def test_atomic_snapshot_persistence_and_age(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(storage, "engine", engine)
    storage.initialize_database()
    sample = [
        {
            "symbol": symbol, "source": "Mock Kraken", "price_usd": 100,
            "bid_usd": 99, "ask_usd": 101, "volume_base_24h": 900,
        }
        for symbol in ("BTC", "ETH", "SOL")
    ]
    assert storage.save_tickers(sample) == 3
    status = storage.get_operations_status()
    assert status["total_snapshot_records"] == 3
    assert status["overall_status"] == "FRESH"

    old_batch = datetime.now(UTC) - timedelta(hours=2)
    storage.save_tickers(sample, captured_at=old_batch)
    assert storage.get_operations_status()["overall_status"] == "FRESH"
    assert storage.get_operations_status()["total_snapshot_records"] == 6
    engine.dispose()


def test_not_started_is_reported_correctly(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    monkeypatch.setattr(storage, "engine", engine)
    storage.initialize_database()
    status = storage.get_operations_status()
    assert status["overall_status"] == "NOT_STARTED"
    assert status["total_snapshot_records"] == 0
    engine.dispose()


def test_old_snapshots_are_marked_stale(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    monkeypatch.setattr(storage, "engine", engine)
    storage.initialize_database()
    sample = [
        {
            "symbol": symbol, "source": "Fixture", "price_usd": 100,
            "bid_usd": 99, "ask_usd": 101, "volume_base_24h": 10,
        }
        for symbol in ("BTC", "ETH", "SOL")
    ]
    storage.save_tickers(sample, captured_at=datetime.now(UTC) - timedelta(days=1))
    assert storage.get_operations_status()["overall_status"] == "STALE"
    engine.dispose()

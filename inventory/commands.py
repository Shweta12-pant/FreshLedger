import argparse
import logging
import os
import time
from csv import Error as CSVError
from datetime import date
from pathlib import Path

from sqlalchemy.engine import Engine

from .db import build_engine, store_now, transaction
from .forecast import run_forecast
from .import_sales import import_sales
from .models import Base, StoreSetting
from .seed import seed_demo

log = logging.getLogger("freshledger")


def initialize(engine: Engine, *, demo: bool, today: date) -> None:
    Base.metadata.create_all(engine)
    with transaction(engine, write=True) as session:
        existing = session.get(StoreSetting, "data_mode")
        if existing is not None:
            log.info("Existing %s workspace kept.", existing.value)
            return
        session.add(StoreSetting(name="data_mode", value="demo" if demo else "live"))
        if demo:
            seed_demo(session, today)
        log.info("Initialized a %s workspace.", "demo" if demo else "live")


def work(engine: Engine) -> None:
    last_day = None
    interval = int(os.getenv("FORECAST_POLL_SECONDS", "60"))
    if interval < 1:
        raise ValueError("FORECAST_POLL_SECONDS must be positive.")
    while True:
        today = store_now().date()
        if last_day != today:
            try:
                count = run_forecast(engine, today)
            except Exception:
                log.exception("Forecast failed. The worker will retry.")
            else:
                last_day = today
                log.info("Forecast available for %s with %d products.", today, count)
        time.sleep(interval)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="FreshLedger database and forecasting commands")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument(
        "--demo", action="store_true", help="Seed synthetic data during first initialization"
    )
    commands.add_parser("forecast")
    commands.add_parser("worker")
    importer = commands.add_parser("import-sales")
    importer.add_argument("file", type=Path)
    args = parser.parse_args()
    engine = build_engine()
    try:
        if args.command == "init":
            initialize(
                engine, demo=args.demo or os.getenv("SEED_DEMO", "0") == "1", today=store_now().date()
            )
        elif args.command == "forecast":
            count = run_forecast(engine, store_now().date(), force=True)
            log.info("Published forecasts for %d products.", count)
        elif args.command == "import-sales":
            try:
                with transaction(engine, write=True) as session:
                    inserted, unchanged = import_sales(session, args.file, store_now().date())
            except (OSError, ValueError, CSVError) as exc:
                parser.exit(1, f"Import failed: {exc}\n")
            log.info("Imported %d sales rows. Kept %d identical rows.", inserted, unchanged)
        else:
            work(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

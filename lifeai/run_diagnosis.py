"""Optional, schedulable, no-network V3 diagnosis; no code execution."""
import json
from dotenv import load_dotenv
from lifeai.config import Settings
from lifeai.db import build_engine, session
from lifeai.evolution import diagnose


def main():
    load_dotenv()
    cfg = Settings.from_env()
    cfg.validate()
    engine = build_engine(cfg.database_url)
    try:
        with session(engine) as db:
            result = diagnose(db, once_per_utc_day=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

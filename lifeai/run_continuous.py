"""Docker-safe daily V3.3 cycle, no code execution or network calls."""
import json
from dotenv import load_dotenv
from .config import Settings
from .db import build_engine, session
from .continuous import run_continuous_cycle


def main():
    load_dotenv()
    cfg = Settings.from_env()
    cfg.validate()
    engine = build_engine(cfg.database_url)
    try:
        with session(engine) as db:
            print(json.dumps(run_continuous_cycle(db, revision=cfg.code_revision),
                             ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

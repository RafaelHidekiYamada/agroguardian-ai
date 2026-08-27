"""Run the idempotent AgroGuardian development seed.

Required environment variables only when the database has no ADMIN account:
INITIAL_ADMIN_USERNAME, INITIAL_ADMIN_EMAIL and INITIAL_ADMIN_PASSWORD.
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.database_seed import SeedConfigurationError, seed_database_from_environment


def main() -> int:
    try:
        result = seed_database_from_environment()
    except SeedConfigurationError as error:
        print(f"Seed nao executado: {error}")
        return 2
    print("Seed concluido com sucesso.")
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations
import json
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.config import settings

OUTPUT_DIR = ROOT_DIR / "data_science_r" / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_CSV = OUTPUT_DIR / "agroguardian_predictions.csv"


def main():
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    try:
        with engine.connect() as connection:
            df = pd.read_sql_query(
                text(
                    """
            SELECT
                id,
                timestamp,
                model_version,
                source,
                predicted_risk,
                risk_label,
                alert_level,
                recommendation,
                input_payload,
                weather_payload
            FROM prediction_records
                    """
                ),
                connection,
            )

        expanded_rows = []

        for _, row in df.iterrows():
            payload = row["input_payload"]
            weather = row["weather_payload"]

            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            elif payload is None:
                payload = {}

            if isinstance(weather, str):
                try:
                    weather = json.loads(weather)
                except Exception:
                    weather = {}
            elif weather is None:
                weather = {}

            base = row.to_dict()
            base.pop("input_payload", None)
            base.pop("weather_payload", None)

            for k, v in payload.items():
                base[f"input_{k}"] = v

            for k, v in weather.items():
                base[f"weather_{k}"] = v

            expanded_rows.append(base)

        final_df = pd.DataFrame(expanded_rows)
        final_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8")
        print(f"Dataset exportado com sucesso para: {OUTPUT_CSV}")
        print(f"Total de linhas exportadas: {len(final_df)}")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

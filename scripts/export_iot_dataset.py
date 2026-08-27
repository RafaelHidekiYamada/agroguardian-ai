"""Export canonical ESP32 telemetry for supervised-model training."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.database import SessionLocal
from backend.iot_dataset import export_equipment_telemetry_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta telemetria ESP32 sem payload bruto ou credenciais.")
    parser.add_argument("--equipment-id", type=int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        output_path = export_equipment_telemetry_dataset(db, args.equipment_id, args.output)
    finally:
        db.close()

    print(f"Dataset IoT exportado para: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

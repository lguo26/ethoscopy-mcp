"""Generate a small, entirely synthetic two-recording Ethoscopy dataset."""

from __future__ import annotations

from pathlib import Path

import ethoscopy as etho
import pandas as pd


HERE = Path(__file__).resolve().parent
GENERATED = HERE / "generated"


def main() -> tuple[Path, Path, Path]:
    GENERATED.mkdir(exist_ok=True)
    first_specs = (
        ("ETHOSCOPE_074", "074250", "01", True),
        ("ETHOSCOPE_074", "074250", "02", True),
        ("ETHOSCOPE_316", "316250", "01", False),
        ("ETHOSCOPE_316", "316250", "02", False),
    )
    second_specs = (
        ("ETHOSCOPE_316", "316250", "01", True),
        ("ETHOSCOPE_316", "316250", "02", True),
        ("ETHOSCOPE_074", "074250", "01", False),
        ("ETHOSCOPE_074", "074250", "02", False),
    )
    canonical = {
        ("2026-01-01", "ETHOSCOPE_074"): ("ETHOSCOPE_074", "074250"),
        ("2026-01-01", "ETHOSCOPE_316"): ("ETHOSCOPE_316", "316250"),
        ("2026-01-02", "ETHOSCOPE_316"): ("ETHOSCOPE_074", "074250"),
        ("2026-01-02", "ETHOSCOPE_074"): ("ETHOSCOPE_316", "316250"),
    }

    mapping_rows: list[dict] = []
    pickle_paths: list[Path] = []
    for date, baseline, specs, filename in (
        ("2026-01-01", 0, first_specs, "synthetic_day_1.pkl"),
        ("2026-01-02", 1, second_specs, "synthetic_day_2.pkl"),
    ):
        data_rows: list[dict] = []
        metadata_rows: list[dict] = []
        for machine, token, roi, infection in specs:
            original_id = f"{date}_00-00-00_{token}|{roi}"
            canonical_machine, canonical_token = canonical[(date, machine)]
            analysis_id = f"{date}_00-00-00_{canonical_token}|{roi}"
            for time in range(0, 24 * 3600, 10):
                dies = infection and roi == "01" and (
                    baseline == 1 or time >= 12 * 3600
                )
                data_rows.append(
                    {
                        "id": original_id,
                        "t": time,
                        "moving": not dies,
                        "walk": not dies,
                    }
                )
            metadata_rows.append(
                {
                    "id": original_id,
                    "date": date,
                    "machine_name": machine,
                    "region_id": int(roi),
                    "sex": "male",
                    "infection": infection,
                    "baseline": baseline,
                    "temperature": 25,
                }
            )
            mapping_rows.append(
                {
                    "original_id": original_id,
                    "analysis_id": analysis_id,
                    "date": date,
                    "original_machine": machine,
                    "canonical_machine": canonical_machine,
                    "roi": roi,
                    "sex": "male",
                    "infection": infection,
                }
            )

        data = pd.DataFrame(data_rows).set_index("id")
        metadata = pd.DataFrame(metadata_rows).set_index("id")
        pickle_path = GENERATED / filename
        etho.behavpy(data, metadata, canvas=None, check=True).to_pickle(pickle_path)
        metadata.reset_index().to_csv(
            GENERATED / f"{pickle_path.stem}_metadata.csv", index=False
        )
        pickle_paths.append(pickle_path)

    mapping_path = GENERATED / "identity_overlay.csv"
    pd.DataFrame(mapping_rows).to_csv(mapping_path, index=False)
    return pickle_paths[0], pickle_paths[1], mapping_path


if __name__ == "__main__":
    first, second, mapping = main()
    print(first)
    print(second)
    print(mapping)

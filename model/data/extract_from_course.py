"""
Extract data from the original course Excel into self-contained CSV files.
Run once after cloning; the CSVs in model/data/ are pre-extracted.
"""

import os
import pandas as pd
import numpy as np


def extract(data_dir: str = None):
    """Extract all data from course materials into model/data/. """
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(__file__))

    monthly_billing_dir = os.path.join(data_dir, "monthly_billing")
    os.makedirs(monthly_billing_dir, exist_ok=True)

    base = os.path.dirname(os.path.dirname(os.path.dirname(data_dir)))
    xlsx = os.path.join(base,
        "material-ucema",
        "Clases 4 y 5 - Estrategias de abastecimiento-20260415",
        "TP final",
        "Datos para casos UCEMA x.xlsx")

    if not os.path.exists(xlsx):
        print(f"Source Excel not found at {xlsx}. Skipping extraction.")
        return

    # --- Caso 3: pad 35008 -> 35040 ---
    df3 = pd.read_excel(xlsx, sheet_name="Caso 3")
    vals3 = df3["Potencia (kW)"].values.astype(np.float64)
    padded3 = np.pad(vals3, (0, 35040 - len(vals3)), mode="edge")
    pd.DataFrame({"demand_kw": padded3}).to_csv(
        os.path.join(data_dir, "demand_case_3.csv"), index=False
    )
    print(f"Caso 3: {len(vals3)} -> {len(padded3)}")

    # --- Caso 10: truncate 38016 -> 35040 ---
    df10 = pd.read_excel(xlsx, sheet_name="Caso 10")
    vals10 = df10["Potencia Activa kW"].values.astype(np.float64)
    trunc10 = vals10[:35040]
    pd.DataFrame({"demand_kw": trunc10}).to_csv(
        os.path.join(data_dir, "demand_case_10.csv"), index=False
    )
    print(f"Caso 10: {len(vals10)} -> {len(trunc10)}")

    # --- Monthly billing cases ---
    for case, sheet in [("1", "Caso 1"), ("2", "Caso 2"),
                        ("6", "Caso 6"), ("7", "Caso 7"), ("9", "Caso 9")]:
        df = pd.read_excel(xlsx, sheet_name=sheet)
        df.to_csv(os.path.join(monthly_billing_dir, f"caso_{case}.csv"), index=False)
        print(f"Caso {case}: {df.shape}")

    # --- Solar irradiance (reference CSV) ---
    T = 35040
    t = np.arange(T)
    hour = (t // 4) % 24
    day = t // 96
    np.random.seed(42)
    day_angle = 2 * np.pi * (day - 80) / 365
    declination = 23.45 * np.cos(day_angle) * np.pi / 180
    latitude = -31.4 * np.pi / 180
    hour_angle = 15 * (hour - 12) * np.pi / 180
    sin_elev = np.sin(latitude) * np.sin(declination) + \
               np.cos(latitude) * np.cos(declination) * np.cos(hour_angle)
    ghi = np.maximum(sin_elev, 0)
    ghi = ghi / np.max(ghi)
    cloud = np.random.beta(2, 5, T)
    ghi_cloudy = ghi * (1 - 0.3 * cloud)
    pd.DataFrame({"solar_factor": ghi_cloudy}).to_csv(
        os.path.join(data_dir, "solar_irradiance_cordoba.csv"), index=False
    )
    print(f"Solar: {len(ghi_cloudy)} rows")

    print("Done. All data extracted to", data_dir)


if __name__ == "__main__":
    extract()

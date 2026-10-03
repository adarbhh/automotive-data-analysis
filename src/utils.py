# -*- coding: utf-8 -*-
"""
Shared helpers for the analysis scripts: project paths and small save functions.
"""

import json
import os

import matplotlib
matplotlib.use("Agg")  # save figures to files instead of opening windows
import matplotlib.pyplot as plt
import numpy as np

# All paths in the scripts are relative to the project root,
# so the scripts work no matter where they are launched from
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"
FIGURES_DIR = "docs/figures"
TABLES_DIR = "reports/tables"
DASHBOARD_DATA_DIR = "docs/data"

for folder in [PROCESSED_DIR, FIGURES_DIR, TABLES_DIR, DASHBOARD_DATA_DIR]:
    os.makedirs(folder, exist_ok=True)


def save_fig(filename):
    """Save the current matplotlib figure under docs/figures and close it."""
    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, filename), dpi=130)
    plt.close()


def save_table(df, filename, index=False):
    """Save a small summary table under reports/tables."""
    df.to_csv(os.path.join(TABLES_DIR, filename), index=index)


def _to_json(value):
    # numpy numbers are not JSON serializable by default
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if np.isnan(value) else float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return str(value)


def save_dashboard_data(key, data):
    """
    Save the numbers a script produced so the dashboard can show them.
    The file is a small .js file (not .json) so that docs/index.html
    also works when it is opened directly from disk, without a web server.
    """
    path = os.path.join(DASHBOARD_DATA_DIR, f"{key}.js")
    payload = json.dumps(data, default=_to_json, indent=1)
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.DASHBOARD = window.DASHBOARD || {};\n")
        f.write(f"window.DASHBOARD.{key} = {payload};\n")
    print(f"Dashboard data saved to {path}")

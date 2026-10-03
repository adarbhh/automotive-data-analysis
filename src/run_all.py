# -*- coding: utf-8 -*-
"""
Run all the analysis stages in order.
"""

import os
import subprocess
import sys

SRC_DIR = os.path.dirname(os.path.abspath(__file__))

stages = [
    "01_clean_listings.py",
    "02_eda_pricing.py",
    "03_recalls_analysis.py",
    "04_vin_enrichment.py",
    "05_telematics.py",
]

for stage in stages:
    print("\n" + "=" * 70)
    print(f"Running {stage}")
    print("=" * 70)
    # check=True stops the run if a stage fails
    subprocess.run([sys.executable, os.path.join(SRC_DIR, stage)], check=True)

print("\nAll stages finished. Open docs/index.html to see the dashboard.")

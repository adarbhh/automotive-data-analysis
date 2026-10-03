# -*- coding: utf-8 -*-
"""
Stage 1 - Used car listings: ingestion, data quality checks and cleaning.

Input : data/raw/vehicles.csv (Kaggle - Craigslist Cars & Trucks, Austin Reese)
Output: data/processed/usedcars_clean.csv
        reports/tables/missingness.csv, reports/tables/cleaning_audit.csv

@author: Adar
"""

import pandas as pd

from utils import RAW_DIR, PROCESSED_DIR, save_table, save_dashboard_data

RAW_PATH = f"{RAW_DIR}/vehicles.csv"

# --- A1: Ingestion & schema understanding ---

# The raw file is 1.4 GB. Most of that is free text and links
# (description, url, region_url, image_url) that the analysis does not use,
# so these four columns are not loaded.
all_columns = pd.read_csv(RAW_PATH, nrows=0).columns.tolist()
skipped_columns = ['description', 'url', 'region_url', 'image_url']
df = pd.read_csv(RAW_PATH, usecols=[c for c in all_columns if c not in skipped_columns],
                 low_memory=False)

print("--- The data structure (Rows, Columns) ---")
print(f"Columns in the raw file: {len(all_columns)}, loaded: {df.shape[1]}")
print(df.shape)

print("\n--- Data types ---")
print(df.dtypes)

print("\n--- First five rows ---")
print(df.head())

# Numeric columns - ranges (price, year, odometer, coordinates)
print("\n--- Numerical ranges ---")
print(df.describe().loc[['min', 'max']])

# Text columns - how many unique values each one has
print("\n--- Categorical unique counts ---")
for col in df.select_dtypes(include=['object']).columns:
    unique_count = df[col].nunique()
    print(f"{col}: {unique_count} unique values")
    # If there are few values (like fuel), show what they are
    if unique_count < 15:
        print(f"   Values: {df[col].dropna().unique().tolist()}")

total_original = len(df)

# --- A2: Missingness ---

# A price of 0 is not a real price, so it is treated as a missing value
df['price'] = df['price'].where(df['price'] > 0)

# What we decided to do with each column that has missing values
missing_decisions = {
    'county': 'drop column',
    'size': 'drop column',
    'price': 'drop rows',
    'year': 'drop rows',
    'odometer': 'drop rows',
    'cylinders': 'keep as unknown',
    'condition': 'keep as unknown',
    'drive': 'keep as unknown',
    'paint_color': 'keep as unknown',
    'type': 'keep as unknown',
    'manufacturer': 'keep as unknown',
    'model': 'keep as unknown',
    'title_status': 'keep as unknown',
    'fuel': 'keep as unknown',
    'transmission': 'keep as unknown',
    'VIN': 'keep (identifier, left empty)',
    'lat': 'keep (not used)',
    'long': 'keep (not used)',
    'posting_date': 'keep (not used)',
}

missingness = (df.isna().mean() * 100).round(2).sort_values(ascending=False)
missingness = missingness.rename('missing_pct').reset_index().rename(columns={'index': 'column'})
missingness['decision'] = missingness['column'].map(missing_decisions).fillna('keep (complete)')

print("\n--- Missing values percentage per column ---")
print(missingness.to_string(index=False))
save_table(missingness, "missingness.csv")

# Columns that are (almost) empty give no information
df = df.drop(columns=['county', 'size'])

# Categorical columns: a missing value becomes its own category.
# Filling with the most common value would invent data
# (for example it would turn every unknown model into an F-150).
unknown_cols = ['cylinders', 'condition', 'drive', 'paint_color', 'type',
                'manufacturer', 'model', 'title_status', 'fuel', 'transmission']
df[unknown_cols] = df[unknown_cols].fillna('unknown')

# --- A2: Validity rules ---

# The rules are applied one after the other and every removed row is counted
# under the first rule it breaks, so the counts add up to the total removed.
PRICE_MIN, PRICE_MAX = 500, 200000
YEAR_MIN, YEAR_MAX = 1990, 2022
ODOMETER_MAX = 400000

rules = [
    ("Price missing or zero",
     lambda d: d['price'].notna()),
    (f"Price outside ${PRICE_MIN:,} - ${PRICE_MAX:,}",
     lambda d: d['price'].between(PRICE_MIN, PRICE_MAX)),
    (f"Year missing or outside {YEAR_MIN} - {YEAR_MAX}",
     lambda d: d['year'].between(YEAR_MIN, YEAR_MAX)),
    (f"Odometer missing or outside 0 - {ODOMETER_MAX:,} miles",
     lambda d: d['odometer'].between(0, ODOMETER_MAX)),
]

audit = []
df_cleaned = df
for rule_name, is_valid in rules:
    rows_before = len(df_cleaned)
    df_cleaned = df_cleaned[is_valid(df_cleaned)]
    audit.append({'step': rule_name, 'rows_removed': rows_before - len(df_cleaned),
                  'rows_remaining': len(df_cleaned)})

# --- A3: De-duplication ---

# 1. Exact duplicates (identical rows) and duplicate ad IDs
rows_before = len(df_cleaned)
df_cleaned = df_cleaned.drop_duplicates().drop_duplicates(subset=['id'])
audit.append({'step': "Exact duplicate rows / duplicate ad IDs",
              'rows_removed': rows_before - len(df_cleaned), 'rows_remaining': len(df_cleaned)})

# 2. Same vehicle listed more than once (same VIN, usually posted in several regions).
#    Only real VINs are compared - rows without a VIN are all kept at this step.
#    The most recent ad of each vehicle is kept.
rows_before = len(df_cleaned)
df_cleaned = df_cleaned.sort_values('posting_date', ascending=False)
has_vin = df_cleaned['VIN'].notna()
df_cleaned = pd.concat([df_cleaned[has_vin].drop_duplicates(subset=['VIN']),
                        df_cleaned[~has_vin]])
audit.append({'step': "Same vehicle listed again (duplicate VIN)",
              'rows_removed': rows_before - len(df_cleaned), 'rows_remaining': len(df_cleaned)})

# 3. Near-duplicates without a VIN: same car details and same price
#    posted in several regions (typical for dealer ads)
rows_before = len(df_cleaned)
near_dup_keys = ['manufacturer', 'model', 'year', 'odometer', 'price']
has_vin = df_cleaned['VIN'].notna()
df_cleaned = pd.concat([df_cleaned[has_vin],
                        df_cleaned[~has_vin].drop_duplicates(subset=near_dup_keys)])
audit.append({'step': "Same ad reposted without a VIN (same car details and price)",
              'rows_removed': rows_before - len(df_cleaned), 'rows_remaining': len(df_cleaned)})

df_cleaned = df_cleaned.sort_values('id').reset_index(drop=True)

# --- Cleaning audit report ---
audit_df = pd.DataFrame(audit)
audit_df['pct_of_original'] = (audit_df['rows_removed'] / total_original * 100).round(2)

print("\n--- Data cleaning audit report ---")
print(f"Original dataset size: {total_original:,}")
print(audit_df.to_string(index=False))
print(f"Cleaned dataset size: {len(df_cleaned):,} "
      f"({len(df_cleaned) / total_original * 100:.1f}% of the original)")
save_table(audit_df, "cleaning_audit.csv")

# --- A3: Leakage check ---
# Every remaining column is known when the ad is posted (no sale date, no "sold" status),
# so none of them leaks the target. The price column holds asking prices, not sale prices.
print("\nColumns in the cleaned dataset:")
print(df_cleaned.columns.tolist())

# --- Save the clean file ---
df_cleaned.to_csv(f"{PROCESSED_DIR}/usedcars_clean.csv", index=False)
print(f"\nSaved {PROCESSED_DIR}/usedcars_clean.csv")

save_dashboard_data("cleaning", {
    'raw_rows': total_original,
    'clean_rows': len(df_cleaned),
    'raw_columns': len(all_columns),
    'audit': audit_df.to_dict(orient='records'),
    'missingness': missingness[missingness['missing_pct'] > 0].to_dict(orient='records'),
})

# -*- coding: utf-8 -*-
"""
Stage 4 - VIN decoding: enrich a sample of listings with official specs and validate them.

The VIN of a sample of listings is decoded with the NHTSA vPIC API. The decoded
specs are used to (1) fill gaps in the listings and (2) check what the seller typed.

Input : data/processed/usedcars_clean.csv (from stage 1)
Output: data/processed/vin_specs.csv, data/processed/listings_vin_enriched.csv
        reports/tables/vin_*.csv
        data/raw/vin_cache/ (raw API responses, so a re-run does not call the API again)

@author: Adar
"""

import json
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd
import requests

from utils import RAW_DIR, PROCESSED_DIR, save_table, save_dashboard_data

SAMPLE_SIZE = 1000
BATCH_SIZE = 50          # the API accepts up to 50 VINs per request
RANDOM_STATE = 42
CACHE_DIR = f"{RAW_DIR}/vin_cache"
API_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVINValuesBatch/"

os.makedirs(CACHE_DIR, exist_ok=True)

# =============================================================================
# C1: API INGESTION + NORMALIZATION
# =============================================================================

# --- 1. Controlled batch ---
listings = pd.read_csv(f"{PROCESSED_DIR}/usedcars_clean.csv",
                       usecols=['id', 'VIN', 'price', 'year', 'manufacturer', 'model',
                                'fuel', 'drive', 'type'])

# A valid VIN has exactly 17 characters and never uses the letters I, O or Q
listings['VIN'] = listings['VIN'].str.strip().str.upper()
has_vin = listings['VIN'].notna()
valid_vin = listings['VIN'].str.match(r'^[A-HJ-NPR-Z0-9]{17}$', na=False)

print(f"Listings: {len(listings):,}")
print(f"  with a VIN:       {has_vin.sum():,} ({has_vin.mean() * 100:.1f}%)")
print(f"  with a valid VIN: {valid_vin.sum():,} ({valid_vin.mean() * 100:.1f}%)")
print(f"  malformed VINs:   {(has_vin & ~valid_vin).sum():,}")

# Random sample (fixed seed), so the batch represents all the listings that have a VIN
batch = listings[valid_vin].sample(n=SAMPLE_SIZE, random_state=RANDOM_STATE).reset_index(drop=True)

# --- 2. Decode with caching, rate limiting and retries ---

def decode_batch(vins, batch_number):
    """Decode up to 50 VINs in one request. The raw response is cached on disk."""
    cache_path = f"{CACHE_DIR}/batch_{batch_number:03d}.json"
    if os.path.exists(cache_path):
        with open(cache_path, encoding='utf-8') as f:
            return json.load(f)['Results']

    for attempt in range(3):
        try:
            response = requests.post(API_URL, data={'format': 'json', 'data': ';'.join(vins)}, timeout=60)
            response.raise_for_status()
            payload = response.json()
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f)
            time.sleep(1)  # rate limiting - pause between calls
            return payload['Results']
        except Exception as e:
            print(f"  batch {batch_number}: attempt {attempt + 1} failed ({e})")
            time.sleep(5 * (attempt + 1))
    return []  # the VINs of this batch stay undecoded and are reported as failures

print(f"\nDecoding {SAMPLE_SIZE} VINs in batches of {BATCH_SIZE}...")
results = []
for start in range(0, SAMPLE_SIZE, BATCH_SIZE):
    vins = batch['VIN'].iloc[start:start + BATCH_SIZE].tolist()
    results.extend(decode_batch(vins, start // BATCH_SIZE))

# --- 3. Flatten the JSON into one row per VIN, keeping only the fields we use ---
api_fields = {
    'VIN': 'VIN',
    'Make': 'API_Make',
    'Model': 'API_Model',
    'ModelYear': 'API_Year',
    'BodyClass': 'API_Body',
    'DisplacementL': 'API_Engine',
    'DriveType': 'API_Drive',
    'FuelTypePrimary': 'API_Fuel',
    'ErrorCode': 'API_ErrorCode',
}
vin_specs = pd.DataFrame(results)[list(api_fields.keys())].rename(columns=api_fields)
vin_specs = vin_specs.replace('', np.nan).drop_duplicates(subset='VIN')
vin_specs['API_Year'] = pd.to_numeric(vin_specs['API_Year'], errors='coerce')
vin_specs['API_Engine'] = pd.to_numeric(vin_specs['API_Engine'], errors='coerce')

# A decode counts as successful when the API recognised at least the make
vin_specs['Status'] = np.where(vin_specs['API_Make'].notna(), 'Success', 'Failed')
vin_specs.to_csv(f"{PROCESSED_DIR}/vin_specs.csv", index=False)

# --- 4. Track failures ---
enriched = batch.merge(vin_specs, on='VIN', how='left', validate='1:1')
enriched['Status'] = enriched['Status'].fillna('Failed')
success = enriched['Status'] == 'Success'
# ErrorCode '0' = clean decode. Other codes mean the VIN decoded only partly (e.g. bad check digit)
clean_decode = enriched['API_ErrorCode'].astype(str).str.strip() == '0'

print("\n--- C1 summary ---")
print(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
print(f"VINs checked: {SAMPLE_SIZE}")
print(f"Decoded: {success.sum()}  |  Failed: {(~success).sum()}  |  Failure rate: {(~success).mean() * 100:.1f}%")
print(f"Decoded with a warning (check digit or position errors): {(success & ~clean_decode).sum()}")

# =============================================================================
# C2: ENRICHMENT + COVERAGE
# =============================================================================

# --- 1. Coverage: how often does the decoder return each spec? ---
coverage_fields = {'Engine displacement': 'API_Engine', 'Body class': 'API_Body',
                   'Drivetrain': 'API_Drive', 'Fuel type': 'API_Fuel'}
coverage = pd.DataFrame([{'field': label, 'populated': int(enriched[col].notna().sum()),
                          'coverage_pct': round(enriched[col].notna().mean() * 100, 1)}
                         for label, col in coverage_fields.items()])
print(f"\n--- C2: API coverage (N={SAMPLE_SIZE}) ---")
print(coverage.to_string(index=False))
save_table(coverage, "vin_coverage.csv")

# --- 2. Bring both sources to the same vocabulary before comparing them ---

# Make: lowercase, hyphens as spaces ('alfa-romeo' = 'ALFA ROMEO').
# Ram trucks were sold as 'Dodge Ram' until 2010 and many later VINs still decode as Dodge,
# so the two names are treated as one make.
make_aliases = {'rover': 'land rover', 'ram': 'dodge'}
enriched['make_listing'] = enriched['manufacturer'].str.replace('-', ' ').replace(make_aliases)
enriched['make_api'] = enriched['API_Make'].str.lower().str.replace('-', ' ').replace(make_aliases)
# 'unknown' in the listing means the seller left the field empty
enriched.loc[enriched['make_listing'] == 'unknown', 'make_listing'] = np.nan

# Drive: the listings only know fwd / rwd / 4wd. The decoder separates AWD from 4WD
# (both are '4wd' in the listings) and often returns '4x2', which only says "two-wheel drive".
def normalize_drive(value):
    if pd.isna(value):
        return np.nan
    value = value.upper()
    if '4WD' in value or 'AWD' in value or '4X4' in value:
        return '4wd'
    if 'FWD' in value:
        return 'fwd'
    if 'RWD' in value:
        return 'rwd'
    if '4X2' in value or '2WD' in value:
        return '2wd'
    return np.nan

enriched['drive_api'] = enriched['API_Drive'].apply(normalize_drive)
enriched['drive_listing'] = enriched['drive'].replace('unknown', np.nan)

# Fuel: only the three unambiguous types are compared (hybrids decode as gasoline + electric)
fuel_map = {'Gasoline': 'gas', 'Diesel': 'diesel', 'Electric': 'electric'}
enriched['fuel_api'] = enriched['API_Fuel'].map(fuel_map)
enriched['fuel_listing'] = enriched['fuel'].where(enriched['fuel'].isin(['gas', 'diesel', 'electric']))

# --- 3. Pre- vs post-enrichment: gaps filled and conflicts found ---
# For every field: Enrichment = the listing was empty and the API has a value
#                  Conflict   = both have a value and they disagree
def drive_conflict(listing, api):
    # '2wd' from the API agrees with both fwd and rwd
    return (api != listing) & ~((api == '2wd') & listing.isin(['fwd', 'rwd']))

comparisons = [
    ('Manufacturer', 'make_listing', 'make_api', lambda l, a: l != a),
    ('Model year', 'year', 'API_Year', lambda l, a: l != a),
    ('Drive type', 'drive_listing', 'drive_api', drive_conflict),
    ('Fuel type', 'fuel_listing', 'fuel_api', lambda l, a: l != a),
]

audit_rows = []
for label, listing_col, api_col, is_conflict in comparisons:
    listing_val, api_val = enriched[listing_col], enriched[api_col]
    both = success & listing_val.notna() & api_val.notna()
    enriched[f'filled_{listing_col}'] = success & listing_val.isna() & api_val.notna()
    enriched[f'conflict_{listing_col}'] = both & is_conflict(listing_val, api_val)
    audit_rows.append({
        'field': label,
        'compared': int(both.sum()),
        'gaps_filled': int(enriched[f'filled_{listing_col}'].sum()),
        'conflicts': int(enriched[f'conflict_{listing_col}'].sum()),
        'conflict_pct': round(enriched[f'conflict_{listing_col}'].sum() / max(both.sum(), 1) * 100, 1),
    })
quality_audit = pd.DataFrame(audit_rows)
print("\n--- C2: listing vs decoder ---")
print(quality_audit.to_string(index=False))
save_table(quality_audit, "vin_quality_audit.csv")

for label, listing_col, api_col, _ in comparisons:
    conflicts = enriched[enriched[f'conflict_{listing_col}']]
    if len(conflicts) > 0:
        print(f"\nSample conflicts - {label}:")
        print(conflicts[['VIN', listing_col, api_col]].head(5).to_string(index=False))

# --- 4. Does the enrichment change the conclusions? ---
# Stage 2 found that drive type is one of the price drivers, but 'drive' is unknown
# for a large share of the listings. Here the unknowns are filled from the decoder
# and the median price per drive type is compared before and after.
enriched['drive_enriched'] = enriched['drive_listing'].fillna(enriched['drive_api'])

before = (enriched.groupby(enriched['drive_listing'].fillna('unknown'))['price']
          .agg(listings_before='size', median_price_before='median'))
after = (enriched.groupby(enriched['drive_enriched'].fillna('unknown'))['price']
         .agg(listings_after='size', median_price_after='median'))
drive_comparison = before.join(after, how='outer').rename_axis('drive').reset_index()
drive_comparison['listings_before'] = drive_comparison['listings_before'].fillna(0).astype(int)
print("\n--- Median price by drive type, before and after enrichment ---")
print(drive_comparison.to_string(index=False))
save_table(drive_comparison, "vin_drive_before_after.csv")

# =============================================================================
# C3: VALIDATION RULES
# =============================================================================
current_year = datetime.now().year

rules = {
    # An electric vehicle cannot have an engine displacement
    'Electric vehicle with an engine displacement':
        (enriched['fuel'] == 'electric') & (enriched['API_Engine'] > 0),
    # A combustion or hybrid vehicle should come back with an engine size
    'Combustion vehicle without an engine displacement':
        success & enriched['fuel'].isin(['gas', 'diesel', 'hybrid']) & ~(enriched['API_Engine'] > 0),
    # Decoded model year has to be plausible
    'Model year out of range':
        enriched['API_Year'].notna() & ~enriched['API_Year'].between(1981, current_year + 1),
    # A pickup should come back with a drivetrain
    'Pickup without a drivetrain':
        enriched['API_Body'].str.contains('Pickup', na=False) & enriched['API_Drive'].isna(),
    # Listed model year differs from the decoded one by more than one year
    'Listed year more than 1 year off the decoded year':
        success & ((enriched['year'] - enriched['API_Year']).abs() > 1),
}

validation = pd.DataFrame([{'rule': rule, 'violations': int(mask.sum()),
                            'violation_pct': round(mask.mean() * 100, 1),
                            'example_vin': enriched.loc[mask, 'VIN'].iloc[0] if mask.any() else ''}
                           for rule, mask in rules.items()])
print("\n--- C3: validation rules ---")
print(validation.to_string(index=False))
save_table(validation, "vin_validation_rules.csv")

# --- Error taxonomy: listing error (seller) vs decoder missingness (API) ---
taxonomy = pd.DataFrame([
    {'error_type': 'Listing error', 'category': 'Manufacturer conflict', 'count': int(enriched['conflict_make_listing'].sum())},
    {'error_type': 'Listing error', 'category': 'Model year conflict', 'count': int(enriched['conflict_year'].sum())},
    {'error_type': 'Listing error', 'category': 'Drive type conflict', 'count': int(enriched['conflict_drive_listing'].sum())},
    {'error_type': 'Listing error', 'category': 'Fuel type conflict', 'count': int(enriched['conflict_fuel_listing'].sum())},
    {'error_type': 'Decoder missingness', 'category': 'VIN not decoded', 'count': int((~success).sum())},
    {'error_type': 'Decoder missingness', 'category': 'Missing engine', 'count': int((success & enriched['API_Engine'].isna()).sum())},
    {'error_type': 'Decoder missingness', 'category': 'Missing drivetrain', 'count': int((success & enriched['API_Drive'].isna()).sum())},
    {'error_type': 'Decoder missingness', 'category': 'Missing body class', 'count': int((success & enriched['API_Body'].isna()).sum())},
])
taxonomy['pct_of_sample'] = (taxonomy['count'] / SAMPLE_SIZE * 100).round(1)
print("\n--- Error taxonomy ---")
print(taxonomy.to_string(index=False))
save_table(taxonomy, "vin_error_taxonomy.csv")

# --- Decision: drop, correct or flag ---
# All changes are made on a copy and every decision is logged.
#   Drop    - the VIN could not be decoded, so nothing about the listing can be verified
#   Correct - the model year: the VIN encodes it, so the decoder is the source of truth
#   Flag    - manufacturer conflict: either the VIN or the brand was typed wrong; needs a person
final = enriched.copy()
final['action'] = 'Keep'
final.loc[final['conflict_year'], 'action'] = 'Correct'
final.loc[final['conflict_make_listing'], 'action'] = 'Flag'
final.loc[~success, 'action'] = 'Drop'

final['year_original'] = final['year']
final.loc[final['conflict_year'], 'year'] = final['API_Year']

decisions = final['action'].value_counts().rename_axis('action').reset_index(name='listings')
decisions['pct_of_sample'] = (decisions['listings'] / SAMPLE_SIZE * 100).round(1)
print("\n--- Remediation decisions ---")
print(decisions.to_string(index=False))
save_table(decisions, "vin_decisions.csv")

output_cols = ['id', 'VIN', 'price', 'year', 'year_original', 'manufacturer', 'model', 'fuel', 'drive', 'type',
               'API_Make', 'API_Model', 'API_Year', 'API_Body', 'API_Engine', 'API_Drive', 'API_Fuel',
               'drive_enriched', 'Status', 'action']
final_clean = final.loc[final['action'] != 'Drop', output_cols]
final_clean.to_csv(f"{PROCESSED_DIR}/listings_vin_enriched.csv", index=False)
print(f"\nSample: {SAMPLE_SIZE} rows -> final enriched dataset: {len(final_clean)} rows")
print(f"Saved {PROCESSED_DIR}/listings_vin_enriched.csv")

save_dashboard_data("vin", {
    'listings': len(listings),
    'with_vin_pct': round(has_vin.mean() * 100, 1),
    'malformed_vins': int((has_vin & ~valid_vin).sum()),
    'sample_size': SAMPLE_SIZE,
    'decoded': int(success.sum()),
    'failure_rate': round((~success).mean() * 100, 1),
    'coverage': coverage.to_dict(orient='records'),
    'audit': quality_audit.to_dict(orient='records'),
    'drive_before_after': drive_comparison.to_dict(orient='records'),
    'validation': validation.to_dict(orient='records'),
    'taxonomy': taxonomy.to_dict(orient='records'),
    'decisions': decisions.to_dict(orient='records'),
})

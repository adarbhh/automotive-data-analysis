# -*- coding: utf-8 -*-
"""
Stage 3 - NHTSA safety recalls: patterns over time, text analysis and join to the listings.

Input : data/raw/recalls.csv (NHTSA recalls export)
        data/processed/usedcars_clean.csv (from stage 1)
Output: data/processed/recalls_clean.csv
        data/processed/usedcars_with_recalls.csv
        docs/figures/*.png, reports/tables/*.csv

@author: Adar
"""

import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
from sklearn.decomposition import NMF

from utils import RAW_DIR, PROCESSED_DIR, save_fig, save_table, save_dashboard_data

# =============================================================================
# B1: RECALL PATTERN ANALYSIS
# =============================================================================

# --- 1. DATA LOADING AND PREPARATION ---
df = pd.read_csv(f"{RAW_DIR}/recalls.csv")
df.columns = df.columns.str.strip()  # one column name has a trailing space in the export

# Convert 'Report Received Date' to datetime objects and extract the year
df['Report Received Date'] = pd.to_datetime(df['Report Received Date'])
df['Reported_Year'] = df['Report Received Date'].dt.year

print(f"Recalls loaded: {len(df):,} ({df['Reported_Year'].min()} - {df['Reported_Year'].max()})")
print(f"Last report date in the export: {df['Report Received Date'].max().date()}")


# --- 2. MANUFACTURER NAME NORMALIZATION ---

def clean_manufacturer(series):
    """
    Standardizes manufacturer names: lowercase, text in brackets removed,
    punctuation removed and legal suffixes (inc, llc, corp...) dropped,
    so that 'FREIGHTLINER LLC' and 'Freightliner Corporation' become one name.
    """
    return (series
            .str.lower()
            .str.replace(r'\(.*?\)', ' ', regex=True)
            .str.replace(r'[^a-z0-9 ]', ' ', regex=True)
            .str.replace(r'\s+', ' ', regex=True)
            .str.strip()
            .str.replace(r'( (inc|corp|corporation|ltd|llc|co|company|limited|incorporated))+$', '', regex=True))

df['mfr_norm'] = clean_manufacturer(df['Manufacturer'])
print(f"Manufacturer names: {df['Manufacturer'].nunique():,} raw -> {df['mfr_norm'].nunique():,} after normalization")

# The recall is filed by the corporate entity (e.g. "General Motors, LLC"), not by the
# brand on the car. Each passenger-car maker is mapped to one group with an explicit
# pattern, so every match can be checked by eye (see recall_manufacturer_mapping.csv).
MFR_GROUP_PATTERNS = {
    'General Motors': r'^general motors',
    'Ford': r'^ford motor',
    'Chrysler (FCA)': r'^chrysler|^fca us|^daimlerchrysler',
    'Toyota': r'^toyota',
    'Honda': r'^honda|^american honda',
    'Nissan': r'^nissan',
    'Volkswagen Group': r'^volkswagen|^audi',
    'BMW': r'^bmw',
    'Mercedes-Benz': r'^mercedes benz',
    'Hyundai': r'^hyundai motor',
    'Kia': r'^kia',
    'Mazda': r'^mazda',
    'Subaru': r'^subaru',
    'Mitsubishi': r'^mitsubishi motors',
    'Volvo Cars': r'^volvo car',
    'Jaguar Land Rover': r'^jaguar|^land rover',
    'Porsche': r'^porsche',
    'Tesla': r'^tesla',
    'Ferrari': r'^ferrari',
    'Aston Martin': r'^aston martin',
    'Harley-Davidson': r'^harley davidson',
}

df['mfr_group'] = None
for group, pattern in MFR_GROUP_PATTERNS.items():
    df.loc[df['mfr_norm'].str.contains(pattern, regex=True), 'mfr_group'] = group

mapping_audit = (df[df['mfr_group'].notna()]
                 .groupby(['mfr_group', 'Manufacturer']).size().reset_index(name='recalls')
                 .sort_values(['mfr_group', 'recalls'], ascending=[True, False]))
save_table(mapping_audit, "recall_manufacturer_mapping.csv")

# Name used in charts: the group name where there is one, otherwise the most common raw spelling
most_common_name = df.groupby('mfr_norm')['Manufacturer'].agg(lambda s: s.value_counts().index[0])
df['mfr_display'] = df['mfr_group'].fillna(df['mfr_norm'].map(most_common_name))

# --- 3. AGGREGATION ---
# The export was taken in January 2026, so 2026 holds only a few weeks of data.
# It is kept in the dataset but left out of every yearly trend.
LAST_FULL_YEAR = 2025
df_trend = df[df['Reported_Year'] <= LAST_FULL_YEAR]

# Matrix: Rows = Years, Columns = Manufacturers, Values = Recall counts
recalls_per_year = df_trend.groupby('Reported_Year').size()

# Spikes and breaks are only meaningful for manufacturers with a real history:
# a company with 2 recalls in 60 years has a huge Z-score in both of those years.
MIN_RECALLS = 100
mfr_totals = df_trend['mfr_display'].value_counts()
major_mfrs = mfr_totals[mfr_totals >= MIN_RECALLS].index
recall_matrix = (df_trend[df_trend['mfr_display'].isin(major_mfrs)]
                 .groupby(['Reported_Year', 'mfr_display']).size().unstack(fill_value=0))
print(f"\nManufacturers with at least {MIN_RECALLS} recalls: {len(major_mfrs)}")

# --- 4. SPIKE DETECTION (Z-SCORE LOGIC) ---
# Each manufacturer is compared to its own history: Z = (Value - Mean) / Standard Deviation
z_scores = (recall_matrix - recall_matrix.mean()) / recall_matrix.std()

spikes_list = []
for mfr in z_scores.columns:
    # Z > 2: the year is more than two standard deviations above that manufacturer's average
    for year in z_scores.index[z_scores[mfr] > 2]:
        spikes_list.append({
            'Manufacturer': mfr,
            'Year': year,
            'Recall_Count': recall_matrix.loc[year, mfr],
            'Z_Score': round(z_scores.loc[year, mfr], 2)
        })
all_spikes = pd.DataFrame(spikes_list).sort_values(by='Z_Score', ascending=False)

# --- 5. STRUCTURAL BREAK DETECTION ---
# Goal: find lasting shifts - the average of the last 10 full years
# is at least double the average of the 10 years before them.
recent_avg = recall_matrix.loc[2016:2025].mean()
previous_avg = recall_matrix.loc[2006:2015].mean()

breaks_list = []
for mfr in recall_matrix.columns:
    # a manufacturer with no recalls at all in the earlier window is a new filer, not a break
    if previous_avg[mfr] > 0 and recent_avg[mfr] >= 2 * previous_avg[mfr] and recent_avg[mfr] >= 5:
        ratio = recent_avg[mfr] / previous_avg[mfr]
        breaks_list.append({
            'Manufacturer': mfr,
            'Avg_2006_2015': round(previous_avg[mfr], 1),
            'Avg_2016_2025': round(recent_avg[mfr], 1),
            'Increase_Ratio': round(ratio, 2)
        })
all_breaks = pd.DataFrame(breaks_list).sort_values(by='Increase_Ratio', ascending=False)

print(f"Total spikes detected: {len(all_spikes)}")
print(all_spikes.head(10).to_string(index=False))
print(f"\nTotal structural breaks detected: {len(all_breaks)}")
print(all_breaks.to_string(index=False))
save_table(all_spikes, "recall_spikes.csv")
save_table(all_breaks, "recall_structural_breaks.csv")

# --- 6. EXPOSURE BIAS ---
# Large manufacturers have more vehicles on the road, so they naturally file more recalls.
# The export has no sales figures, but it does report how many units each recall covers.
# Ranking by units gives a different picture than ranking by number of recalls.
exposure = (df.groupby('mfr_display')
            .agg(recalls=('NHTSA ID', 'size'), units_affected=('Potentially Affected', 'sum'))
            .reset_index().rename(columns={'mfr_display': 'manufacturer'}))
exposure['units_per_recall'] = (exposure['units_affected'] / exposure['recalls']).round(0)
exposure = exposure.sort_values('recalls', ascending=False)
exposure['rank_by_recalls'] = range(1, len(exposure) + 1)
exposure['rank_by_units'] = exposure['units_affected'].rank(ascending=False).astype(int)
print("\n--- Top 15 manufacturers: number of recalls vs units affected ---")
print(exposure.head(15).to_string(index=False))
save_table(exposure.head(50), "recall_exposure.csv")

# --- 7. COMPONENT DOMINANCE ANALYSIS ---
component_counts = df['Component'].value_counts()
top_10_components = component_counts.head(10)

# Pivot table: recall counts per year for each component (top 5 only, to keep the plot clear)
comp_over_time = df_trend.groupby(['Reported_Year', 'Component']).size().unstack(fill_value=0)
top_5_names = top_10_components.index[:5]
filtered_trends = comp_over_time[top_5_names]

print("\n--- Top 10 components overall ---")
print(top_10_components)
print(f"Recalls without a component: {df['Component'].isna().mean() * 100:.1f}%")

filtered_trends.plot(kind='line', marker='o', markersize=3, figsize=(12, 6))
plt.title('Evolution of Top Recall Components (By Reporting Year)')
plt.ylabel('Number of Recalls')
plt.xlabel('Year')
plt.grid(True, linestyle='--', alpha=0.7)
plt.legend(title='Vehicle Components')
save_fig("recall_components_over_time.png")

plt.figure(figsize=(12, 5))
plt.bar(recalls_per_year.index, recalls_per_year.values, color='steelblue')
plt.title(f'Recalls Reported per Year (1966 - {LAST_FULL_YEAR})')
plt.ylabel('Number of Recalls')
plt.xlabel('Year')
save_fig("recalls_per_year.png")

# =============================================================================
# B2: NLP - FAILURE MODE DISCOVERY
# =============================================================================

# --- 1. TEXT CLEANING AND NORMALIZATION ---

def clean_text(series):
    """Lowercase, keep letters only and collapse extra whitespace."""
    return (series
            .fillna('')
            .str.lower()
            .str.replace(r'[^a-z\s]', ' ', regex=True)
            .str.replace(r'\s+', ' ', regex=True)
            .str.strip())

# 'Consequence Summary' describes what can happen because of the defect
df['consequence_clean'] = clean_text(df['Consequence Summary'])
has_text = df['consequence_clean'] != ''
print(f"\nRecalls with a consequence text: {has_text.sum():,} of {len(df):,} "
      f"(the field is mostly empty before 1990)")

# --- 2. TF-IDF VECTORIZATION (The Baseline) ---
# Almost every summary ends with the same boilerplate ("...increasing the risk of a crash").
# These words are removed so the topics describe the failure itself.
boilerplate = ['increasing', 'increase', 'increases', 'increased', 'risk', 'result', 'resulting',
               'vehicle', 'vehicles', 'crash', 'injury', 'condition', 'occur', 'possibly',
               'possible', 'personal', 'cause', 'causing', 'warning', 'accident', 'event']

# ngram_range=(1, 2): captures single words and pairs (e.g. "air bag")
tfidf_vec = TfidfVectorizer(
    max_features=2000,
    stop_words=list(ENGLISH_STOP_WORDS) + boilerplate,
    ngram_range=(1, 2),
    min_df=20
)
tfidf_matrix = tfidf_vec.fit_transform(df.loc[has_text, 'consequence_clean'])

# Works with both old and new scikit-learn versions
if hasattr(tfidf_vec, 'get_feature_names_out'):
    feature_names = tfidf_vec.get_feature_names_out()
else:
    feature_names = tfidf_vec.get_feature_names()

# --- 3. TOPIC MODEL (NMF) ---
# K-Means on the same matrix put ~70% of the recalls in one cluster,
# NMF gives more balanced and readable topics.
NUM_TOPICS = 8
nmf = NMF(n_components=NUM_TOPICS, random_state=42, init='nndsvd', max_iter=400)
topic_weights = nmf.fit_transform(tfidf_matrix)

df['Topic'] = -1
df.loc[has_text, 'Topic'] = topic_weights.argmax(axis=1)
df.loc[has_text, 'topic_weight'] = topic_weights.max(axis=1)
# Texts that contain none of the vocabulary words get no topic
df.loc[has_text & (df['topic_weight'] == 0), 'Topic'] = -1

# Names given after reading the top words and the examples printed below
TOPIC_NAMES = {
    0: 'Fuel leak / fire',
    1: 'Loss of steering or vehicle control',
    2: 'Seats & seat belts',
    3: 'Engine stall',
    4: 'Brakes, tires & other (broad)',
    5: 'Electrical short / fire',
    6: 'Air bags',
    7: 'Loss of drive power',
}

# --- 4. TOP WORDS AND VALIDATION EXAMPLES PER TOPIC ---
print("\n--- Top words per topic and the 2 most representative examples ---")
topic_rows = []
for i in range(NUM_TOPICS):
    top_words = [feature_names[ind] for ind in nmf.components_[i].argsort()[::-1][:8]]
    in_topic = df[df['Topic'] == i]
    examples = (in_topic.sort_values('topic_weight', ascending=False)['Consequence Summary']
                .drop_duplicates().head(2).tolist())
    print(f"\nTopic {i} - {TOPIC_NAMES[i]} ({len(in_topic):,} recalls): {', '.join(top_words)}")
    for ex in examples:
        print(f"   - {ex}")
    topic_rows.append({'topic': i, 'name': TOPIC_NAMES[i], 'recalls': len(in_topic),
                       'top_words': ', '.join(top_words), 'example': examples[0]})

# =============================================================================
# B3: SEVERITY PROXY
# =============================================================================

# Keyword-based proxy on a 1-3 scale. A recall gets the highest level it matches.
#   3 (High)   - fire, or the driver loses control of the vehicle
#   2 (Medium) - crash or injury risk is mentioned, without the terms above
#   1 (Low)    - none of these terms (e.g. a labelling non-compliance)
HIGH_SEVERITY_TERMS = ['fire', 'burn', 'explo', 'death', 'fatal', 'loss of control',
                       'loss of vehicle control', 'loss of steering', 'loss of brak',
                       'brake failure', 'rollaway', 'roll away', 'stall',
                       'loss of drive power', 'loss of motive power', 'unintended']
MEDIUM_SEVERITY_TERMS = ['crash', 'collision', 'accident', 'injur']

# The proxy reads the original wording (lowercased), not the text stripped for the topic model
consequence_lower = df['Consequence Summary'].fillna('').str.lower()
is_high = consequence_lower.str.contains('|'.join(HIGH_SEVERITY_TERMS), regex=True)
is_medium = consequence_lower.str.contains('|'.join(MEDIUM_SEVERITY_TERMS), regex=True)

df['Severity'] = np.where(is_high, 3, np.where(is_medium, 2, 1))
df.loc[~has_text, 'Severity'] = np.nan  # no text - no score

print("\n--- Severity distribution (recalls with text) ---")
print(df['Severity'].value_counts().sort_index())

# Rank the topics by mean severity
severity_by_topic = (df[df['Topic'] >= 0].groupby('Topic')['Severity']
                     .agg(mean_severity='mean', share_high=lambda s: (s == 3).mean()).reset_index())
topic_summary = pd.DataFrame(topic_rows).merge(severity_by_topic, left_on='topic', right_on='Topic').drop(columns='Topic')
topic_summary['mean_severity'] = topic_summary['mean_severity'].round(2)
topic_summary['share_high'] = (topic_summary['share_high'] * 100).round(1)
topic_summary = topic_summary.sort_values('mean_severity', ascending=False)
print("\n--- Topics ranked by mean severity ---")
print(topic_summary[['name', 'recalls', 'mean_severity', 'share_high']].to_string(index=False))
save_table(topic_summary, "recall_topics_severity.csv")

# Sanity check of the proxy against two fields it never saw: NHTSA's own advisories.
# "Park outside" is issued for fire risk and "Do not drive" for the most urgent defects,
# so these recalls should be scored High much more often than the average recall.
validation = []
for advisory in ['Park Outside Advisory', 'Do Not Drive Advisory']:
    flagged = df[(df[advisory] == 'Yes') & has_text]
    validation.append({'group': advisory, 'recalls': len(flagged),
                       'share_scored_high': round((flagged['Severity'] == 3).mean() * 100, 1)})
validation.append({'group': 'All recalls with text', 'recalls': int(has_text.sum()),
                   'share_scored_high': round((df.loc[has_text, 'Severity'] == 3).mean() * 100, 1)})
validation = pd.DataFrame(validation)
print("\n--- Proxy validation against NHTSA advisories ---")
print(validation.to_string(index=False))
save_table(validation, "recall_severity_validation.csv")

# --- Save the processed recalls ---
recalls_clean = df[['NHTSA ID', 'Report Received Date', 'Reported_Year', 'Manufacturer', 'mfr_norm',
                    'mfr_group', 'Recall Type', 'Component', 'Potentially Affected', 'Subject',
                    'Recall Description', 'Consequence Summary', 'Topic', 'Severity',
                    'Park Outside Advisory', 'Do Not Drive Advisory']].copy()
recalls_clean['Topic_Name'] = recalls_clean['Topic'].map(TOPIC_NAMES)
recalls_clean.to_csv(f"{PROCESSED_DIR}/recalls_clean.csv", index=False)
print(f"\nSaved {PROCESSED_DIR}/recalls_clean.csv")

# =============================================================================
# B4: JOIN WITH THE USED CAR LISTINGS
# =============================================================================

# Join keys, from the weakest to the strongest:
#   1. Manufacturer group            (listing brand -> corporate group that files the recall)
#   2. + model year                  (extracted from the recall sentence of the description)
#   3. + model name                  (first word of the listing model found in that sentence)

# --- 1. PREPARE DATASET A (LISTINGS) ---
cars = pd.read_csv(f"{PROCESSED_DIR}/usedcars_clean.csv",
                   usecols=['id', 'manufacturer', 'model', 'year', 'price'])
cars['year'] = cars['year'].astype(int)

BRAND_TO_GROUP = {
    'buick': 'General Motors', 'cadillac': 'General Motors', 'chevrolet': 'General Motors',
    'gmc': 'General Motors', 'pontiac': 'General Motors', 'saturn': 'General Motors',
    'ford': 'Ford', 'lincoln': 'Ford', 'mercury': 'Ford',
    'chrysler': 'Chrysler (FCA)', 'dodge': 'Chrysler (FCA)', 'jeep': 'Chrysler (FCA)',
    'ram': 'Chrysler (FCA)', 'fiat': 'Chrysler (FCA)', 'alfa-romeo': 'Chrysler (FCA)',
    'toyota': 'Toyota', 'lexus': 'Toyota',
    'honda': 'Honda', 'acura': 'Honda',
    'nissan': 'Nissan', 'infiniti': 'Nissan', 'datsun': 'Nissan',
    'volkswagen': 'Volkswagen Group', 'audi': 'Volkswagen Group',
    'bmw': 'BMW', 'mini': 'BMW',
    'mercedes-benz': 'Mercedes-Benz',
    'hyundai': 'Hyundai', 'kia': 'Kia', 'mazda': 'Mazda', 'subaru': 'Subaru',
    'mitsubishi': 'Mitsubishi', 'volvo': 'Volvo Cars',
    'jaguar': 'Jaguar Land Rover', 'land rover': 'Jaguar Land Rover', 'rover': 'Jaguar Land Rover',
    'porsche': 'Porsche', 'tesla': 'Tesla', 'ferrari': 'Ferrari',
    'aston-martin': 'Aston Martin', 'harley-davidson': 'Harley-Davidson',
}
cars['mfr_group'] = cars['manufacturer'].map(BRAND_TO_GROUP)

def normalize_token(text):
    """'F-150' -> 'f150', 'CR-V' -> 'crv' so both datasets spell a model the same way."""
    return re.findall(r'[a-z0-9]+', str(text).lower().replace('-', ''))

# First word of the listing model ("silverado 1500 crew cab" -> "silverado")
cars['model_token'] = cars['model'].apply(lambda m: (normalize_token(m) or [''])[0])

# Words that are not a model name on their own
AMBIGUOUS_TOKENS = {'', 'unknown', 'other', 'new', 'super', 'grand', 'sport', 'base',
                    'limited', 'town', 'land'}
# A token has to be a common model name to be used (drops typos and one-off free text).
# Ordinary English words ("is", "all") and very short tokens ("3", "s") are dropped too,
# because they would match almost every recall text. Years are dropped as well.
token_counts = cars['model_token'].value_counts()
valid_tokens = {t for t in token_counts[token_counts >= 20].index
                if len(t) >= 2 and not (t.isdigit() and len(t) < 3)
                and not re.fullmatch(r'(19|20)\d{2}', t)}  # a year typed in the model field
valid_tokens = valid_tokens - AMBIGUOUS_TOKENS - set(ENGLISH_STOP_WORDS)
cars.loc[~cars['model_token'].isin(valid_tokens), 'model_token'] = None

# --- 2. PREPARE DATASET B (RECALLS) ---
# Only vehicle recalls describe a car model and model year (not tires, child seats or equipment)
vehicle_recalls = df[df['Recall Type'] == 'Vehicle'].copy()

def recall_sentence(text):
    """
    The sentence that says what is being recalled, e.g.
    "Ford Motor Company (Ford) is recalling certain 2020-2022 Escape vehicles."
    Model years and model names are read from this sentence only. The rest of the
    description explains the defect, where words like 'bolt', 'spark' or 'escape'
    are not model names.
    """
    if pd.isna(text):
        return ''
    text = str(text)
    start = text.lower().find('recalling')
    if start == -1:
        return ''
    end = text.find('. ', start)
    return text[:end] if end != -1 else text

def extract_years(text):
    """Model years in the text. A range like '2013-2018' is expanded to every year in it."""
    years = set()
    for start, end in re.findall(r'\b((?:19|20)\d{2})\s*-\s*((?:19|20)\d{2})\b', text):
        if 0 <= int(end) - int(start) <= 30:
            years.update(range(int(start), int(end) + 1))
    years.update(int(y) for y in re.findall(r'\b(?:19|20)\d{2}\b', text))
    return sorted(y for y in years if 1980 <= y <= 2027)

vehicle_recalls['recall_sentence'] = vehicle_recalls['Recall Description'].apply(recall_sentence)
vehicle_recalls['model_years'] = vehicle_recalls['recall_sentence'].apply(extract_years)
vehicle_recalls['has_years'] = vehicle_recalls['model_years'].apply(len) > 0

# One row per (recall, model year) - only for manufacturers that exist in the listings
recall_years = (vehicle_recalls.loc[vehicle_recalls['mfr_group'].notna() & vehicle_recalls['has_years'],
                                    ['NHTSA ID', 'mfr_group', 'model_years', 'recall_sentence']]
                .explode('model_years').rename(columns={'model_years': 'year'}))
recall_years['year'] = recall_years['year'].astype(int)

# One row per (recall, model year, model name found in the description)
recall_years['model_token'] = recall_years['recall_sentence'].apply(
    lambda text: sorted(set(normalize_token(text)) & valid_tokens))
recall_models = recall_years.drop(columns='recall_sentence').explode('model_token').dropna(subset=['model_token'])
recall_years = recall_years.drop(columns=['recall_sentence', 'model_token'])

# --- 3. AGGREGATE THE RECALLS BEFORE JOINING ---
# The recalls are reduced to one row per key first, so the join is many-to-one
# and can never duplicate a listing (no many-to-many explosion).
recalls_by_mfr_year = (recall_years.groupby(['mfr_group', 'year'])['NHTSA ID'].nunique()
                       .reset_index(name='mfr_year_recall_count'))
recalls_by_model = (recall_models.groupby(['mfr_group', 'year', 'model_token'])['NHTSA ID'].nunique()
                    .reset_index(name='recall_count'))

# --- 4. JOIN ---
rows_before = len(cars)
cars = cars.merge(recalls_by_model, on=['mfr_group', 'year', 'model_token'], how='left', validate='m:1')
cars = cars.merge(recalls_by_mfr_year, on=['mfr_group', 'year'], how='left', validate='m:1')
assert len(cars) == rows_before, "The join changed the number of listings"
print(f"\nJoin audit: {rows_before:,} listings before, {len(cars):,} after - no duplication")

cars['recall_count'] = cars['recall_count'].fillna(0).astype(int)
cars['mfr_year_recall_count'] = cars['mfr_year_recall_count'].fillna(0).astype(int)
# Binary feature: at least one recall on record for this model and model year
cars['recalled_flag'] = (cars['recall_count'] > 0).astype(int)

cars[['id', 'mfr_group', 'recalled_flag', 'recall_count', 'mfr_year_recall_count']].to_csv(
    f"{PROCESSED_DIR}/usedcars_with_recalls.csv", index=False)
print(f"Saved {PROCESSED_DIR}/usedcars_with_recalls.csv")

# --- 5. JOIN COVERAGE - LISTING SIDE ---
n_cars = len(cars)
listing_coverage = pd.DataFrame([
    {'level': 'Manufacturer mapped to a recall group', 'listings': int(cars['mfr_group'].notna().sum())},
    {'level': 'Model name usable as a join key', 'listings': int((cars['mfr_group'].notna() & cars['model_token'].notna()).sum())},
    {'level': 'Manufacturer + year has at least one recall', 'listings': int((cars['mfr_year_recall_count'] > 0).sum())},
    {'level': 'Model + year has at least one recall (recalled_flag = 1)', 'listings': int(cars['recalled_flag'].sum())},
])
listing_coverage['pct_of_listings'] = (listing_coverage['listings'] / n_cars * 100).round(1)
print("\n--- Join coverage: listings ---")
print(listing_coverage.to_string(index=False))
save_table(listing_coverage, "join_coverage_listings.csv")

# --- 6. JOIN COVERAGE - RECALL SIDE ---
# For every recall: what is the best key that connects it to at least one listing?
car_keys_model = set(zip(cars['mfr_group'], cars['year'], cars['model_token']))
car_keys_year = set(zip(cars['mfr_group'], cars['year']))

matched_model = set(recall_models.loc[[k in car_keys_model for k in
                                       zip(recall_models['mfr_group'], recall_models['year'], recall_models['model_token'])],
                                      'NHTSA ID'])
matched_year = set(recall_years.loc[[k in car_keys_year for k in
                                     zip(recall_years['mfr_group'], recall_years['year'])], 'NHTSA ID'])

def assign_quality(row):
    if row['Recall Type'] != 'Vehicle':
        return 'Out of scope (tire / equipment / child seat)'
    if row['NHTSA ID'] in matched_model:
        return 'High (Mfr + Year + Model)'
    if row['NHTSA ID'] in matched_year:
        return 'Medium (Mfr + Year)'
    if pd.notna(row['mfr_group']):
        return 'Low (Mfr only)'
    return 'Unmatched (manufacturer not in the listings)'

df['join_quality'] = df.apply(assign_quality, axis=1)
recall_coverage = df['join_quality'].value_counts().rename_axis('join_quality').reset_index(name='recalls')
recall_coverage['pct_of_recalls'] = (recall_coverage['recalls'] / len(df) * 100).round(2)
print("\n--- Join coverage: recalls ---")
print(recall_coverage.to_string(index=False))
save_table(recall_coverage, "join_coverage_recalls.csv")

# Who are the unmatched manufacturers? (expected: trucks, buses, trailers and RVs)
unmatched = (df[df['join_quality'].str.startswith('Unmatched')]['Manufacturer']
             .value_counts().head(15).rename_axis('manufacturer').reset_index(name='recalls'))
print("\n--- Top unmatched manufacturers ---")
print(unmatched.to_string(index=False))
save_table(unmatched, "join_unmatched_examples.csv")

# Why do recalls of mapped manufacturers stop at 'Mfr only'? Mostly old recalls without a model year.
low = df[df['join_quality'] == 'Low (Mfr only)']
print(f"\n'Mfr only' recalls reported before 2005: {(low['Reported_Year'] < 2005).mean() * 100:.1f}%")

# --- 7. SPOT CHECK ---
sample_car = cars[cars['recalled_flag'] == 1].sort_values('recall_count', ascending=False).iloc[0]
sample_ids = recall_models[(recall_models['mfr_group'] == sample_car['mfr_group']) &
                           (recall_models['year'] == sample_car['year']) &
                           (recall_models['model_token'] == sample_car['model_token'])]['NHTSA ID'].unique()
print(f"\n--- Spot check: {sample_car['year']} {sample_car['manufacturer']} {sample_car['model']} "
      f"-> {len(sample_ids)} recalls ---")
print(df[df['NHTSA ID'].isin(sample_ids)][['NHTSA ID', 'Subject']].head(5).to_string(index=False))

# --- 8. RECALLS ON THE MOST LISTED MODELS ---
cars['model_label'] = cars['manufacturer'] + ' ' + cars['model_token']
top_models = (cars[cars['model_token'].notna() & cars['mfr_group'].notna()]
              .groupby('model_label')
              .agg(listings=('id', 'size'), share_recalled=('recalled_flag', 'mean'),
                   avg_recalls=('recall_count', 'mean'))
              .sort_values('listings', ascending=False).head(15).reset_index())
top_models['share_recalled'] = (top_models['share_recalled'] * 100).round(1)
top_models['avg_recalls'] = top_models['avg_recalls'].round(1)
print("\n--- 15 most listed models: recalls on record ---")
print(top_models.to_string(index=False))
save_table(top_models, "recalls_top_listed_models.csv")

recalled_by_year = (cars[cars['mfr_group'].notna()].groupby('year')
                    .agg(listings=('id', 'size'), share_recalled=('recalled_flag', 'mean')).reset_index())
recalled_by_year['share_recalled'] = (recalled_by_year['share_recalled'] * 100).round(1)

# =============================================================================
# DATA FOR THE DASHBOARD
# =============================================================================

top_10_mfrs = mfr_totals.head(10).index.tolist()
years = list(range(1966, LAST_FULL_YEAR + 1))
all_mfr_matrix = (df_trend[df_trend['mfr_display'].isin(top_10_mfrs)]
                  .groupby(['Reported_Year', 'mfr_display']).size().unstack(fill_value=0).reindex(years, fill_value=0))

# --- Top 10 manufacturers page (docs/vehicle_recall_dashboard.html) ---
top10 = df_trend[df_trend['mfr_display'].isin(top_10_mfrs)]
top10_components = top10['Component'].value_counts().head(10)
top10_per_year = top10.groupby('Reported_Year').size()
heat_mfrs = top_10_mfrs[:5]
heat_components = top10_components.index[:5].tolist()
heat = (top10[top10['mfr_display'].isin(heat_mfrs) & top10['Component'].isin(heat_components)]
        .groupby(['mfr_display', 'Component']).size().unstack(fill_value=0)
        .reindex(index=heat_mfrs, columns=heat_components, fill_value=0))
trend_years = list(range(2000, LAST_FULL_YEAR + 1))

save_dashboard_data("recalls_top10", {
    'first_year': int(top10['Reported_Year'].min()),
    'last_year': LAST_FULL_YEAR,
    'total_recalls': len(top10),
    'manufacturers': [{'name': m, 'recalls': int(mfr_totals[m])} for m in top_10_mfrs],
    'components': top10_components.rename_axis('component').reset_index(name='recalls').to_dict(orient='records'),
    'missing_component': int(top10['Component'].isna().sum()),
    'trend_years': trend_years,
    'trend_values': top10_per_year.reindex(trend_years, fill_value=0).tolist(),
    'peak_year': int(top10_per_year.idxmax()),
    'peak_recalls': int(top10_per_year.max()),
    'heat_manufacturers': heat_mfrs,
    'heat_components': heat_components,
    'heat_values': heat.values.tolist(),
})

save_dashboard_data("recalls", {
    'total_recalls': len(df),
    'first_year': int(df['Reported_Year'].min()),
    'last_full_year': LAST_FULL_YEAR,
    'export_date': str(df['Report Received Date'].max().date()),
    'manufacturers': int(df['mfr_norm'].nunique()),
    'units_affected': int(df['Potentially Affected'].sum()),
    'years': years,
    'per_year': recalls_per_year.reindex(years, fill_value=0).tolist(),
    'top_manufacturers': exposure.head(10).to_dict(orient='records'),
    'per_year_by_manufacturer': {m: all_mfr_matrix[m].tolist() for m in top_10_mfrs},
    'top_components': top_10_components.rename_axis('component').reset_index(name='recalls').to_dict(orient='records'),
    'component_trends': {c: filtered_trends[c].reindex(years, fill_value=0).tolist() for c in top_5_names},
    'missing_component_pct': round(df['Component'].isna().mean() * 100, 1),
    'spikes': all_spikes.head(10).to_dict(orient='records'),
    'breaks': all_breaks.to_dict(orient='records'),
    'topics': topic_summary.to_dict(orient='records'),
    'severity_validation': validation.to_dict(orient='records'),
    'recalls_with_text': int(has_text.sum()),
    'join_listings': listing_coverage.to_dict(orient='records'),
    'join_recalls': recall_coverage.to_dict(orient='records'),
    'top_models': top_models.to_dict(orient='records'),
    'recalled_by_year': recalled_by_year[recalled_by_year['year'] >= 2000].to_dict(orient='list'),
})

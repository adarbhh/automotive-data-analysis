# -*- coding: utf-8 -*-
"""
Stage 2 - Used car listings: EDA, feature engineering and price drivers.

Business question: what drives the asking price of a used car the most?

Input : data/processed/usedcars_clean.csv
Output: docs/figures/*.png, reports/tables/*.csv

@author: Adar
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score

from utils import PROCESSED_DIR, save_fig, save_table, save_dashboard_data

sns.set_style("whitegrid")

# Load the clean file from stage 1
df = pd.read_csv(f"{PROCESSED_DIR}/usedcars_clean.csv", low_memory=False)
print(f"Loaded {len(df):,} cleaned listings")

# --- A4: Price distribution (raw vs log) ---

plt.figure(figsize=(12, 5))

plt.subplot(1, 2, 1)
plt.hist(df['price'], bins=50, color='skyblue', edgecolor='black')
plt.title('Price Distribution (Raw)')
plt.xlabel('Price ($)')
plt.ylabel('Number of listings')

plt.subplot(1, 2, 2)
plt.hist(np.log10(df['price']), bins=50, color='salmon', edgecolor='black')
plt.title('Price Distribution (Log Scale)')
plt.xlabel('Log10(Price)')
plt.ylabel('Number of listings')

save_fig("price_distribution.png")

print(f"Price skewness: raw = {df['price'].skew():.2f}, log = {np.log(df['price']).skew():.2f}")

# --- A4: Price vs odometer and price vs year, segmented ---

# A scatter plot of 200,000 listings is one solid cloud: the largest category hides the
# others. Instead, each panel shows the median price of every category along the x axis,
# with a shaded band for the middle 50% of listings.
# Only the main categories are drawn ('unknown' and 'other' are left out).
segments = {
    'fuel': ['gas', 'diesel'],
    'transmission': ['automatic', 'manual'],
    'drive': ['fwd', 'rwd', '4wd'],
}
segment_colors = ['#2a78d6', '#eb6834', '#1baf7a']
MIN_LISTINGS = 150  # a median of fewer listings than this is too noisy to plot

# Odometer in 20,000-mile bands (labelled by the middle of the band); model year as it is
df['odometer_band'] = (df['odometer'] // 20000) * 20000 + 10000

def q25(x): return x.quantile(0.25)
def q75(x): return x.quantile(0.75)

x_axes = [
    ('odometer', 'odometer_band', 'Odometer (miles)', df['odometer'] < 240000),
    ('year', 'year', 'Model year', df['year'] >= 1995),
]

segment_lines = []
for x_name, x_col, x_label, in_range in x_axes:
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.2), sharey=True)
    for ax, (col, categories) in zip(axes, segments.items()):
        for category, color in zip(categories, segment_colors):
            subset = df[in_range & (df[col] == category)]
            line = subset.groupby(x_col)['price'].agg(listings='size', median='median', q25=q25, q75=q75)
            line = line[line['listings'] >= MIN_LISTINGS]
            ax.fill_between(line.index, line['q25'], line['q75'], color=color, alpha=0.12)
            ax.plot(line.index, line['median'], color=color, linewidth=2.2, marker='o', markersize=4, label=category)
            for x_value, row in line.iterrows():
                segment_lines.append({'x_axis': x_name, 'x_value': x_value, 'segment': col, 'category': category,
                                      'listings': int(row['listings']), 'median_price': row['median']})
        ax.set_title(f'By {col} type' if col != 'transmission' else 'By transmission')
        ax.set_xlabel(x_label)
        ax.legend(title=None, frameon=False, loc='upper right' if x_name == 'odometer' else 'upper left')
        ax.xaxis.set_major_formatter(plt.FuncFormatter(
            (lambda v, _: f'{v / 1000:.0f}K') if x_name == 'odometer' else (lambda v, _: f'{v:.0f}')))
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'${v / 1000:.0f}K'))
        ax.set_ylim(bottom=0)
    axes[0].set_ylabel('Median asking price (band = middle 50%)')
    save_fig(f"price_vs_{x_name}_segments.png")

segment_lines = pd.DataFrame(segment_lines)
save_table(segment_lines, "price_by_segment_lines.csv")

# The gaps between the lines, at a typical mileage and at a recent model year
print("\n--- Median price by segment at 80,000-100,000 miles and for model year 2015 ---")
checkpoints = segment_lines[((segment_lines['x_axis'] == 'odometer') & (segment_lines['x_value'] == 90000)) |
                            ((segment_lines['x_axis'] == 'year') & (segment_lines['x_value'] == 2015))]
print(checkpoints.to_string(index=False))

# Overall median price of each segment value
segment_rows = []
for col in segments:
    summary = df.groupby(col)['price'].agg(listings='size', median_price='median').reset_index()
    summary = summary.rename(columns={col: 'value'})
    summary.insert(0, 'segment', col)
    segment_rows.append(summary)
segment_summary = pd.concat(segment_rows).sort_values(['segment', 'median_price'], ascending=[True, False])
print("\n--- Median price by segment ---")
print(segment_summary.to_string(index=False))
save_table(segment_summary, "price_by_segment.csv")

# --- A5: Feature engineering ---

# Reference year: all the ads were posted in April-May 2021,
# so the age of a vehicle is measured at the time it was listed.
REFERENCE_YEAR = 2021
print(f"\nPosting dates: {df['posting_date'].min()[:10]} to {df['posting_date'].max()[:10]}")

# Model year 2022 cars were already on sale in 2021 - their age is set to 0
df['vehicle_age'] = (REFERENCE_YEAR - df['year']).clip(lower=0)

# np.maximum(age, 1) makes sure we never divide by zero for new cars
df['miles_per_year'] = df['odometer'] / np.maximum(df['vehicle_age'], 1)

# Explicit rule: a vehicle is "Luxury" if its manufacturer is in this list
luxury_brands = ['acura', 'alfa-romeo', 'aston-martin', 'audi', 'bmw', 'cadillac', 'ferrari',
                 'infiniti', 'jaguar', 'land rover', 'lexus', 'lincoln', 'mercedes-benz',
                 'porsche', 'rover', 'tesla', 'volvo']
df['brand_segment'] = np.where(df['manufacturer'].isin(luxury_brands), 'Luxury', 'Standard')

# High cardinality: 'model' has thousands of free-text values.
# Keep the 20 most frequent models and group the rest as 'Other'.
top_20_models = df.loc[df['model'] != 'unknown', 'model'].value_counts().nlargest(20).index
df['model_grouped'] = np.where(df['model'].isin(top_20_models), df['model'], 'Other')

print("\n--- New features ---")
print(df[['year', 'vehicle_age', 'odometer', 'miles_per_year', 'brand_segment', 'model_grouped']].describe(include='all').T)
print(f"Models covered by the top 20: {(df['model_grouped'] != 'Other').mean() * 100:.1f}% of listings "
      f"({df['model'].nunique():,} distinct model strings in total)")

# --- A4: Brand analysis (median & IQR by manufacturer and era) ---

bins = [1989, 1999, 2009, 2019, 2022]
labels = ['1990-1999', '2000-2009', '2010-2019', '2020-2022']
df['year_bucket'] = pd.cut(df['year'], bins=bins, labels=labels)

brand_summary = (df[df['manufacturer'] != 'unknown']
                 .groupby('manufacturer')
                 .agg(listings=('price', 'size'), median_price=('price', 'median'),
                      q25=('price', q25), q75=('price', q75),
                      median_age=('vehicle_age', 'median'), median_odometer=('odometer', 'median'))
                 .reset_index())
brand_summary['iqr'] = brand_summary['q75'] - brand_summary['q25']
# Brands with very few listings are not reliable enough to compare
brand_summary = brand_summary[brand_summary['listings'] >= 500].sort_values('median_price', ascending=False)
print("\n--- Brand summary (brands with at least 500 listings) ---")
print(brand_summary.to_string(index=False))
save_table(brand_summary, "brand_summary.csv")

top_10_brands = df.loc[df['manufacturer'] != 'unknown', 'manufacturer'].value_counts().nlargest(10).index
df_top = df[df['manufacturer'].isin(top_10_brands)]

plt.figure(figsize=(15, 7))
sns.boxplot(data=df_top, x='manufacturer', y='price', hue='year_bucket',
            order=top_10_brands, palette='viridis', showfliers=False)
plt.yscale('log')
plt.title('Price by Manufacturer and Era (Median & IQR, 10 most listed brands)')
plt.xlabel('Manufacturer')
plt.ylabel('Price ($) - Log Scale')
plt.legend(title='Model year', loc='lower right', ncol=4)
save_fig("brand_price_by_era.png")

# --- A4: Depreciation curve (median price by vehicle age) ---

depreciation = (df.groupby('vehicle_age')['price']
                .agg(listings='size', median_price='median', q25=q25, q75=q75).reset_index())
depreciation = depreciation[depreciation['vehicle_age'] <= 25]

plt.figure(figsize=(10, 5.5))
plt.fill_between(depreciation['vehicle_age'], depreciation['q25'], depreciation['q75'],
                 alpha=0.25, label='Middle 50% of listings')
plt.plot(depreciation['vehicle_age'], depreciation['median_price'], marker='o', label='Median price')
plt.title('Depreciation Curve: Asking Price by Vehicle Age')
plt.xlabel('Vehicle age at listing (years)')
plt.ylabel('Price ($)')
plt.legend()
save_fig("depreciation_curve.png")
save_table(depreciation, "depreciation_curve.csv")

# --- A6: What drives price most? ---

# Linear regression on log(price). Working on the log scale means every
# coefficient reads as a percentage change in price, and the long right tail
# of expensive cars does not dominate the fit.
#
# 'year' and 'miles_per_year' are left out on purpose: year is the same
# information as vehicle_age, and miles_per_year is built from odometer and age.

# Readable baselines for the categorical features (the most common value)
baselines = {'type': 'sedan', 'fuel': 'gas', 'transmission': 'automatic', 'drive': 'fwd',
             'brand_segment': 'Standard', 'model_grouped': 'Other'}

df['odometer_10k'] = df['odometer'] / 10000
numeric_features = ['vehicle_age', 'odometer_10k']
categorical_features = list(baselines.keys())

X = df[numeric_features].copy()
for col, baseline in baselines.items():
    dummies = pd.get_dummies(df[col], prefix=col).drop(columns=[f"{col}_{baseline}"])
    X = pd.concat([X, dummies], axis=1)
y = np.log(df['price'])

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = LinearRegression()
model.fit(X_train, y_train)
y_pred = model.predict(X_test)

r2 = r2_score(y_test, y_pred)
# Typical error in dollar terms: median of |predicted - actual| / actual
median_pct_error = np.median(np.abs(np.exp(y_pred) - np.exp(y_test)) / np.exp(y_test)) * 100
print(f"\nModel fit on the test set: R2 = {r2:.3f} (log price), "
      f"median absolute error = {median_pct_error:.1f}% of the asking price")

# Summary table: effect of each feature as a % change in price
coefficients = pd.DataFrame({'feature': X.columns, 'coefficient': model.coef_})
coefficients['pct_effect'] = (np.exp(coefficients['coefficient']) - 1) * 100

def describe_feature(name):
    if name == 'vehicle_age':
        return 'Vehicle age', '+1 year'
    if name == 'odometer_10k':
        return 'Odometer', '+10,000 miles'
    for col, baseline in baselines.items():
        if name.startswith(col + '_'):
            return col, f"{name[len(col) + 1:]} (vs {baseline})"

coefficients[['group', 'label']] = [describe_feature(f) for f in coefficients['feature']]
group_names = {'type': 'Body type', 'fuel': 'Fuel type', 'transmission': 'Transmission', 'drive': 'Drive type',
               'brand_segment': 'Brand segment', 'model_grouped': 'Vehicle model'}
coefficients['group'] = coefficients['group'].replace(group_names)
coefficients = coefficients[['group', 'label', 'pct_effect', 'coefficient']].round(4)

print("\n--- Summary table: effect on asking price (holding the other features fixed) ---")
print(coefficients.to_string(index=False))
save_table(coefficients, "price_model_effects.csv")

# How much does each feature group matter?
# Importance = how much the test R2 drops when the group is removed from the model.
feature_groups = {'Vehicle age': ['vehicle_age'], 'Odometer': ['odometer_10k']}
for col in categorical_features:
    feature_groups[group_names[col]] = [c for c in X.columns if c.startswith(col + '_')]

importance = []
for group, cols in feature_groups.items():
    reduced = LinearRegression().fit(X_train.drop(columns=cols), y_train)
    r2_without = r2_score(y_test, reduced.predict(X_test.drop(columns=cols)))
    importance.append({'feature_group': group, 'r2_without': round(r2_without, 4),
                       'r2_drop': round(r2 - r2_without, 4)})
importance = pd.DataFrame(importance).sort_values('r2_drop', ascending=False)

print("\n--- Feature importance (drop in R2 when the feature group is removed) ---")
print(importance.to_string(index=False))
save_table(importance, "price_model_importance.csv")

# Plot 1 - feature importance
plt.figure(figsize=(9, 5))
sns.barplot(x='r2_drop', y='feature_group', data=importance, color='steelblue')
plt.title(f'What Drives Price Most? (full model R$^2$ = {r2:.2f})')
plt.xlabel('Drop in R2 when the feature is removed')
plt.ylabel('')
save_fig("price_drivers_importance.png")

# Plot 2 - actual vs predicted
actual_price, predicted_price = np.exp(y_test.values), np.exp(y_pred)
plot_idx = np.random.RandomState(42).choice(len(y_test), size=8000, replace=False)
dollar_ticks = [1000, 10000, 100000]

plt.figure(figsize=(7, 6.5))
plt.scatter(actual_price[plot_idx], predicted_price[plot_idx], alpha=0.28, s=7, color='#2a78d6', linewidths=0)
plt.plot([500, 200000], [500, 200000], color='#52514e', linestyle='--', lw=1.5, label='Perfect prediction')
plt.xscale('log')
plt.yscale('log')
plt.xticks(dollar_ticks, ['$1K', '$10K', '$100K'])
plt.yticks(dollar_ticks, ['$1K', '$10K', '$100K'])
plt.minorticks_off()
plt.annotate('Cheap listings are\npredicted too high', xy=(900, 14000), xytext=(560, 75000),
             fontsize=10, color='#52514e', arrowprops=dict(arrowstyle='->', color='#52514e'))
plt.title(f'Actual vs. Predicted Price (R$^2$ = {r2:.2f})')
plt.xlabel('Actual asking price')
plt.ylabel('Predicted price')
plt.legend(loc='lower right', frameon=False)
save_fig("price_actual_vs_predicted.png")

# Where does the model fail? Listings under $2,000 are usually cars with a problem
# the data does not record, or a down payment typed in as the price.
cheap = actual_price < 2000
error_by_price = pd.DataFrame([
    {'listings': 'Asking price under $2,000', 'test_rows': int(cheap.sum()),
     'median_predicted': round(np.median(predicted_price[cheap])),
     'predicted_more_than_double': round((predicted_price[cheap] > 2 * actual_price[cheap]).mean() * 100, 1)},
    {'listings': 'Asking price $2,000 and above', 'test_rows': int((~cheap).sum()),
     'median_predicted': round(np.median(predicted_price[~cheap])),
     'predicted_more_than_double': round((predicted_price[~cheap] > 2 * actual_price[~cheap]).mean() * 100, 1)},
])
print("\n--- Where the model fails: share of listings predicted at more than double the asking price ---")
print(error_by_price.to_string(index=False))
save_table(error_by_price, "price_model_error_by_price.csv")

# --- Robustness check: is the depreciation rate stable across segments? ---
# The same model is refitted separately inside each brand segment.
robustness = []
for seg in ['Standard', 'Luxury']:
    mask = df['brand_segment'] == seg
    seg_model = LinearRegression().fit(df.loc[mask, numeric_features], y[mask])
    robustness.append({'brand_segment': seg, 'listings': int(mask.sum()),
                       'pct_per_year': round((np.exp(seg_model.coef_[0]) - 1) * 100, 2),
                       'pct_per_10k_miles': round((np.exp(seg_model.coef_[1]) - 1) * 100, 2)})
robustness = pd.DataFrame(robustness)
print("\n--- Robustness: age and mileage effects inside each brand segment ---")
print(robustness.to_string(index=False))
save_table(robustness, "price_model_robustness.csv")

# --- Data for the dashboard ---

# Price histogram on log-spaced bins
log_edges = np.linspace(np.log10(500), np.log10(200000), 41)
log_counts, _ = np.histogram(np.log10(df['price']), bins=log_edges)

# Depreciation curve for all listings and for each of the 10 most listed brands
depreciation_by_brand = {'All brands': depreciation[['vehicle_age', 'median_price', 'listings']]
                         .to_dict(orient='list')}
for brand in top_10_brands:
    curve = (df[df['manufacturer'] == brand].groupby('vehicle_age')['price']
             .agg(listings='size', median_price='median').reset_index())
    # an age with only a handful of listings gives a noisy median
    curve = curve[(curve['vehicle_age'] <= 25) & (curve['listings'] >= 30)]
    depreciation_by_brand[brand] = curve[['vehicle_age', 'median_price', 'listings']].to_dict(orient='list')

save_dashboard_data("pricing", {
    'listings': len(df),
    'median_price': df['price'].median(),
    'median_age': df['vehicle_age'].median(),
    'median_odometer': df['odometer'].median(),
    'reference_year': REFERENCE_YEAR,
    'histogram': {'edges': np.round(10 ** log_edges).astype(int), 'counts': log_counts},
    'depreciation': depreciation_by_brand,
    'brands': brand_summary.head(40).to_dict(orient='records'),
    'segments': segment_summary.to_dict(orient='records'),
    'model': {'r2': round(r2, 3), 'median_pct_error': round(median_pct_error, 1),
              'train_rows': len(X_train), 'test_rows': len(X_test),
              'effects': coefficients.to_dict(orient='records'),
              'importance': importance.to_dict(orient='records'),
              'robustness': robustness.to_dict(orient='records')},
})

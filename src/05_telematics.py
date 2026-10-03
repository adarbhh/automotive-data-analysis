# -*- coding: utf-8 -*-
"""
Stage 5 - Vehicle telematics: signal inspection, data quality and driving features.

Input : data/raw/telematics.csv (OBD-II + phone sensor readings, about one row per second)
Output: data/processed/telematics_trip_features.csv
        docs/figures/telematics_*.png, reports/tables/telematics_*.csv

@author: Adar
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from utils import RAW_DIR, PROCESSED_DIR, save_fig, save_table, save_dashboard_data

# =============================================================================
# D1: TIME-SERIES INSPECTION
# =============================================================================

# --- 1. Load only the columns we need (the file is 330 MB) ---
needed_cols = ['tripID', 'deviceID', 'timeStamp', 'speed', 'gps_speed', 'rpm', 'x']
df = pd.read_csv(f"{RAW_DIR}/telematics.csv", usecols=needed_cols)

df['timeStamp'] = pd.to_datetime(df['timeStamp'], format='%d-%m-%Y %H:%M:%S', errors='coerce')
df = df.sort_values(['deviceID', 'timeStamp']).reset_index(drop=True)

# Time between consecutive rows of the same device
df['time_delta'] = df.groupby('deviceID')['timeStamp'].diff().dt.total_seconds()

# The 'tripID' column of the file is not a reliable trip identifier: one ID can cover
# recordings that are days apart. Trips are therefore rebuilt from the timestamps:
# a new trip starts whenever a device was silent for more than 2 minutes.
TRIP_BREAK_SECONDS = 120
print(f"Longest time span covered by a single original tripID: "
      f"{df.groupby('tripID')['timeStamp'].agg(lambda t: t.max() - t.min()).max()}")
new_trip = df['time_delta'].isna() | (df['time_delta'] > TRIP_BREAK_SECONDS)
df['trip'] = new_trip.cumsum()
df.loc[new_trip, 'time_delta'] = np.nan  # the first row of a trip has no previous row

print(f"Rows: {len(df):,} | Devices: {df['deviceID'].nunique()} | "
      f"Original tripIDs: {df['tripID'].nunique()} | Rebuilt trips: {df['trip'].nunique()}")
print(f"Period: {df['timeStamp'].min()} to {df['timeStamp'].max()}")
# Note: the source file was prepared in Excel and stops at 1,048,564 rows, right at the
# Excel row limit, so the last trip in the file is most likely cut in the middle.

# --- 2. Units and ranges ---
signal_info = {'speed': 'OBD speed (km/h)', 'gps_speed': 'GPS speed (km/h)',
               'rpm': 'Engine RPM', 'x': 'Accelerometer X (normalized, -1 to 1)'}
ranges = df[list(signal_info)].describe(percentiles=[0.5, 0.99]).T[['min', '50%', '99%', 'max']]
ranges.insert(0, 'signal', [signal_info[c] for c in ranges.index])
ranges['missing'] = df[list(signal_info)].isna().sum().values
print("\n--- Units and ranges ---")
print(ranges.round(2).to_string(index=False))
save_table(ranges.round(2), "telematics_signal_ranges.csv")

# --- 3. Plot the raw signals of one typical trip ---
trip_lengths = df.groupby('trip').size()
# a typical longer drive: the trip whose length is closest to 30 minutes of data
example_trip = (trip_lengths - 1800).abs().idxmin()
trip = df[df['trip'] == example_trip]
minutes = (trip['timeStamp'] - trip['timeStamp'].iloc[0]).dt.total_seconds() / 60

fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
axes[0].plot(minutes, trip['speed'], color='blue')
axes[0].set_title(f'Trip {example_trip}: Speed')
axes[0].set_ylabel('km/h')
axes[1].plot(minutes, trip['rpm'], color='green')
axes[1].set_title('Engine RPM')
axes[1].set_ylabel('RPM')
axes[2].plot(minutes, trip['x'], color='red')
axes[2].set_title('Accelerometer (X-axis)')
axes[2].set_ylabel('normalized')
axes[2].set_xlabel('Minutes from the start of the trip')
save_fig("telematics_example_trip.png")

# --- 4. Sampling distribution (time deltas between rows) ---
# Measured inside each trip, so the pause between two trips is not counted
deltas = df['time_delta'].dropna()

sampling = pd.DataFrame([
    {'interval': 'Duplicate timestamp (0 s)', 'rows': int((deltas == 0).sum())},
    {'interval': '1 s (nominal rate)', 'rows': int((deltas == 1).sum())},
    {'interval': '2 s', 'rows': int((deltas == 2).sum())},
    {'interval': '3 - 10 s', 'rows': int(deltas.between(3, 10).sum())},
    {'interval': f'11 - {TRIP_BREAK_SECONDS} s', 'rows': int((deltas > 10).sum())},
])
sampling['pct'] = (sampling['rows'] / len(deltas) * 100).round(2)
print("\n--- Sampling distribution (time deltas per trip) ---")
print(deltas.describe().round(3))
print(sampling.to_string(index=False))
save_table(sampling, "telematics_sampling.csv")

# --- 5. Data quality report ---
GAP_SECONDS = 10

# Sensor freeze: the accelerometer repeats exactly the same value for 10+ rows
# while the car is moving - a real sensor always shows some noise.
same_as_previous = df.groupby('trip')['x'].diff() == 0
run_id = (~same_as_previous).cumsum()
run_length = same_as_previous.groupby(run_id).transform('sum')
frozen = same_as_previous & (run_length >= 10) & (df['speed'] > 0)

# Sensor dropout vs true zero: the engine cannot be at 0 RPM while the car is moving
rpm_dropout = (df['rpm'] == 0) & (df['speed'] > 10)

# Two independent speed sources that disagree by more than 20 km/h
speed_mismatch = (df['speed'] - df['gps_speed']).abs() > 20

quality = pd.DataFrame([
    {'check': 'Missing accelerometer values', 'rows': int(df['x'].isna().sum())},
    {'check': 'Unparsed timestamps', 'rows': int(df['timeStamp'].isna().sum())},
    {'check': 'Duplicate timestamps inside a trip', 'rows': int((df['time_delta'] == 0).sum())},
    {'check': f'Missing intervals (gap > {GAP_SECONDS} s inside a trip)', 'rows': int((df['time_delta'] > GAP_SECONDS).sum())},
    {'check': 'Accelerometer frozen for 10+ rows while moving', 'rows': int(frozen.sum())},
    {'check': 'RPM = 0 while speed > 10 km/h (sensor dropout)', 'rows': int(rpm_dropout.sum())},
    {'check': 'OBD speed vs GPS speed differ by > 20 km/h', 'rows': int(speed_mismatch.sum())},
    {'check': 'GPS speed above 200 km/h (not plausible)', 'rows': int((df['gps_speed'] > 200).sum())},
])
quality['pct_of_rows'] = (quality['rows'] / len(df) * 100).round(3)
trips_with_gaps = df.loc[df['time_delta'] > GAP_SECONDS, 'trip'].nunique()
print("\n--- Data quality report ---")
print(quality.to_string(index=False))
print(f"Trips with at least one gap > {GAP_SECONDS} s: {trips_with_gaps} of {df['trip'].nunique()}")
save_table(quality, "telematics_quality_report.csv")

# =============================================================================
# D2: WINDOW FEATURES
# =============================================================================

# Acceleration from the speed signal: change in km/h per second -> m/s^2.
# Only computed between rows that are exactly 1 second apart, so a gap in the
# data is never read as a sudden braking.
speed_change = df.groupby('trip')['speed'].diff()
df['accel_ms2'] = np.where(df['time_delta'] == 1, speed_change / 3.6, np.nan)

# Rolling windows look backwards only (the current row and the 9 rows before it),
# so a feature never uses information from the future.
WINDOW = 10
grouped_speed = df.groupby('trip')['speed']
df['speed_mean_10s'] = grouped_speed.transform(lambda s: s.rolling(WINDOW, min_periods=WINDOW).mean())
df['speed_std_10s'] = grouped_speed.transform(lambda s: s.rolling(WINDOW, min_periods=WINDOW).std())

# Common thresholds for harsh events: about 0.3 g
HARSH_THRESHOLD = 3.0  # m/s^2
df['harsh_brake'] = df['accel_ms2'] < -HARSH_THRESHOLD
df['harsh_accel'] = df['accel_ms2'] > HARSH_THRESHOLD
df['idle'] = (df['speed'] == 0) & (df['rpm'] > 0)
# Distance covered since the previous row (speed in km/h x seconds / 3600)
df['km'] = df['speed'] * df['time_delta'].fillna(0) / 3600

# --- Trip-level feature table ---
trip_features = df.groupby('trip').agg(
    deviceID=('deviceID', 'first'),
    start=('timeStamp', 'min'),
    duration_min=('timeStamp', lambda t: (t.max() - t.min()).total_seconds() / 60),
    rows=('speed', 'size'),
    distance_km=('km', 'sum'),
    mean_speed=('speed', 'mean'),
    max_speed=('speed', 'max'),
    speed_std_10s_mean=('speed_std_10s', 'mean'),
    harsh_brakes=('harsh_brake', 'sum'),
    harsh_accels=('harsh_accel', 'sum'),
    idle_share=('idle', 'mean'),
).reset_index()
# Very short recordings (under 2 minutes or under 0.5 km) are not real drives
trip_features = trip_features[(trip_features['duration_min'] >= 2) & (trip_features['distance_km'] >= 0.5)].copy()
# Normalized per 100 km so short and long trips can be compared
trip_features['harsh_events_per_100km'] = ((trip_features['harsh_brakes'] + trip_features['harsh_accels'])
                                           / trip_features['distance_km'] * 100)
trip_features = trip_features.round(2)
trip_features.to_csv(f"{PROCESSED_DIR}/telematics_trip_features.csv", index=False)

print("\n--- Trip features ---")
print(trip_features[['duration_min', 'distance_km', 'mean_speed', 'max_speed', 'harsh_brakes',
                     'harsh_accels', 'idle_share', 'harsh_events_per_100km']].describe().round(2).T)
print(f"\nSaved {PROCESSED_DIR}/telematics_trip_features.csv")

# Drivers compared: harsh events per 100 km by device
device_summary = trip_features.groupby('deviceID').agg(
    trips=('trip', 'size'), distance_km=('distance_km', 'sum'),
    harsh_events=('harsh_brakes', 'sum'), harsh_accels=('harsh_accels', 'sum'),
    idle_share=('idle_share', 'mean')).reset_index()
device_summary['harsh_events'] = device_summary['harsh_events'] + device_summary['harsh_accels']
device_summary['harsh_events_per_100km'] = (device_summary['harsh_events'] / device_summary['distance_km'] * 100).round(1)
device_summary = device_summary.drop(columns='harsh_accels').round(2).sort_values('harsh_events_per_100km', ascending=False)
# A rate measured over a few kilometres is not reliable - keep devices with at least 100 km
device_summary = device_summary[device_summary['distance_km'] >= 100]
print("\n--- Harsh events per 100 km by device ---")
print(device_summary.to_string(index=False))
save_table(device_summary, "telematics_device_summary.csv")

plt.figure(figsize=(9, 5))
plt.bar(device_summary['deviceID'].astype(int).astype(str), device_summary['harsh_events_per_100km'], color='steelblue')
plt.title('Harsh Braking / Acceleration Events per 100 km by Device')
plt.xlabel('Device ID')
plt.ylabel('Events per 100 km')
save_fig("telematics_harsh_events_by_device.png")

# Downsampled example trip for the dashboard (one point every 5 seconds)
trip_plot = trip.iloc[::5]
save_dashboard_data("telematics", {
    'rows': len(df),
    'trips': len(trip_features),
    'original_trip_ids': int(df['tripID'].nunique()),
    'devices': int(df['deviceID'].nunique()),
    'devices_compared': len(device_summary),
    'nominal_rate_pct': float(sampling.loc[1, 'pct']),
    'sampling': sampling.to_dict(orient='records'),
    'quality': quality.to_dict(orient='records'),
    'total_distance_km': round(trip_features['distance_km'].sum()),
    'median_trip_min': round(trip_features['duration_min'].median(), 1),
    'devices_summary': device_summary.to_dict(orient='records'),
    'example_trip': {'trip_id': int(example_trip),
                     'minutes': (minutes.iloc[::5]).round(2).tolist(),
                     'speed': trip_plot['speed'].tolist(),
                     'rpm': trip_plot['rpm'].tolist()},
})

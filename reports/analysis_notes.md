# Analysis notes

Methodology, definitions and limitations for each stage. The numbers quoted here are written by the scripts to `reports/tables/`, where they can be checked.

## Stage 1: Cleaning the used-car listings

**Dataset:** Craigslist Cars & Trucks (Kaggle, Austin Reese). 426,880 rows, 26 columns. All ads were posted between 4 April and 4 May 2021.

### Data dictionary

| Column | Meaning | Values / range |
|--------|---------|----------------|
| id | Unique ID of the ad (stable identifier) | |
| url, region_url, image_url | Links to the ad, the regional site and the image | not loaded |
| region | Craigslist region of the ad | 404 regions |
| price | Asking price in USD (**target**) | 0 to 3.7 billion in the raw data |
| year | Model year | 1900 to 2022 |
| manufacturer | Vehicle brand | 42 brands |
| model | Vehicle model, free text (high cardinality) | about 29,600 distinct values |
| condition | Condition stated by the seller | good, excellent, fair, like new, new, salvage |
| cylinders | Engine cylinders | 3 to 12, other |
| fuel | Fuel type | gas, diesel, hybrid, electric, other |
| odometer | Mileage in miles | 0 to 10,000,000 in the raw data |
| title_status | Title status | clean, rebuilt, lien, salvage, missing, parts only |
| transmission | Transmission | automatic, manual, other |
| VIN | Vehicle Identification Number (stable identifier) | missing for 37.7% |
| drive | Drive type | fwd, rwd, 4wd |
| size | Size category | missing for 71.8% |
| type | Body type | 13 values |
| paint_color | Colour | 12 values |
| description | Free text written by the seller | not loaded |
| county | Empty column | 100% missing |
| state | US state | 51 values |
| lat, long | Coordinates | |
| posting_date | Date the ad was posted | |

### Missing values

| Decision | Columns | Reason |
|----------|---------|--------|
| Drop column | county (100%), size (71.8%) | Empty or mostly empty. |
| Drop rows | price (7.7%, zero treated as missing), year (0.3%), odometer (1.0%) | Price is the target and year and odometer are the main predictors. Imputing them would invent the values the analysis is about. |
| Keep as "unknown" | cylinders, condition, drive, paint_color, type, manufacturer, model, title_status, fuel, transmission | A missing value becomes its own category. Filling with the most common value would invent data. |
| Keep empty | VIN | It is an identifier, not a category. |
| Not loaded | description, url, region_url, image_url | Not used by the analysis and most of the 1.4 GB file size. |

### Validity rules and de-duplication

Rules are applied in order and each removed row is counted under the first rule it breaks.

| Step | Rows removed | % of raw |
|------|-------------:|---------:|
| Price missing or zero | 32,895 | 7.71% |
| Price outside $500 to $200,000 | 9,323 | 2.18% |
| Year missing or outside 1990 to 2022 | 13,007 | 3.05% |
| Odometer missing or outside 0 to 400,000 miles | 3,132 | 0.73% |
| Exact duplicate rows or duplicate ad IDs | 0 | 0.00% |
| Same vehicle listed again (duplicate VIN, most recent ad kept) | 131,397 | 30.78% |
| Same ad reposted without a VIN (same make, model, year, odometer and price) | 32,271 | 7.56% |
| **Clean dataset** | **204,855 rows remain** | **48.0%** |

**Bias introduced by the rules.** The price floor removes "call for price" and down-payment ads, the year floor removes classic cars (a different market), and the odometer cap removes typing errors along with a few genuine very-high-mileage vehicles. The near-duplicate rule can merge two different cars that share all five values, which is rare.

**Leakage check.** Every remaining column is known when the ad is posted. There is no sale date, sold status or final price, so no column leaks the target.

## Stage 2: EDA, features and price drivers

### Feature definitions

| Feature | Definition | Notes |
|---------|------------|-------|
| vehicle_age | 2021 − model year, minimum 0 | 2021 is the year all ads were posted, so this is the age at listing. Model year 2022 cars are age 0. |
| miles_per_year | odometer / max(vehicle_age, 1) | The floor of 1 avoids dividing by zero for new cars. |
| brand_segment | "Luxury" if the manufacturer is in a fixed list, otherwise "Standard" | Luxury list: Acura, Alfa Romeo, Aston Martin, Audi, BMW, Cadillac, Ferrari, Infiniti, Jaguar, Land Rover, Lexus, Lincoln, Mercedes-Benz, Porsche, Tesla, Volvo. |
| model_grouped | The 20 most frequent models, all others grouped as "Other" | Encoding all model strings would create thousands of sparse columns. The top 20 cover 15.7% of the listings. |
| year_bucket | 1990-1999, 2000-2009, 2010-2019, 2020-2022 | Used for the brand comparison. |

All features are available at the time an ad is posted, so they are safe to use for prediction.

### Why log(price)

Raw prices are strongly right-skewed (skewness 2.33). On a log scale the distribution is close to symmetric (skewness −0.43), the variance is more stable across the price range, and regression coefficients read as percentage changes.

### Price model

- Linear regression on log(price), 80/20 train/test split with a fixed seed.
- Features: vehicle_age, odometer, body type, fuel, transmission, drive, brand_segment, model_grouped.
- `year` is left out because it is the same information as vehicle_age. `miles_per_year` is left out because it is built from odometer and age.
- Categorical baselines are the most common values (sedan, gas, automatic, fwd, Standard, Other).
- Test set: R² = 0.58 on log price, median absolute error 25% of the asking price.

**Feature importance** is the drop in test R² when a feature group is removed and the model is refitted: vehicle age 0.139, odometer 0.042, fuel type 0.029, body type 0.021, drive type 0.018, vehicle model 0.006, brand segment 0.006, transmission 0.002.

**Robustness.** Refitting age and mileage separately inside each brand segment gives −6.6% per year for both Standard and Luxury brands. Mileage costs more for luxury brands (−5.2% per 10,000 miles against −3.1%).

**Alternative explanations.** The diesel premium (+108% against gas) is confounded with heavy-duty trucks. The 4WD premium partly reflects trucks and SUVs. Manual transmission shows a small positive effect because manuals are concentrated in sports and off-road vehicles.

## Stage 3: Recalls

**Dataset:** NHTSA recalls export, 29,712 recalls from 1966 to 28 January 2026. 2026 is excluded from yearly trends because it covers only four weeks.

### Pattern analysis

- **Name normalization.** Lowercase, bracketed text and punctuation removed, legal suffixes dropped: 3,066 raw names become 3,027.
- **Manufacturer groups.** A recall is filed by the corporate entity, not the brand, so 21 passenger-car makers are mapped to groups with explicit patterns. The full mapping is in `tables/recall_manufacturer_mapping.csv`.
- **Spikes.** A year is a spike when a manufacturer's count is more than 2 standard deviations above its own average. Only the 51 manufacturers with at least 100 recalls are tested, because small filers produce meaningless Z-scores. 164 spikes were found; the largest is Ford in 2025 (153 recalls, Z = 5.7).
- **Structural breaks.** The 2016-2025 average is at least double the 2006-2015 average and at least 5 recalls per year. 16 manufacturers qualify, led by Kia (5.0x) and Mercedes-Benz (4.9x).
- **Exposure bias.** Both methods compare a manufacturer with its own history, which removes the size effect. The export has no sales figures, so recalls per vehicle sold cannot be computed. As a partial check, manufacturers are also ranked by units affected.

### Text analysis

- Text: the consequence summary (available for 24,823 recalls, mostly after 1990), lowercased and stripped to letters.
- Boilerplate such as "increasing the risk of a crash" is removed before vectorizing, so topics describe the failure.
- TF-IDF (unigrams and bigrams) followed by NMF with 8 topics. K-Means on the same matrix put about 70% of recalls in one cluster, so NMF was used.
- Topics were named after reading their top terms and most representative examples. One topic ("Brakes, tires & other") is a broad bucket holding 45% of the recalls.

### Severity proxy

| Score | Rule |
|-------|------|
| 3 (High) | Mentions fire, burn, explosion, death, loss of control / steering / braking, rollaway, stall, loss of drive power or unintended movement |
| 2 (Medium) | Mentions crash, collision, accident or injury, without a high-severity term |
| 1 (Low) | None of the above |

**Validation.** NHTSA's "park outside" and "do not drive" advisories are not used by the proxy. 100% of park-outside recalls and 69.6% of do-not-drive recalls were scored High, against 39.4% of all recalls.

**Failure modes.** False positives: a summary that mentions fire only as a remote possibility. False negatives: a serious defect described in mild or unusual wording. The proxy should support human triage, never replace it.

### Join to the listings

| Level | Key | Source of the key in the recalls |
|-------|-----|----------------------------------|
| 1 | Manufacturer group | Explicit name patterns |
| 2 | + model year | Years and year ranges in the sentence that announces the recall |
| 3 | + model name | First word of the listing's model, found in the same sentence |

Only the announcing sentence is searched, because the rest of the description explains the defect and contains words such as "bolt", "spark" or "escape" that are also model names.

Recalls are aggregated to one row per key before joining, so the join is many-to-one. The listing count is asserted to be unchanged (204,855 before and after).

**Features added to each listing:** `recalled_flag` (at least one recall for the model and year), `recall_count` (number of such recalls) and `mfr_year_recall_count`.

**Coverage, listing side:** 96.7% of listings map to a manufacturer group, 88.3% have a usable model name, and 75.9% have at least one recall for their model and year.

**Coverage, recall side:** 11.7% of recalls match at model level, 2.3% at manufacturer + year, 18.9% at manufacturer only (77% of these were reported before 2005 and have no model year in the text), 12.9% are tire, equipment or child-seat recalls, and 54.2% belong to manufacturers that are not in the listings (trucks, buses, trailers and RVs).

## Stage 4: VIN decoding

- **Sample.** 1,000 VINs drawn at random (fixed seed) from the 100,134 clean listings with a valid 17-character VIN. 293 malformed VINs were found.
- **API.** NHTSA vPIC batch endpoint, 50 VINs per request, one-second pause between requests, three retries, raw responses cached to disk.
- **Result.** 999 decoded, 1 failed, 6 decoded with a check-digit or position warning.
- **Coverage.** Engine displacement 99.0%, body class 99.8%, fuel type 96.6%, drivetrain 73.2%.

### Listing vs. decoder

Values are normalized before comparing: makes are lowercased and Ram / Dodge are treated as one make, the decoder's AWD and 4WD both map to the listings' "4wd", and "4x2" is treated as compatible with both fwd and rwd.

| Field | Compared | Gaps filled | Conflicts |
|-------|---------:|------------:|----------:|
| Manufacturer | 977 | 22 | 3 (0.3%) |
| Model year | 999 | 0 | 3 (0.3%) |
| Drive type | 579 | 152 | 12 (2.1%) |
| Fuel type | 850 | 86 | 4 (0.5%) |

### Decisions

| Decision | When | Count |
|----------|------|------:|
| Drop | The VIN could not be decoded, so nothing can be verified | 1 |
| Correct | Model year conflict. The VIN encodes the year, so the decoder is the source of truth | 3 |
| Flag | Manufacturer conflict. Either the VIN or the brand was typed wrong, which needs a person | 3 |
| Keep | No issue | 993 |

All corrections are made on a copy, and the original year is kept in `year_original`.

**Does enrichment change the conclusions?** Unknown drive types in the sample fall from 235 to 83 and most turn out to be 4WD / AWD. The median 4WD price moves from $21,999 to $22,995, so the stage 2 finding that 4WD vehicles are priced higher holds.

## Stage 5: Telematics

**Dataset:** OBD-II and phone sensor readings from 8 vehicles, 18 November to 31 December 2017, 1,048,564 rows. The source file stops at the Excel row limit, so its last recording is probably cut.

- **Trips.** The `tripID` column is not reliable: a single ID covers up to 42 days. Trips are rebuilt from timestamps, with a new trip after 2 minutes of silence from a device. This gives 1,092 segments, of which 841 are real drives (at least 2 minutes and 0.5 km).
- **Sampling.** 98.5% of consecutive readings are exactly 1 second apart. 0.67% are duplicate timestamps and 0.06% are gaps longer than 10 seconds.
- **Quality.** The accelerometer repeats the same value for 10 or more rows while the car is moving in 20.8% of the readings. OBD and GPS speed differ by more than 20 km/h in 2.7% of the readings.
- **Features.** Acceleration is computed from the OBD speed signal, only between rows exactly 1 second apart, so a gap is never read as a harsh event. Rolling windows cover the current and the previous 9 seconds, never the future. Harsh events are changes above 3 m/s².
- **Result.** Harsh events per 100 km range from 5.2 to 28.4 across the five vehicles with at least 100 km of data.

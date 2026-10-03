window.DASHBOARD = window.DASHBOARD || {};
window.DASHBOARD.cleaning = {
 "raw_rows": 426880,
 "clean_rows": 204855,
 "raw_columns": 26,
 "audit": [
  {
   "step": "Price missing or zero",
   "rows_removed": 32895,
   "rows_remaining": 393985,
   "pct_of_original": 7.71
  },
  {
   "step": "Price outside $500 - $200,000",
   "rows_removed": 9323,
   "rows_remaining": 384662,
   "pct_of_original": 2.18
  },
  {
   "step": "Year missing or outside 1990 - 2022",
   "rows_removed": 13007,
   "rows_remaining": 371655,
   "pct_of_original": 3.05
  },
  {
   "step": "Odometer missing or outside 0 - 400,000 miles",
   "rows_removed": 3132,
   "rows_remaining": 368523,
   "pct_of_original": 0.73
  },
  {
   "step": "Exact duplicate rows / duplicate ad IDs",
   "rows_removed": 0,
   "rows_remaining": 368523,
   "pct_of_original": 0.0
  },
  {
   "step": "Same vehicle listed again (duplicate VIN)",
   "rows_removed": 131397,
   "rows_remaining": 237126,
   "pct_of_original": 30.78
  },
  {
   "step": "Same ad reposted without a VIN (same car details and price)",
   "rows_removed": 32271,
   "rows_remaining": 204855,
   "pct_of_original": 7.56
  }
 ],
 "missingness": [
  {
   "column": "county",
   "missing_pct": 100.0,
   "decision": "drop column"
  },
  {
   "column": "size",
   "missing_pct": 71.77,
   "decision": "drop column"
  },
  {
   "column": "cylinders",
   "missing_pct": 41.62,
   "decision": "keep as unknown"
  },
  {
   "column": "condition",
   "missing_pct": 40.79,
   "decision": "keep as unknown"
  },
  {
   "column": "VIN",
   "missing_pct": 37.73,
   "decision": "keep (identifier, left empty)"
  },
  {
   "column": "drive",
   "missing_pct": 30.59,
   "decision": "keep as unknown"
  },
  {
   "column": "paint_color",
   "missing_pct": 30.5,
   "decision": "keep as unknown"
  },
  {
   "column": "type",
   "missing_pct": 21.75,
   "decision": "keep as unknown"
  },
  {
   "column": "price",
   "missing_pct": 7.71,
   "decision": "drop rows"
  },
  {
   "column": "manufacturer",
   "missing_pct": 4.13,
   "decision": "keep as unknown"
  },
  {
   "column": "title_status",
   "missing_pct": 1.93,
   "decision": "keep as unknown"
  },
  {
   "column": "lat",
   "missing_pct": 1.53,
   "decision": "keep (not used)"
  },
  {
   "column": "long",
   "missing_pct": 1.53,
   "decision": "keep (not used)"
  },
  {
   "column": "model",
   "missing_pct": 1.24,
   "decision": "keep as unknown"
  },
  {
   "column": "odometer",
   "missing_pct": 1.03,
   "decision": "drop rows"
  },
  {
   "column": "fuel",
   "missing_pct": 0.71,
   "decision": "keep as unknown"
  },
  {
   "column": "transmission",
   "missing_pct": 0.6,
   "decision": "keep as unknown"
  },
  {
   "column": "year",
   "missing_pct": 0.28,
   "decision": "drop rows"
  },
  {
   "column": "posting_date",
   "missing_pct": 0.02,
   "decision": "keep (not used)"
  }
 ]
};

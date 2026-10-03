window.DASHBOARD = window.DASHBOARD || {};
window.DASHBOARD.vin = {
 "listings": 204855,
 "with_vin_pct": 49.0,
 "malformed_vins": 293,
 "sample_size": 1000,
 "decoded": 999,
 "failure_rate": 0.1,
 "coverage": [
  {
   "field": "Engine displacement",
   "populated": 990,
   "coverage_pct": 99.0
  },
  {
   "field": "Body class",
   "populated": 998,
   "coverage_pct": 99.8
  },
  {
   "field": "Drivetrain",
   "populated": 732,
   "coverage_pct": 73.2
  },
  {
   "field": "Fuel type",
   "populated": 966,
   "coverage_pct": 96.6
  }
 ],
 "audit": [
  {
   "field": "Manufacturer",
   "compared": 977,
   "gaps_filled": 22,
   "conflicts": 3,
   "conflict_pct": 0.3
  },
  {
   "field": "Model year",
   "compared": 999,
   "gaps_filled": 0,
   "conflicts": 3,
   "conflict_pct": 0.3
  },
  {
   "field": "Drive type",
   "compared": 579,
   "gaps_filled": 152,
   "conflicts": 12,
   "conflict_pct": 2.1
  },
  {
   "field": "Fuel type",
   "compared": 850,
   "gaps_filled": 86,
   "conflicts": 4,
   "conflict_pct": 0.5
  }
 ],
 "drive_before_after": [
  {
   "drive": "2wd",
   "listings_before": 0,
   "median_price_before": NaN,
   "listings_after": 35,
   "median_price_after": 11550.0
  },
  {
   "drive": "4wd",
   "listings_before": 313,
   "median_price_before": 21999.0,
   "listings_after": 419,
   "median_price_after": 22995.0
  },
  {
   "drive": "fwd",
   "listings_before": 320,
   "median_price_before": 10444.0,
   "listings_after": 331,
   "median_price_after": 10488.0
  },
  {
   "drive": "rwd",
   "listings_before": 132,
   "median_price_before": 15994.5,
   "listings_after": 132,
   "median_price_after": 15994.5
  },
  {
   "drive": "unknown",
   "listings_before": 235,
   "median_price_before": 16995.0,
   "listings_after": 83,
   "median_price_after": 12500.0
  }
 ],
 "validation": [
  {
   "rule": "Electric vehicle with an engine displacement",
   "violations": 0,
   "violation_pct": 0.0,
   "example_vin": ""
  },
  {
   "rule": "Combustion vehicle without an engine displacement",
   "violations": 3,
   "violation_pct": 0.3,
   "example_vin": "1HGCP28878A149515"
  },
  {
   "rule": "Model year out of range",
   "violations": 0,
   "violation_pct": 0.0,
   "example_vin": ""
  },
  {
   "rule": "Pickup without a drivetrain",
   "violations": 3,
   "violation_pct": 0.3,
   "example_vin": "1GC1KTEY0KF190901"
  },
  {
   "rule": "Listed year more than 1 year off the decoded year",
   "violations": 3,
   "violation_pct": 0.3,
   "example_vin": "19XFB2F55FE119763"
  }
 ],
 "taxonomy": [
  {
   "error_type": "Listing error",
   "category": "Manufacturer conflict",
   "count": 3,
   "pct_of_sample": 0.3
  },
  {
   "error_type": "Listing error",
   "category": "Model year conflict",
   "count": 3,
   "pct_of_sample": 0.3
  },
  {
   "error_type": "Listing error",
   "category": "Drive type conflict",
   "count": 12,
   "pct_of_sample": 1.2
  },
  {
   "error_type": "Listing error",
   "category": "Fuel type conflict",
   "count": 4,
   "pct_of_sample": 0.4
  },
  {
   "error_type": "Decoder missingness",
   "category": "VIN not decoded",
   "count": 1,
   "pct_of_sample": 0.1
  },
  {
   "error_type": "Decoder missingness",
   "category": "Missing engine",
   "count": 10,
   "pct_of_sample": 1.0
  },
  {
   "error_type": "Decoder missingness",
   "category": "Missing drivetrain",
   "count": 267,
   "pct_of_sample": 26.7
  },
  {
   "error_type": "Decoder missingness",
   "category": "Missing body class",
   "count": 2,
   "pct_of_sample": 0.2
  }
 ],
 "decisions": [
  {
   "action": "Keep",
   "listings": 993,
   "pct_of_sample": 99.3
  },
  {
   "action": "Correct",
   "listings": 3,
   "pct_of_sample": 0.3
  },
  {
   "action": "Flag",
   "listings": 3,
   "pct_of_sample": 0.3
  },
  {
   "action": "Drop",
   "listings": 1,
   "pct_of_sample": 0.1
  }
 ]
};

# Tax Reconciliation

Matches invoices, bank payments and ledger entries, then finds wrong GST, duplicates, missing records and unusual invoices.

Built for Fintechstico (Consilium'26, NSUT) — Problem Statement 2 by **Team Fourier**.

## Features
- Synthetic data generator with planted errors (so accuracy is measurable)
- Exact + fuzzy matching (rapidfuzz) across three sources
- GST slab recomputation (5, 12, 18, 28%)
- Duplicate and missing-record detection
- Isolation Forest for unusual records that rules miss
- Monthly net GST liability and ITC-at-risk
- Precision and recall per error type against the planted ground truth
- Papery Flask dashboard with Plotly charts
- Excel and CSV report downloads

## Run locally
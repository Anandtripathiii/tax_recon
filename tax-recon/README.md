# Tax reconciliation (Fintechstico PS2)

Matches invoices, bank payments and ledger entries, then finds wrong GST, duplicates, missing records and unusual invoices.

## Run it (Windows)
    py -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    streamlit run app.py

Check accuracy without the dashboard: `python engine.py`. Save the sample CSVs: `python generator.py`.

## Files
- generator.py : makes fake invoices, bank and ledger records and plants errors (keeps a hidden answer table)
- engine.py    : matching, tax check, duplicates, missing records, Isolation Forest, GST liability, accuracy scoring
- app.py       : the dashboard

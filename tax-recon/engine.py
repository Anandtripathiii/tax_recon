"""Reconciliation engine: match, check tax, find duplicates and gaps, score odd records,
estimate GST liability, and measure accuracy against the planted errors."""
import re
import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process, utils
from sklearn.ensemble import IsolationForest

SLABS = {5, 12, 18, 28}
ID_RE = re.compile(r"INV-?(\d{4,})", re.I)
MATCH_SCORE = 0.85        # fuzzy match needs at least this score
TAX_TOLERANCE = 1         # rupees
PAY_LATE_DAYS = 35        # bank payment later than this after invoice date is flagged
LEDGER_LATE_DAYS = 7
FEATURES = ["log_amount", "party_z", "tax_ratio", "pay_lag", "weekday", "is_round"]


def invoice_id_from(text):
    m = ID_RE.search(str(text))
    return f"INV-{m.group(1)}" if m else None


def _find_duplicates(inv):
    """Same party and total within 7 days of an earlier invoice = duplicate."""
    key = inv.gstin.astype(str) + "|" + inv.total.round(2).astype(str)
    s = inv.sort_values(["gstin", "total", "date"])
    prev_key = s.groupby(key)["date"].shift()
    gap = (s["date"] - prev_key).dt.days
    s["dup"] = gap.le(7).fillna(False)
    inv["dup"] = s["dup"].reindex(inv.index)


def _match_payments(inv, bank, fuzzy):
    bank["inv_ref"] = bank.narration.map(invoice_id_from)
    base = inv[~inv.dup]
    exact = bank[bank.inv_ref.isin(set(base.invoice_id))].drop_duplicates("inv_ref")
    inv["txn_id"] = inv.invoice_id.map(dict(zip(exact.inv_ref, exact.txn_id))).where(~inv.dup)
    inv["match"] = np.where(inv.txn_id.notna(), "exact", "none")
    if not fuzzy:
        return
    li = inv[inv.txn_id.isna() & ~inv.dup]
    lb = bank[~bank.txn_id.isin(inv.txn_id.dropna())]
    if li.empty or lb.empty:
        return
    clean = lb.narration.str.replace(r"(?i)\b(neft|upi|imps|rtgs)\b|INV-?\d+", " ", regex=True)
    name = process.cdist(li.party.tolist(), clean.tolist(), scorer=fuzz.WRatio,
                         processor=utils.default_process, workers=-1) / 100
    a, b = li.total.values[:, None], lb.amount.values[None, :]
    amount = np.clip(1 - np.abs(a - b) / a / 0.02, 0, 1)                    # 1 if equal, 0 if 2% or more apart
    lag = (lb.date.values[None, :] - li.date.values[:, None]).astype("timedelta64[D]").astype(int)
    date = np.clip(1 - np.maximum(lag - 30, 0) / 30, 0, 1) * (lag >= -1)    # paid within 30 days is a full score
    same_way = np.asarray(li.type.map({"sales": "in", "purchase": "out"}))[:, None] == np.asarray(lb.direction)[None, :]
    score = (0.5 * name + 0.3 * amount + 0.2 * date) * same_way
    used_i, used_b = set(), set()
    for i, j in sorted(np.argwhere(score >= MATCH_SCORE), key=lambda ij: -score[ij[0], ij[1]]):
        if i in used_i or j in used_b:
            continue
        used_i.add(i), used_b.add(j)
        inv.at[li.index[i], "txn_id"] = lb.txn_id.iloc[j]
        inv.at[li.index[i], "match"] = "fuzzy"


def _anomaly_scores(inv):
    d = inv
    d["log_amount"] = np.log1p(d.total)
    g = d.groupby("party").log_amount
    d["party_z"] = ((d.log_amount - g.transform("mean")) / g.transform("std").replace(0, 1).fillna(1))
    d["tax_ratio"] = d.tax_amount / d.taxable_value
    d["pay_lag"] = d.bank_lag.fillna(d.bank_lag.median())
    d["weekday"] = d.date.dt.dayofweek
    d["is_round"] = (d.taxable_value % 1000 == 0).astype(int)
    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42, n_jobs=-1).fit(d[FEATURES])
    s = -model.score_samples(d[FEATURES])
    d["anomaly_score"] = (s - s.min()) / (s.max() - s.min())
    d["anomaly"] = model.predict(d[FEATURES]) == -1


def run_all(inv, bank, led, fuzzy=True):
    inv, bank, led = inv.copy(), bank.copy(), led.copy()
    for d in (inv, bank, led):
        d["date"] = pd.to_datetime(d["date"])
    inv = inv.sort_values(["date", "row_id"]).reset_index(drop=True)
    _find_duplicates(inv)
    _match_payments(inv, bank, fuzzy)

    b = bank.set_index("txn_id")
    inv["bank_amount"], inv["bank_date"] = inv.txn_id.map(b.amount), inv.txn_id.map(b.date)
    lg = led.drop_duplicates("invoice_ref").set_index("invoice_ref")
    for col, src in [("entry_id", "entry_id"), ("led_amount", "amount"), ("led_date", "date")]:
        inv[col] = inv.invoice_id.map(lg[src]).where(~inv.dup)
    inv["bank_lag"] = (inv.bank_date - inv.date).dt.days
    inv["led_lag"] = (inv.led_date - inv.date).dt.days
    inv["expected_tax"] = (inv.taxable_value * inv.gst_rate / 100).round(2)

    flags, ok = [], ~inv.dup

    def add(mask, kind, msg):
        for i in inv.index[mask]:
            flags.append((inv.at[i, "row_id"], "invoice", kind, msg(inv.loc[i])))

    gap = (inv.tax_amount - inv.expected_tax).abs()
    add(ok & ((gap > TAX_TOLERANCE) | ~inv.gst_rate.isin(SLABS)), "wrong_gst",
        lambda r: f"{r.gst_rate}% is not a valid GST slab" if r.gst_rate not in SLABS else
        f"Tax charged Rs {r.tax_amount:,.0f}, but {r.gst_rate}% of Rs {r.taxable_value:,.0f} is Rs {r.expected_tax:,.0f}")
    add(ok & inv.txn_id.isna(), "missing_payment", lambda r: "No bank payment found for this invoice")
    add(ok & inv.entry_id.isna(), "missing_ledger", lambda r: "No ledger entry found for this invoice")
    add(ok & (((inv.bank_amount - inv.total).abs() > 1) | ((inv.led_amount - inv.total).abs() > 1)), "amount_mismatch",
        lambda r: f"Invoice Rs {r.total:,.0f}, bank Rs {r.bank_amount:,.0f}, ledger Rs {r.led_amount:,.0f}")
    add(ok & ((inv.bank_lag > PAY_LATE_DAYS) | (inv.led_lag > LEDGER_LATE_DAYS)), "date_shift",
        lambda r: f"Bank paid {r.bank_lag:.0f} days after the invoice" if r.bank_lag > PAY_LATE_DAYS
        else f"Ledger entry is {r.led_lag:.0f} days after the invoice")
    add(inv.dup, "duplicate", lambda r: f"Same party and amount (Rs {r.total:,.0f}) as an earlier invoice within 7 days")
    for r in bank[~bank.txn_id.isin(inv.txn_id.dropna())].itertuples():
        flags.append((r.txn_id, "bank", "orphan_payment", f"Payment of Rs {r.amount:,.0f} ({r.narration}) has no invoice"))
    flags = pd.DataFrame(flags, columns=["key", "kind", "error_type", "detail"])

    f_inv = flags[flags.kind == "invoice"]
    inv["status"] = np.select([inv.dup, inv.txn_id.isna() | inv.entry_id.isna(), inv.row_id.isin(f_inv.key)],
                              ["Duplicate", "Unmatched", "Discrepancy"], "Matched")
    inv["issues"] = inv.row_id.map(f_inv.groupby("key").error_type.agg(", ".join)).fillna("")
    inv["reason"] = inv.row_id.map(f_inv.groupby("key").detail.agg("; ".join)).fillna("")
    _anomaly_scores(inv)
    return {"inv": inv, "bank": bank, "ledger": led, "flags": flags,
            "orphans": bank[~bank.txn_id.isin(inv.txn_id.dropna())], "liability": liability(inv)}


def liability(inv):
    """Net GST = output tax on sales - input tax credit on purchases."""
    d = inv.assign(month=inv.date.dt.strftime("%Y-%m"))
    net = lambda x: x[x.type == "sales"].tax_amount.sum() - x[x.type == "purchase"].tax_amount.sum()
    rows = []
    for m, g in d.groupby("month"):
        c = g[g.status == "Matched"]
        rows.append({"month": m, "output_tax": c[c.type == "sales"].tax_amount.sum(),
                     "itc": c[c.type == "purchase"].tax_amount.sum(),
                     "net_clean": net(c), "net_as_filed": net(g)})
    risk = d[(d.type == "purchase") & (d.status != "Matched")].tax_amount.sum()
    return {"monthly": pd.DataFrame(rows), "itc_at_risk": risk}


def evaluate(truth, res):
    """Precision and recall for each planted error type."""
    pred = res["flags"][["key", "error_type"]]
    an = res["inv"].loc[res["inv"].anomaly, ["row_id"]].rename(columns={"row_id": "key"}).assign(error_type="anomalous_amount")
    pred = pd.concat([pred, an])
    rows = []
    for t in sorted(truth.error_type.unique()):
        T, S = set(truth[truth.error_type == t].key), set(pred[pred.error_type == t].key)
        tp = len(T & S)
        p, r = (tp / len(S) if S else 0), tp / len(T)
        rows.append({"error_type": t, "planted": len(T), "flagged": len(S), "correct": tp,
                     "precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0})
    return pd.DataFrame(rows)


def to_excel(res):
    """Reconciliation report as an Excel file (bytes)."""
    from io import BytesIO
    inv = res["inv"]
    flagged = res["flags"].merge(inv[["row_id", "invoice_id", "party", "date", "total"]],
                                 left_on="key", right_on="row_id", how="left").drop(columns="row_id")
    summary = inv.status.value_counts().rename_axis("Status").reset_index(name="Invoices")
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        summary.to_excel(w, sheet_name="Summary", index=False)
        flagged.to_excel(w, sheet_name="Flagged records", index=False)
        res["liability"]["monthly"].round(2).to_excel(w, sheet_name="Monthly GST", index=False)
        res["orphans"].to_excel(w, sheet_name="Payments with no invoice", index=False)
        for ws in w.book.worksheets:
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(60, max(len(str(c.value or "")) for c in col[:50]) + 2)
    return buf.getvalue()


if __name__ == "__main__":
    from generator import make_data
    d = make_data()
    pd.set_option("display.width", 200)
    for fz in (True, False):
        res = run_all(d["invoices"], d["bank"], d["ledger"], fuzzy=fz)
        print("fuzzy matching:", fz)
        print(evaluate(d["truth"], res).round(3).to_string(index=False))
    print(res["inv"].status.value_counts().to_dict() if False else "")
    r = run_all(d["invoices"], d["bank"], d["ledger"])
    print(r["inv"].status.value_counts().to_dict(), r["inv"].match.value_counts().to_dict())
    print(r["liability"]["monthly"].round(0).head(3), round(r["liability"]["itc_at_risk"]))

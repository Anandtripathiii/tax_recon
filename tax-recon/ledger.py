"""Read-only views over one reconciliation run.

Everything the dashboard tables, the exports, the record detail panel and Ask the Ledger show comes from here,
so the numbers always agree with each other. Every function takes the `res` dict that engine.run_all returns.
"""
import pandas as pd

from engine import LEDGER_LATE_DAYS, PAY_LATE_DAYS, SLABS

LABELS = {"amount_mismatch": "Amount mismatch", "duplicate": "Duplicate invoice", "wrong_gst": "Wrong GST",
          "missing_payment": "Missing payment", "missing_ledger": "Missing ledger entry",
          "date_shift": "Date shift", "orphan_payment": "Payment with no invoice",
          "anomalous_amount": "Unusual amount (ML)"}
CODES = {v: k for k, v in LABELS.items()}

# What a CA should do about each kind of flag (shown in the detail panel and used for the pre-filing checklist).
ACTIONS = {
    "wrong_gst": "Issue a credit or debit note for the tax difference and correct the GST rate before filing GSTR-1.",
    "amount_mismatch": "Confirm the right amount with the party, then correct the invoice, the ledger or the payment record.",
    "missing_payment": "Follow up for payment or check whether it was received in another account or under another reference.",
    "missing_ledger": "Book the invoice in the ledger so output tax or ITC is reported in the right period.",
    "date_shift": "Check the period: an entry booked late can move tax into the wrong return period.",
    "duplicate": "Cancel or reverse the duplicate copy so tax and ITC are not counted twice.",
    "orphan_payment": "Find the invoice this payment belongs to, or record it as an advance.",
}


def rs(x):
    """Rupee amount in Indian style: Lakh / Crore."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return ""
    if x != x:  # NaN
        return ""
    if x < 0:
        return "-" + rs(-x)
    if x >= 1e7:
        return f"₹{x / 1e7:.2f} Cr"
    if x >= 1e5:
        return f"₹{x / 1e5:.2f} L"
    return f"₹{x:,.0f}"


def rupees(x):
    """Exact rupee figure with Indian digit grouping (for reports, where L/Cr rounding is not acceptable)."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return ""
    neg, x = x < 0, abs(round(x))
    s = str(int(x))
    head, tail = s[:-3], s[-3:]
    while len(head) > 2:
        tail = head[-2:] + "," + tail
        head = head[:-2]
    out = (head + "," + tail) if head else tail
    return ("-₹" if neg else "₹") + out


def evidence(r, orphan_amt):
    """Expected value, found value and rupees at stake for one flag, so every row explains itself."""
    t = r.error_type
    if t == "wrong_gst":
        return f"Tax {rs(r.expected_tax)}", f"Tax {rs(r.tax_amount)}", abs(r.tax_amount - r.expected_tax)
    if t == "amount_mismatch":
        gaps = {"Bank": r.bank_amount, "Ledger": r.led_amount}
        src, val = max(gaps.items(), key=lambda kv: abs((kv[1] if pd.notna(kv[1]) else r.total) - r.total))
        return f"{rs(r.total)} in all three", f"{src} {rs(val)}", abs(val - r.total)
    if t == "missing_payment":
        return f"Payment of {rs(r.total)}", "No bank payment", r.total
    if t == "missing_ledger":
        return f"Ledger entry of {rs(r.total)}", "No ledger entry", r.total
    if t == "duplicate":
        return "One invoice", "A second copy", r.total
    if t == "date_shift":
        if pd.notna(r.bank_lag) and r.bank_lag > PAY_LATE_DAYS:
            return f"Paid within {PAY_LATE_DAYS} days", f"Paid after {r.bank_lag:.0f} days", float("nan")
        return f"Booked within {LEDGER_LATE_DAYS} days", f"Booked after {r.led_lag:.0f} days", float("nan")
    if t == "orphan_payment":
        amt = orphan_amt.get(r.key, float("nan"))
        return "A matching invoice", f"Payment of {rs(amt)}", amt
    return "", "", float("nan")


def flag_rows(res):
    """One row per flag with its evidence. Cached on the run."""
    if "_flag_rows" in res:
        return res["_flag_rows"]
    inv, flags = res["inv"], res["flags"]
    t = flags.assign(problem=flags.error_type.map(LABELS))
    t = t.merge(inv[["row_id", "invoice_id", "party", "gstin", "type", "date", "total", "tax_amount", "expected_tax",
                     "bank_amount", "led_amount", "bank_lag", "led_lag"]],
                left_on="key", right_on="row_id", how="left")
    bank = res["bank"].set_index("txn_id")
    orphan_amt = bank.amount
    cols = ["expected", "found", "stake"]
    ev = t.apply(lambda r: pd.Series(evidence(r, orphan_amt), index=cols), axis=1) if len(t) else pd.DataFrame(columns=cols)
    t = t.join(ev)
    t["detail"] = t.detail.str.replace("Rs ", "₹", regex=False)
    # Bank-only rows (payment with no invoice): use the payment's own date and amount.
    is_bank = t.kind == "bank"
    t.loc[is_bank, "date"] = t.loc[is_bank, "key"].map(bank.date)
    t.loc[is_bank, "total"] = t.loc[is_bank, "key"].map(bank.amount)
    t["invoice_id"] = t.invoice_id.fillna(t.key)
    t["party"] = t.party.fillna("Unknown (bank only)")
    t["date"] = pd.to_datetime(t["date"], errors="coerce")
    t["action"] = t.error_type.map(ACTIONS).fillna("")
    res["_flag_rows"] = t
    return t


def filter_flags(t, q="", kind="All", party="", min_amt=None, max_amt=None, sort="stake", order="desc"):
    """Filter and sort flag rows. `kind` is a label or code, `party` a case-insensitive substring,
    amounts compare against the invoice or payment total."""
    if kind and kind != "All":
        code = CODES.get(kind, kind)
        t = t[t.error_type == code]
    if party:
        t = t[t.party.str.contains(party, case=False, na=False, regex=False)]
    if min_amt is not None:
        t = t[t.total >= min_amt]
    if max_amt is not None:
        t = t[t.total <= max_amt]
    if q:
        hay = t[["party", "invoice_id", "detail", "key", "problem", "gstin"]].astype(str)
        t = t[hay.apply(lambda c: c.str.contains(q, case=False, na=False, regex=False)).any(axis=1)]
    key = {"stake": "stake", "amount": "total", "date": "date", "party": "party", "problem": "problem",
           "invoice": "invoice_id"}.get(sort, "stake")
    return t.sort_values([key, "invoice_id"], ascending=[order == "asc", True], na_position="last")


def flags_export(t):
    """Flag rows as a plain table for CSV / Excel: exact rupees, readable dates, the reason and the next step."""
    out = pd.DataFrame({
        "Problem": t.problem, "Invoice / payment": t.invoice_id, "Party": t.party, "GSTIN": t.gstin.fillna(""),
        "Type": t["type"].fillna("bank"), "Date": t.date.dt.strftime("%d-%m-%Y").fillna(""),
        "Amount (₹)": t.total.round(2), "Expected": t.expected, "Found": t.found,
        "₹ at stake": t.stake.round(2), "Why it was flagged": t.detail, "Suggested action": t.action,
    })
    return out


def unusual_rows(res):
    """Invoices with an anomaly score, a plain reason, and any rule flags on the same invoice."""
    inv = res["inv"]
    u = inv[["row_id", "invoice_id", "party", "gstin", "type", "date", "total", "party_z", "anomaly_score",
             "anomaly", "issues", "tax_ratio", "pay_lag", "is_round"]].copy()

    def why(r):
        parts = [f"{abs(r.party_z):.1f} std. dev. {'above' if r.party_z > 0 else 'below'} this party's usual amount"]
        if r.is_round:
            parts.append("taxable value is a round thousand")
        if pd.notna(r.pay_lag) and r.pay_lag > PAY_LATE_DAYS:
            parts.append(f"paid {r.pay_lag:.0f} days after the invoice")
        return "; ".join(parts)

    u["why"] = u.apply(why, axis=1)
    u["also"] = u.issues.apply(lambda v: ", ".join(LABELS.get(c.strip(), c.strip()) for c in v.split(",") if c.strip()))
    return u


def filter_unusual(u, q="", party="", min_amt=None, max_amt=None, only_marked=True, sort="score", order="desc"):
    if only_marked:
        u = u[u.anomaly]
    if party:
        u = u[u.party.str.contains(party, case=False, na=False, regex=False)]
    if min_amt is not None:
        u = u[u.total >= min_amt]
    if max_amt is not None:
        u = u[u.total <= max_amt]
    if q:
        hay = u[["party", "invoice_id", "why", "also", "gstin"]].astype(str)
        u = u[hay.apply(lambda c: c.str.contains(q, case=False, na=False, regex=False)).any(axis=1)]
    key = {"score": "anomaly_score", "amount": "total", "date": "date", "party": "party", "invoice": "invoice_id"}.get(sort, "anomaly_score")
    return u.sort_values([key, "invoice_id"], ascending=[order == "asc", True])


def unusual_export(u):
    return pd.DataFrame({
        "Invoice": u.invoice_id, "Party": u.party, "GSTIN": u.gstin, "Type": u["type"],
        "Date": u.date.dt.strftime("%d-%m-%Y"), "Amount (₹)": u.total.round(2),
        "Unusualness score": u.anomaly_score.round(3), "What looks unusual": u.why, "Also flagged for": u.also,
    })


def record_detail(res, key):
    """Invoice, bank payment and ledger entry for one record, side by side, with the fields that disagree marked.
    `key` may be a row id, an invoice id (e.g. INV-1201 or INV-2208-R) or a bank transaction id (e.g. T000106)."""
    inv, bank, led = res["inv"], res["bank"], res["ledger"]
    key = (key or "").strip()
    row = inv[(inv.row_id == key) | (inv.invoice_id.str.upper() == key.upper())]
    flags = flag_rows(res)
    if row.empty:
        b = bank[bank.txn_id.str.upper() == key.upper()]
        if b.empty:
            return None
        b = b.iloc[0]
        fl = flags[flags.key == b.txn_id]
        return {
            "id": b.txn_id, "kind": "bank", "title": f"Payment {b.txn_id}",
            "invoice": None,
            "bank": {"Transaction": b.txn_id, "Date": pd.to_datetime(b.date).strftime("%d %b %Y"),
                     "Amount": rs(b.amount), "Narration": b.narration, "Direction": b.direction},
            "ledger": None, "hl": {"invoice": ["missing"], "bank": [], "ledger": ["missing"]},
            "flags": [_flag_dict(r) for r in fl.itertuples()],
        }
    r = row.iloc[0]
    fl = flags[flags.key == r.row_id]
    types = set(fl.error_type)
    hl = {"invoice": [], "bank": [], "ledger": []}
    if "wrong_gst" in types:
        hl["invoice"] += ["GST rate", "Tax charged"]
    if "amount_mismatch" in types:
        if pd.notna(r.bank_amount) and abs(r.bank_amount - r.total) > 1:
            hl["bank"].append("Amount")
        if pd.notna(r.led_amount) and abs(r.led_amount - r.total) > 1:
            hl["ledger"].append("Amount")
    if "missing_payment" in types:
        hl["bank"].append("missing")
    if "missing_ledger" in types:
        hl["ledger"].append("missing")
    if "date_shift" in types:
        if pd.notna(r.bank_lag) and r.bank_lag > PAY_LATE_DAYS:
            hl["bank"].append("Date")
        else:
            hl["ledger"].append("Date")
    if "duplicate" in types:
        hl["invoice"].append("Invoice")

    invoice = {"Invoice": r.invoice_id, "Party": r.party, "GSTIN": r.gstin, "Type": str(r.type).title(),
               "Date": r.date.strftime("%d %b %Y"), "Taxable value": rs(r.taxable_value),
               "GST rate": f"{r.gst_rate}%" + ("" if r.gst_rate in SLABS else " (not a valid slab)"),
               "Tax charged": rs(r.tax_amount), "Tax at this rate": rs(r.expected_tax), "Total": rs(r.total)}
    bank_rec = None
    if pd.notna(r.txn_id):
        b = bank[bank.txn_id == r.txn_id].iloc[0]
        bank_rec = {"Transaction": b.txn_id, "Date": pd.to_datetime(b.date).strftime("%d %b %Y"),
                    "Amount": rs(b.amount), "Narration": b.narration,
                    "Matched by": "invoice number" if r.match == "exact" else "party, amount and date (fuzzy)"}
    led_rec = None
    if pd.notna(r.entry_id):
        l = led[led.entry_id == r.entry_id].iloc[0]
        led_rec = {"Entry": l.entry_id, "Date": pd.to_datetime(l.date).strftime("%d %b %Y"),
                   "Amount": rs(l.amount), "Party": l.party, "Tax booked": rs(l.tax_amount)}
    original = None
    if r.dup:
        cands = inv[(~inv.dup) & (inv.party == r.party) & ((inv.total - r.total).abs() <= 1) & (inv.date <= r.date)]
        if len(cands):
            o = cands.sort_values("date").iloc[-1]
            original = f"{o.invoice_id} on {o.date.strftime('%d %b %Y')}"
    return {"id": r.invoice_id, "kind": "invoice", "title": f"Invoice {r.invoice_id}", "invoice": invoice,
            "bank": bank_rec, "ledger": led_rec, "hl": hl, "original": original,
            "anomaly_score": round(float(r.anomaly_score), 3), "marked_unusual": bool(r.anomaly),
            "status": r.status, "flags": [_flag_dict(x) for x in fl.itertuples()]}


def _flag_dict(r):
    return {"problem": r.problem, "expected": r.expected, "found": r.found,
            "stake": rs(r.stake) if pd.notna(r.stake) else "", "why": r.detail, "action": r.action}


def tax_breakdown(res):
    """Totals a CA can drop into a report: output tax, ITC and net, by rate slab and by month, clean vs as filed."""
    inv = res["inv"]
    lia = res["liability"]
    ok = ~inv.dup
    clean = inv[inv.status == "Matched"]

    def side(df, kind):
        return df[df["type"] == kind]

    def totals(df):
        s, p = side(df, "sales"), side(df, "purchase")
        return {"taxable_sales": s.taxable_value.sum(), "output_tax": s.tax_amount.sum(),
                "taxable_purchases": p.taxable_value.sum(), "itc": p.tax_amount.sum(),
                "net": s.tax_amount.sum() - p.tax_amount.sum(), "invoices": len(df)}

    as_filed, clean_t = totals(inv), totals(clean)
    wrong = inv[ok & inv.issues.str.contains("wrong_gst")]
    gap = (wrong.tax_amount - wrong.expected_tax)
    slabs = []
    for rate, g in inv[ok].groupby("gst_rate"):
        s, p = side(g, "sales"), side(g, "purchase")
        slabs.append({"rate": f"{rate}%" + ("" if rate in SLABS else " (invalid)"), "sales_taxable": s.taxable_value.sum(),
                      "output_tax": s.tax_amount.sum(), "purchase_taxable": p.taxable_value.sum(),
                      "itc": p.tax_amount.sum(), "invoices": len(g)})
    m = lia["monthly"]
    months = [{"month": pd.to_datetime(x.month).strftime("%b %Y"), "output_tax": x.output_tax, "itc": x.itc,
               "net_clean": x.net_clean, "net_as_filed": x.net_as_filed} for x in m.itertuples()]
    period = f"{inv.date.min().strftime('%d %b %Y')} to {inv.date.max().strftime('%d %b %Y')}"
    return {"period": period, "as_filed": as_filed, "clean": clean_t, "itc_at_risk": lia["itc_at_risk"],
            "excess_tax_charged": gap[gap > 0].sum(), "short_tax_charged": -gap[gap < 0].sum(),
            "wrong_gst_invoices": len(wrong), "slabs": slabs, "months": months,
            "excluded": as_filed["invoices"] - clean_t["invoices"]}


def tax_report_text(b):
    """The tax breakdown as plain text for pasting into a report or email."""
    L = [f"GST summary, {b['period']} (synthetic demo data)", ""]
    for name, t in (("As filed (all invoices)", b["as_filed"]), ("Clean (fully matched invoices only)", b["clean"])):
        L += [name,
              f"  Taxable sales:        {rupees(t['taxable_sales'])}",
              f"  Output tax:           {rupees(t['output_tax'])}",
              f"  Taxable purchases:    {rupees(t['taxable_purchases'])}",
              f"  Input tax credit:     {rupees(t['itc'])}",
              f"  Net GST payable:      {rupees(t['net'])}" + ("  (negative = credit carried forward)" if t['net'] < 0 else ""),
              f"  Invoices:             {t['invoices']:,}", ""]
    L += ["Adjustments to review",
          f"  ITC at risk (purchases not fully matched): {rupees(b['itc_at_risk'])}",
          f"  Excess tax charged on wrong-GST invoices: {rupees(b['excess_tax_charged'])}",
          f"  Tax short-charged on wrong-GST invoices:  {rupees(b['short_tax_charged'])}",
          f"  Wrong-GST invoices: {b['wrong_gst_invoices']:,}; invoices excluded from the clean figures: {b['excluded']:,}", "",
          "By GST rate (as filed, duplicates excluded)"]
    for s in b["slabs"]:
        L.append(f"  {s['rate']:>16}  sales {rupees(s['sales_taxable'])}  output tax {rupees(s['output_tax'])}  "
                 f"purchases {rupees(s['purchase_taxable'])}  ITC {rupees(s['itc'])}")
    L += ["", "By month (net, clean vs as filed)"]
    for m in b["months"]:
        L.append(f"  {m['month']}: output {rupees(m['output_tax'])}, ITC {rupees(m['itc'])}, "
                 f"net clean {rupees(m['net_clean'])}, net as filed {rupees(m['net_as_filed'])}")
    return "\n".join(L)


def party_summary(res, sort="flags", limit=10):
    """Flags per party (vendor or customer) with rupees at stake."""
    t = flag_rows(res)
    t = t[t.party != "Unknown (bank only)"]
    g = t.groupby("party").agg(flags=("key", "size"), stake=("stake", "sum"),
                               types=("problem", lambda s: ", ".join(f"{k} ({v})" for k, v in s.value_counts().items())))
    g = g.sort_values("stake" if sort == "stake" else "flags", ascending=False).head(limit)
    return g.reset_index()

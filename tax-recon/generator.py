"""Makes fake invoices, bank transactions and ledger entries, then plants errors in them.

The planted errors are saved in a separate `truth` table. The engine never sees it;
we only use it at the end to measure how many errors the engine found.
"""
import string
import numpy as np
import pandas as pd

SLABS = [5, 12, 18, 28]
# share of each planted error type among the bad invoices
ERROR_MIX = {"amount_mismatch": .20, "duplicate": .15, "wrong_gst": .20,
             "missing_payment": .15, "missing_ledger": .10, "date_shift": .20}
TRADE = ["Traders", "Enterprises", "Industries", "Agencies", "Solutions", "Exports"]


_SURNAMES = ("Sharma Patel Verma Singh Kumar Gupta Mehta Shah Jain Agarwal Kapoor Malhotra "
              "Reddy Rao Nair Menon Iyer Khan Ahmed Das Bose Chatterjee Mukherjee Banerjee "
              "Desai Modi Thakur Chopra Bhat Pillai Joshi Mishra Pandey Tiwari Yadav Saxena "
              "Trivedi Dubey Chauhan Rathore Sinha Mittal Goyal Bansal Jindal Arora Bhatia").split()


def _vendors(rng, k=100):
    sur = rng.choice(_SURNAMES, k)
    tra = rng.choice(TRADE, k)
    names = pd.unique(pd.Series([f"{s} {t} Pvt Ltd" for s, t in zip(sur, tra)]))
    while len(names) < k:
        names = pd.unique(pd.concat([pd.Series(names),
            pd.Series([f"{rng.choice(_SURNAMES)} {rng.choice(TRADE)} Pvt Ltd" for _ in range(k)])]))
    names = names[:k]
    letters = np.array(list(string.ascii_uppercase))
    alnum = np.array(list(string.digits + string.ascii_uppercase))
    states = np.array(["07", "09", "27", "29", "33", "24", "19", "06"])
    s = rng.choice(states, k)
    L = rng.choice(letters, (k, 5))
    n4 = rng.integers(1000, 9999, k)
    c1 = rng.choice(letters, k)
    c2 = rng.choice(alnum, k)
    gstin = [f"{s[i]}{''.join(L[i])}{n4[i]}{c1[i]}1Z{c2[i]}" for i in range(k)]
    # half the parties are customers (sales), half are suppliers (purchase)
    return pd.DataFrame({"party": names, "gstin": gstin,
                         "type": np.where(np.arange(k) % 2 == 0, "sales", "purchase"),
                         "scale": rng.lognormal(10.2, 0.6, k)})


def _variant(name, rng):
    """A slightly different spelling of the same party, like a bank would write it."""
    options = [name.replace(" Pvt Ltd", ""),
               name.replace("Traders", "Trader").replace("Enterprises", "Enterprise").replace("Agencies", "Agency"),
               name.upper(), name.replace("Pvt Ltd", "P Ltd")]
    return options[rng.integers(len(options))]


def make_data(n=3000, error_rate=0.10, seed=42):
    rng = np.random.default_rng(seed)
    v = _vendors(rng)
    vi = rng.integers(0, len(v), n)
    inv = pd.DataFrame({
        "row_id": [f"R{i + 1:05d}" for i in range(n)],
        "invoice_id": [f"INV-{i + 1:04d}" for i in range(n)],
        "date": pd.Timestamp("2025-04-01") + pd.to_timedelta(rng.integers(0, 365, n), unit="D"),
        "party": v.party.values[vi], "gstin": v.gstin.values[vi], "type": v.type.values[vi]})
    inv["taxable_value"] = (v.scale.values[vi] * rng.lognormal(0, .35, n)).round(2)
    inv["gst_rate"] = rng.choice(SLABS, n, p=[.2, .25, .4, .15])

    perm = rng.permutation(n)
    k_an, k_err = max(1, int(n * .01)), int(n * error_rate)
    an, err = perm[:k_an], perm[k_an:k_an + k_err]
    kinds = rng.choice(list(ERROR_MIX), k_err, p=list(ERROR_MIX.values()))
    truth = []

    # unusually big (but otherwise valid) invoices: rules cannot catch these
    inv.loc[an, "taxable_value"] = (inv.loc[an, "taxable_value"] * 15).round(2)
    inv["tax_amount"] = (inv.taxable_value * inv.gst_rate / 100).round(2)
    truth += [(inv.at[i, "row_id"], "invoice", "anomalous_amount") for i in an]

    # wrong GST: either the tax does not match the rate, or the rate is not a real slab
    for i, kd in zip(err, kinds):
        if kd != "wrong_gst":
            continue
        if rng.random() < .5:
            other = [s for s in SLABS if s != inv.at[i, "gst_rate"]]
            inv.at[i, "tax_amount"] = round(inv.at[i, "taxable_value"] * int(rng.choice(other)) / 100, 2)
        else:
            inv.at[i, "gst_rate"] = int(rng.choice([15, 20]))
            inv.at[i, "tax_amount"] = round(inv.at[i, "taxable_value"] * inv.at[i, "gst_rate"] / 100, 2)
    inv["total"] = (inv.taxable_value + inv.tax_amount).round(2)

    # clean bank and ledger records, one each per invoice
    names = [_variant(p, rng) if rng.random() < .25 else p for p in inv.party]
    form = rng.integers(0, 3, n)
    no_id = rng.random(n) < .12
    narr = np.where(no_id, "NEFT/" + np.asarray(names),
          np.where(form == 0, "NEFT/" + np.asarray(names) + "/" + inv.invoice_id.values,
          np.where(form == 1, inv.invoice_id.values + " " + np.asarray(names),
                   "UPI-" + np.asarray(names) + "-" + pd.Series(inv.invoice_id.values).str.replace("-", "").values)))
    bank = pd.DataFrame({"txn_id": [f"T{i + 1:06d}" for i in range(n)],
                         "date": inv.date + pd.to_timedelta(rng.integers(1, 31, n), unit="D"),
                         "amount": inv.total, "narration": narr,
                         "direction": np.where(inv.type == "sales", "in", "out")})
    led = pd.DataFrame({"entry_id": [f"L{i + 1:06d}" for i in range(n)],
                        "date": inv.date + pd.to_timedelta(rng.integers(0, 4, n), unit="D"),
                        "invoice_ref": inv.invoice_id,
                        "party": [_variant(p, rng) if rng.random() < .08 else p for p in inv.party],
                        "amount": inv.total, "tax_amount": inv.tax_amount,
                        "side": np.where(inv.type == "sales", "Cr", "Dr")})

    drop_b, drop_l, dups = [], [], []
    for i, kd in zip(err, kinds):
        rid = inv.at[i, "row_id"]
        if kd == "amount_mismatch":
            f = 1 - rng.uniform(.005, .05)
            tbl, col = (bank, "amount") if rng.random() < .5 else (led, "amount")
            tbl.at[i, col] = round(tbl.at[i, col] * f, 2)
        elif kd == "missing_payment":
            drop_b.append(i)
        elif kd == "missing_ledger":
            drop_l.append(i)
        elif kd == "date_shift":
            if rng.random() < .5:
                bank.at[i, "date"] += pd.Timedelta(days=int(rng.integers(15, 61)))
            else:
                led.at[i, "date"] += pd.Timedelta(days=int(rng.integers(5, 41)))
        elif kd == "duplicate":
            dups.append(i)
            continue
        truth.append((rid, "invoice", kd))
    bank, led = bank.drop(drop_b), led.drop(drop_l)

    # duplicate invoices: an exact copy, or a copy with a slightly changed id and date
    extra = inv.loc[dups].copy()
    extra["row_id"] = [f"R{n + j + 1:05d}" for j in range(len(extra))]
    extra["date"] += pd.to_timedelta(rng.integers(0, 4, len(extra)), unit="D")
    ren = rng.random(len(extra)) < .4
    extra.loc[ren, "invoice_id"] = extra.loc[ren, "invoice_id"] + "-R"
    truth += [(r, "invoice", "duplicate") for r in extra.row_id]
    inv = pd.concat([inv, extra], ignore_index=True)

    # payments that belong to no invoice
    m = max(1, int(n * .01))
    unknown = [f"{rng.choice(_SURNAMES)} {rng.choice(TRADE)}" for _ in range(m)]
    orph = pd.DataFrame({"txn_id": [f"T{n + j + 1:06d}" for j in range(m)],
                         "date": pd.Timestamp("2025-04-01") + pd.to_timedelta(rng.integers(0, 365, m), unit="D"),
                         "amount": rng.lognormal(10.2, .8, m).round(2),
                         "narration": ["NEFT/" + u for u in unknown],
                         "direction": rng.choice(["in", "out"], m)})
    truth += [(t, "bank", "orphan_payment") for t in orph.txn_id]
    bank = pd.concat([bank, orph]).sort_values("date").reset_index(drop=True)
    return {"invoices": inv, "bank": bank, "ledger": led,
            "truth": pd.DataFrame(truth, columns=["key", "table", "error_type"])}


def save(data, folder="data"):
    import os
    os.makedirs(folder, exist_ok=True)
    for k, d in data.items():
        d.to_csv(f"{folder}/{k}.csv", index=False)


if __name__ == "__main__":
    d = make_data()
    save(d)
    print({k: len(v) for k, v in d.items()})
    print(d["truth"].error_type.value_counts())

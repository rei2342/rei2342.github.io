"""収益台帳。ASP 管理画面へのログイン・スクレイピングはしない（BAN 回避・規約順守）。
各 ASP / Amazon / note の管理画面からダウンロードした CSV を取り込むか、手入力する。"""
from __future__ import annotations

import hashlib
import io
import re
from datetime import date

import pandas as pd

from core import config as C

LEDGER = C.DATA_DIR / "revenue" / "ledger.csv"
COLUMNS = ["date", "account_key", "source", "program", "amount_jpy", "status", "memo", "row_hash"]
SOURCES = ["A8.net", "もしもアフィリエイト", "Amazonアソシエイト", "楽天", "afb", "note売上", "物販", "その他"]

DATE_KEYS = ["成果発生日", "発生日時", "発生日", "注文日", "日付", "date", "購入日", "Date"]
AMOUNT_KEYS = ["成果報酬額", "成果報酬", "報酬額", "報酬", "紹介料", "売上金額", "売上", "収益", "amount", "金額", "Earnings"]
STATUS_KEYS = ["ステータス", "状態", "成果状況", "status"]
PROGRAM_KEYS = ["プログラム名", "広告名", "プロモーション名", "商品名", "記事タイトル", "program", "Name"]


def load() -> pd.DataFrame:
    if not LEDGER.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(LEDGER, dtype={"account_key": str, "row_hash": str})
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["amount_jpy"] = pd.to_numeric(df["amount_jpy"], errors="coerce").fillna(0)
    return df


def _save(df: pd.DataFrame) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    df[COLUMNS].to_csv(LEDGER, index=False)


def _pick(cols, keys):
    for k in keys:
        for c in cols:
            if k.lower() in str(c).lower():
                return c
    return None


def _read_any(raw: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "cp932", "utf-16"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc)
        except Exception:
            continue
    raise ValueError("CSV を読めない（文字コード不明）")


def import_csv(raw: bytes, account_key: str, source: str) -> tuple[int, dict]:
    src = _read_any(raw)
    dc, ac = _pick(src.columns, DATE_KEYS), _pick(src.columns, AMOUNT_KEYS)
    sc, pc = _pick(src.columns, STATUS_KEYS), _pick(src.columns, PROGRAM_KEYS)
    if not dc or not ac:
        raise ValueError(f"日付列/金額列を特定できない。列: {list(src.columns)}")
    rows = []
    for _, r in src.iterrows():
        amt = float(re.sub(r"[^\d.\-]", "", str(r[ac])) or 0)
        d = pd.to_datetime(r[dc], errors="coerce")
        if pd.isna(d):
            continue
        rec = {"date": d.date(), "account_key": account_key, "source": source,
               "program": str(r[pc]) if pc else "", "amount_jpy": amt,
               "status": str(r[sc]) if sc else "", "memo": "csv"}
        rec["row_hash"] = hashlib.md5("|".join(str(rec[k]) for k in ("date", "account_key", "source", "program", "amount_jpy", "status"))
                                      .encode() + str(_).encode()).hexdigest()
        rows.append(rec)
    cur = load()
    new = pd.DataFrame(rows, columns=COLUMNS)
    new = new[~new["row_hash"].isin(set(cur["row_hash"].astype(str)))]
    _save(pd.concat([cur, new], ignore_index=True))
    return len(new), {"date": dc, "amount": ac, "status": sc, "program": pc}


def add_manual(d: date, account_key: str, source: str, amount: float, program: str = "", status: str = "確定", memo: str = "") -> None:
    cur = load()
    rec = {"date": d, "account_key": account_key, "source": source, "program": program, "amount_jpy": amount,
           "status": status, "memo": memo or "manual"}
    rec["row_hash"] = hashlib.md5((str(rec) + C.now_iso()).encode()).hexdigest()
    _save(pd.concat([cur, pd.DataFrame([rec])], ignore_index=True))


def summary(df: pd.DataFrame | None = None, day: date | None = None) -> dict:
    df = load() if df is None else df
    day = day or date.today()
    if df.empty:
        return {"today": 0, "month": 0, "by_source_today": {}, "by_account_month": {}}
    t = df[df["date"] == day]
    m = df[pd.to_datetime(df["date"]).dt.strftime("%Y-%m") == day.strftime("%Y-%m")]
    rejected = df["status"].astype(str).str.contains("否認|キャンセル|取消", na=False)
    return {
        "today": float(t[~rejected.loc[t.index]]["amount_jpy"].sum()),
        "month": float(m[~rejected.loc[m.index]]["amount_jpy"].sum()),
        "by_source_today": t.groupby("source")["amount_jpy"].sum().to_dict(),
        "by_account_month": m.groupby("account_key")["amount_jpy"].sum().to_dict(),
    }

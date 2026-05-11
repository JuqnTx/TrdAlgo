"""Convierte el parquet de OHLCV a un JS consumible por el calendario.

Genera calendar/data.js con un objeto window.MARKET_DATA indexado por fecha:
    "YYYY-MM-DD": {o, h, l, c, v, ret}
donde `ret` = retorno % close-to-close (decimal, ej. 0.0123 = +1.23%)

Uso:
    python data/export_json.py                # NQ=F por defecto
    python data/export_json.py --ticker NQ=F
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"
OUT_PATH = ROOT / "calendar" / "data.js"
HTML_PATH = ROOT / "calendar" / "index.html"

PLACEHOLDER_RE = re.compile(
    r"(/\* MARKET_DATA_PLACEHOLDER \*/)(.*?)(/\* END_MARKET_DATA_PLACEHOLDER \*/)",
    re.DOTALL,
)


def cache_path(ticker: str) -> Path:
    safe = "".join(c for c in ticker.lower() if c.isalnum())
    return CACHE_DIR / f"{safe}.parquet"


def build_payload(df: pd.DataFrame, ticker: str) -> dict:
    df = df.sort_index().copy()
    df["ret"] = df["Close"].pct_change()

    by_date = {}
    for ts, row in df.iterrows():
        key = ts.strftime("%Y-%m-%d")
        by_date[key] = {
            "o": round(float(row["Open"]), 2),
            "h": round(float(row["High"]), 2),
            "l": round(float(row["Low"]), 2),
            "c": round(float(row["Close"]), 2),
            "v": int(row["Volume"]) if not pd.isna(row["Volume"]) else 0,
            "ret": None if pd.isna(row["ret"]) else round(float(row["ret"]), 6),
        }

    return {
        "ticker": ticker,
        "start": df.index.min().strftime("%Y-%m-%d"),
        "end": df.index.max().strftime("%Y-%m-%d"),
        "rows": len(df),
        "data": by_date,
    }


def write_js(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    js = (
        "// Auto-generado por data/export_json.py — no editar a mano.\n"
        f"window.MARKET_DATA = {json.dumps(payload, separators=(',', ':'))};\n"
    )
    path.write_text(js, encoding="utf-8")


def inject_into_html(payload: dict, html_path: Path) -> None:
    if not html_path.exists():
        print(f"[warn] {html_path} no existe; salto inyección inline.")
        return
    html = html_path.read_text(encoding="utf-8")
    new_block = (
        "/* MARKET_DATA_PLACEHOLDER */\n"
        + json.dumps(payload, separators=(",", ":"))
        + "\n/* END_MARKET_DATA_PLACEHOLDER */"
    )
    if not PLACEHOLDER_RE.search(html):
        print(f"[warn] no encontré los marcadores en {html_path}; salto inyección.")
        return
    new_html = PLACEHOLDER_RE.sub(lambda _m: new_block, html)
    html_path.write_text(new_html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="NQ=F")
    args = parser.parse_args()

    src = cache_path(args.ticker)
    if not src.exists():
        raise SystemExit(f"No existe cache para {args.ticker}: {src}\nCorre primero: python data/fetch.py --ticker {args.ticker}")

    df = pd.read_parquet(src)
    payload = build_payload(df, args.ticker)
    write_js(payload, OUT_PATH)
    inject_into_html(payload, HTML_PATH)

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"[export] {args.ticker}: {payload['rows']} días → {OUT_PATH} ({size_kb:.1f} KB)")
    print(f"[export] inyectado inline en {HTML_PATH}")
    print(f"[export] rango: {payload['start']} → {payload['end']}")


if __name__ == "__main__":
    main()

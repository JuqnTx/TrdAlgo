"""Descarga histórico OHLC diario de un futuro/índice y lo cachea en parquet.

Uso:
    python data/fetch.py                            # NQ=F desde 2021-01-01 hasta hoy
    python data/fetch.py --ticker MNQ=F
    python data/fetch.py --start 2020-01-01
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

CACHE_DIR = Path(__file__).parent / "cache"
DEFAULT_START = date(2021, 1, 1)


def cache_path(ticker: str) -> Path:
    safe = "".join(c for c in ticker.lower() if c.isalnum())
    return CACHE_DIR / f"{safe}.parquet"


def fetch(ticker: str, start: date, end: date) -> pd.DataFrame:
    df = yf.download(
        ticker,
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=False,
        progress=False,
    )
    if df.empty:
        raise RuntimeError(f"yfinance devolvió 0 filas para {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.index.name = "date"
    return df[["Open", "High", "Low", "Close", "Volume"]]


def load_or_update(ticker: str, start: date) -> pd.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(ticker)
    today = date.today()

    if path.exists():
        cached = pd.read_parquet(path)
        cached_start = cached.index.min().date()
        cached_end = cached.index.max().date()

        if cached_start <= start:
            if cached_end >= today - timedelta(days=1):
                print(f"[cache] {ticker}: {len(cached)} filas, {cached_start} → {cached_end} (al día)")
                return cached
            print(f"[cache] {ticker}: actualizando incrementalmente desde {cached_end + timedelta(days=1)}")
            new = fetch(ticker, cached_end + timedelta(days=1), today)
            merged = pd.concat([cached, new])
            merged = merged[~merged.index.duplicated(keep="last")].sort_index()
            merged.to_parquet(path)
            print(f"[cache] {ticker}: {len(merged)} filas tras merge")
            return merged

        print(f"[cache] {ticker}: rango pedido empieza antes ({start}) que el cache ({cached_start}); re-descarga limpia")

    print(f"[fetch] {ticker}: descarga desde {start} hasta {today}")
    df = fetch(ticker, start, today)
    df.to_parquet(path)
    print(f"[fetch] {ticker}: {len(df)} filas guardadas en {path}")
    return df


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", default="NQ=F", help="Ticker yfinance (def: NQ=F continuo)")
    parser.add_argument(
        "--start",
        type=parse_date,
        default=DEFAULT_START,
        help=f"Fecha de inicio YYYY-MM-DD (def: {DEFAULT_START.isoformat()})",
    )
    parser.add_argument("--no-export", action="store_true", help="No regenerar calendar/data.js")
    args = parser.parse_args()

    df = load_or_update(args.ticker, args.start)
    print(f"\nResumen {args.ticker}:")
    print(f"  rango:  {df.index.min().date()} → {df.index.max().date()}")
    print(f"  filas:  {len(df)}")
    print(f"  último close: {df['Close'].iloc[-1]:.2f}")

    if not args.no_export:
        from export_json import build_payload, write_js, inject_into_html, OUT_PATH, HTML_PATH
        payload = build_payload(df, args.ticker)
        write_js(payload, OUT_PATH)
        inject_into_html(payload, HTML_PATH)
        size_kb = OUT_PATH.stat().st_size / 1024
        print(f"\n[export] regenerado {OUT_PATH} ({size_kb:.1f} KB) e inyectado en {HTML_PATH}")


if __name__ == "__main__":
    main()

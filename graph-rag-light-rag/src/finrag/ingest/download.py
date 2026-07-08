"""EDGAR -> data/raw/{ticker}_{section}.txt

Pulls the latest 10-K for each configured ticker and writes Items 1 (Business),
1A (Risk Factors), and 7 (MD&A) as plain text. edgartools already does the
HTML-to-text conversion, so there's nothing to clean up here.

Idempotent: a section already on disk is skipped, so re-running after a crash or a
network hiccup only fetches what's missing.
"""

import edgar

from finrag.config import settings

# TenK attribute -> the section tag used in filenames and chunk ids.
SECTIONS = {
    "business": "item1",
    "risk_factors": "item1a",
    "management_discussion": "item7",
}


def download_ticker(ticker: str) -> None:
    """Fetch the latest 10-K for one ticker and write any missing section files."""
    out_dir = settings.data_dir / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)

    missing = [
        section
        for section in SECTIONS.values()
        if not (out_dir / f"{ticker}_{section}.txt").exists()
    ]
    if not missing:
        print(f"{ticker}: all sections already on disk, skipping")
        return

    company = edgar.Company(ticker)
    filings = company.get_filings(form="10-K")
    latest = filings.latest()
    if latest is None:
        print(f"WARNING: {ticker}: no 10-K filings found, skipping")
        return
    ten_k = latest.obj()

    for attr, section in SECTIONS.items():
        out_path = out_dir / f"{ticker}_{section}.txt"
        if out_path.exists():
            continue
        text = getattr(ten_k, attr, None)
        if not text:
            print(f"WARNING: {ticker}: section {attr} ({section}) missing, skipping")
            continue
        out_path.write_text(text, encoding="utf-8")
        print(f"{ticker}: wrote {out_path} ({len(text)} chars)")


def download_all(tickers: list[str] | None = None) -> None:
    """Download the latest 10-K sections for every ticker in `tickers` (or config)."""
    edgar.set_identity(settings.edgar_identity)
    for ticker in tickers or settings.tickers:
        download_ticker(ticker)

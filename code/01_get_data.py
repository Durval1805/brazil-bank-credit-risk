"""
01_get_data.py - download raw IFData reports from the Banco Central do Brasil (BCB).

Source : BCB IFData OData API
         https://olinda.bcb.gov.br/olinda/servico/IFDATA/versao/v1/aplicacao
Licence: Open Data Commons Open Database License (ODbL), per dadosabertos.bcb.gov.br

Usage (run from the repository root):
    python code/01_get_data.py list              # step 1: save the report catalogue
    python code/01_get_data.py check <report>    # step 2: compare the institution-type codes
    python code/01_get_data.py download          # step 3: download all quarters for REPORTS below

Attribution: initial version drafted with Claude (Anthropic); reviewed and adapted by me.
"""

# --- Tools (imports) ----------------------------------------------------------------------
# Tools that come with Python
import sys  # reads the word typed after the command (list, check or download)
import time  # makes the script pause between requests, not to overload the BCB's server
from pathlib import Path  # handles folder and file locations

# Tools I installed in my .venv
import pandas as pd  # table tool, nickname pd
import requests  # tool that downloads things from the internet

# --- Settings -----------------------------------------------------------------------------
BASE = "https://olinda.bcb.gov.br/olinda/servico/IFDATA/versao/v1/odata"  # BCB's API address

# Where the downloaded files get saved: from this file (code/), go one folder up, then data/raw.
# Built this way so it works on any computer (my Mac, Nuvolos, the teacher's).
RAW = Path(__file__).resolve().parents[1] / "data" / "raw"

# Which type of institution to download. The API codes are:
# 1 = Prudential Conglomerates and Independent Institutions
# 2 = Financial Conglomerates and Independent Institutions  <- my choice (same as on the IFData website)
# 3 = Individual Institutions
INST_TYPE = 2

# Reports to download, as {"my_name": "report_number"} (numbers from the API's report list):
# 1 = Resumo (Summary), 2 = Ativo (Assets),
# 8 = Carteira de credito ativa - por nivel de risco (Loans by risk level AA-H).
# Not downloaded: 5 = Informacoes de Capital. For institution type 2 it only exists until 2014Q4,
# so my capital ratio is equity / total assets, built from the Summary report.
REPORTS = {
    "risk_level": "8",  # my Y, current risky share, loan growth
    "summary": "1",  # total assets, equity, net income, funding -> capital ratio
    "assets": "2",  # cash, interbank assets, securities -> liquidity
}

# List of quarters in the API's format (201206 = June 2012 ... 202412 = December 2024).
# Every year 2012-2024, months 3/6/9/12, skipping March 2012 (loan data starts June 2012): 51 quarters.
QUARTERS = [f"{y}{m:02d}" for y in range(2012, 2025) for m in (3, 6, 9, 12)
            if not (y == 2012 and m == 3)]


# --- Helper functions -----------------------------------------------------------------------
def fetch_table(url, retries=3, pause=5):
    """Go to an internet address and bring back a table (the API answers in JSON format).

    Internet connections sometimes fail for a moment, so it tries up to 3 times,
    waiting longer after each failure (5, then 10, then 15 seconds).
    After 3 failures it gives up with a clear message.
    """
    for attempt in range(1, retries + 1):  # attempt = 1, 2, 3
        try:
            r = requests.get(url, timeout=200)  # ask the BCB's server for the data; wait at most 200 s
            r.raise_for_status()  # check whether the server said "error"; if so, jump to except
            rows = r.json().get("value", [])  # the API puts the rows in a list called "value"
            return pd.DataFrame(rows)  # turn the rows into a pandas table (empty if no rows)
        except Exception as e:  # network errors, HTTP errors, empty/odd answers
            print(f"  attempt {attempt} failed: {e}")
            time.sleep(pause * attempt)  # wait 5, 10, then 15 seconds before trying again
    raise RuntimeError(f"Could not fetch {url}")  # all 3 attempts failed: stop with a clear message


def values_url(quarter, inst_type, report):
    """Build the address to ask the API for one report, one quarter, one institution type.

    The API needs a long, precise address. This function assembles it from those three
    pieces, so we never type it by hand. $format=json asks for the answer in JSON,
    the API's standard format, which pandas turns into a table.
    """
    # The words inside the address (IfDataValores, AnoMes = year-month, TipoInstituicao =
    # institution type, Relatorio = report) are the API's own Portuguese names: they must stay as is.
    return (f"{BASE}/IfDataValores(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,"
            f"Relatorio=@Relatorio)?@AnoMes={quarter}&@TipoInstituicao={inst_type}"
            f"&@Relatorio='{report}'&$format=json")


# --- Commands ---------------------------------------------------------------------------------
def cmd_list():
    """Step 1: save the catalogue of reports and preview the institution register."""
    RAW.mkdir(parents=True, exist_ok=True)  # make sure the data/raw folder exists
    # ListaDeRelatorio is a "function" of the API, so it needs () after its name
    reports = fetch_table(f"{BASE}/ListaDeRelatorio()?$format=json")  # download the catalogue
    reports.to_csv(RAW / "report_list.csv", index=False)  # save the catalogue as a CSV file
    print(f"Saved {len(reports)} rows to {RAW / 'report_list.csv'}\n")
    print(reports.drop_duplicates().head(60).to_string())  # print only the first 60 rows

    # Download the register of institutions (names, codes, types) for December 2024
    # and print only its size and column names, to see what it contains.
    register = fetch_table(f"{BASE}/IfDataCadastro(AnoMes=@AnoMes)?@AnoMes=202412&$format=json")
    print(f"\nInstitution register 2024-12: {len(register):,} rows, columns {list(register.columns)}")
    print("\nCheck that numbers 1, 2, 5 and 8 match the names in REPORTS at the top of this file, "
          "then run\n    python code/01_get_data.py download")


def cmd_check(report):
    """Step 2: find which institution-type code (1-4) matches my sample.

    Downloads one report for December 2024 four times, once with each code,
    and prints how many rows came back and the first 5 rows.
    """
    for inst_type in (1, 2, 3, 4):  # try each possible code
        df = fetch_table(values_url("202412", inst_type, report))
        print(f"\nInstitution type {inst_type}: {len(df):,} rows")
        if not df.empty:
            print(df.head(5).to_string())  # show the first 5 rows to recognise the institutions


def cmd_download():
    """Step 3: download every quarter of each report in REPORTS, plus the institution register."""
    if not REPORTS:  # safety check: stop if REPORTS is still empty
        sys.exit("Fill in REPORTS (and check INST_TYPE) at the top of this file first.")
    RAW.mkdir(parents=True, exist_ok=True)  # make sure the data/raw folder exists

    for name, report in REPORTS.items():  # for each report I listed in REPORTS
        out = RAW / f"ifdata_{name}_type{INST_TYPE}.csv.gz"  # name of the file to save
        if out.exists():  # already downloaded: skip it (so the script can be safely re-run)
            print(f"{out.name} already exists - skipping")
            continue
        frames = []  # list that will hold one table per quarter
        for quarter in QUARTERS:  # go through all 51 quarters
            print(f"{name} (report {report}) {quarter} ...", end=" ")
            df = fetch_table(values_url(quarter, INST_TYPE, report))  # download this report for this quarter
            print(f"{len(df):,} rows")
            if not df.empty:
                df["quarter"] = quarter  # label every row with its quarter
                frames.append(df)  # keep it in the list
            time.sleep(1)  # wait 1 second between requests, to be polite to the API
        # Stick the 51 quarters together into one table and save it compressed (.csv.gz),
        # so the file stays small enough for GitHub.
        pd.concat(frames, ignore_index=True).to_csv(out, index=False, compression="gzip")
        print(f"Saved {out}\n")

    # Institution register (names, conglomerate links) for every quarter.
    # Needed to follow banks over time: names, mergers, which group a bank belongs to.
    out = RAW / "ifdata_register.csv.gz"
    if not out.exists():
        frames = []
        for quarter in QUARTERS:
            df = fetch_table(f"{BASE}/IfDataCadastro(AnoMes=@AnoMes)?@AnoMes={quarter}&$format=json")
            df["quarter"] = quarter  # label every row with its quarter
            frames.append(df)
            time.sleep(1)  # be polite to the API
        pd.concat(frames, ignore_index=True).to_csv(out, index=False, compression="gzip")
        print(f"Saved {out}")


# --- Start button (must stay at the very bottom) -----------------------------------------------
if __name__ == "__main__":  # only run this when the file is run directly
    mode = sys.argv[1] if len(sys.argv) > 1 else "list"  # the word typed after the file name
    if mode == "check":  # check needs a report number after it
        if len(sys.argv) < 3:
            sys.exit("Usage: python code/01_get_data.py check <report_number>")
        cmd_check(sys.argv[2])
    elif mode == "download":
        cmd_download()
    else:  # anything else (or nothing) runs list
        cmd_list()
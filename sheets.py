import json
import os
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = ["Date", "Marchand", "Catégorie", "HT", "TVA %", "TVA €", "TTC", "Devise", "Ajouté le", "Remarques"]

_NC_COLS = {3: "D", 4: "E", 5: "F", 6: "G"}  # 0-based indices → column letters for HT, TVA%, TVA€, TTC
_RED = {"textFormat": {"foregroundColor": {"red": 1.0, "green": 0.0, "blue": 0.0}}}


def _get_sheet() -> gspread.Worksheet:
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(
            os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"),
            scopes=SCOPES,
        )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(os.getenv("GOOGLE_SHEET_ID"))
    return spreadsheet.sheet1


def ensure_headers() -> None:
    sheet = _get_sheet()
    first_row = sheet.row_values(1)
    if first_row != HEADERS:
        sheet.insert_row(HEADERS, index=1)


def append_expense(expense: dict) -> None:
    sheet = _get_sheet()
    today = datetime.now().strftime("%d/%m/%Y")

    def _val(key):
        v = expense.get(key)
        return "NC" if v is None else v

    row = [
        expense.get("date", ""),
        expense.get("marchand", ""),
        expense.get("categorie", "Autre"),
        _val("ht"),
        _val("tva_pct"),
        _val("tva_eur"),
        _val("ttc"),
        expense.get("devise", "EUR"),
        today,
        expense.get("remarques", ""),
    ]
    sheet.append_row(row, value_input_option="USER_ENTERED")

    nc_ranges = [
        {"range": f"{col}{len(sheet.get_all_values())}", "format": _RED}
        for idx, col in _NC_COLS.items()
        if row[idx] == "NC"
    ]
    if nc_ranges:
        sheet.batch_format(nc_ranges)

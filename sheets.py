import json
import os
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = ["Date", "Marchand", "Catégorie", "HT", "TVA %", "TVA €", "TTC", "Devise", "Ajouté le"]


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
    row = [
        expense.get("date", ""),
        expense.get("marchand", ""),
        expense.get("categorie", "Autre"),
        expense.get("ht", ""),
        expense.get("tva_pct", ""),
        expense.get("tva_eur", ""),
        expense.get("ttc", ""),
        expense.get("devise", "EUR"),
        today,
    ]
    sheet.append_row(row, value_input_option="USER_ENTERED")

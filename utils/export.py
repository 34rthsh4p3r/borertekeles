from datetime import datetime
from io import BytesIO

import pandas as pd
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from utils.constants import BUDAPEST


COLUMNS = (
    "Timestamp (HH-MM-SS)", "Dátum", "ID", "Tétel", "Bortípus", "Aromacsoportok",
    "Borkészítés", "Illatosság", "Fajtacsoport", "Szőlőfajta", "Borvidék", "Egyensúly",
    "Pontszám", "Diagram aktív",
)
WIDTHS = (25, 14, 40, 10, 14, 55, 15, 17, 21, 24, 34, 21, 12, 17)


def records_frame(records: list[dict]) -> pd.DataFrame:
    rows = []
    for record in records:
        local = record["created_at"].astimezone(BUDAPEST)
        rows.append((
            local.strftime("%H-%M-%S"), local.date(), str(record["id"]), record["lot"],
            record["wine_type"], ", ".join(record["aromas"]), record["technique"],
            record["fragrance"], record["variety_group"], record["grape"], record["region"],
            record["balance"], record["score"], record["chart_active"],
        ))
    return pd.DataFrame(rows, columns=COLUMNS)


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False, sep=";", lineterminator="\r\n").encode("utf-8-sig")


def legacy_votes_frame(records: list[dict]) -> pd.DataFrame:
    columns = ("participant", "wine", "section", "question", "option", "created_at", "archived_at")
    frame = pd.DataFrame(records, columns=columns)
    primary = frame["section"].isin(("elsodleges", "illat", "iz")) & frame["question"].eq("elsodleges_aromak")
    frame.loc[primary, "section"] = "elsodleges"
    repeated = frame.duplicated(subset=["participant", "wine", "section", "question", "option", "archived_at"])
    return frame.loc[~(primary & repeated)]


def excel_bytes(frame: pd.DataFrame) -> bytes:
    workbook = Workbook(write_only=True)
    fill = PatternFill("solid", fgColor="762C47")
    font = Font(bold=True, color="FFFFFF")
    sheet_capacity = 1_048_575  # A fejléc is elfoglal egy sort.
    for start in range(0, max(1, len(frame)), sheet_capacity):
        batch = frame.iloc[start:start + sheet_capacity]
        number = start // sheet_capacity + 1
        sheet = workbook.create_sheet("Értékelések" if number == 1 else f"Értékelések {number}")
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:N{len(batch) + 1}"
        header = []
        for column, (name, width) in enumerate(zip(COLUMNS, WIDTHS), start=1):
            sheet.column_dimensions[get_column_letter(column)].width = width
            cell = WriteOnlyCell(sheet, value=name)
            cell.fill = fill
            cell.font = font
            header.append(cell)
        sheet.append(header)
        for row in batch.itertuples(index=False, name=None):
            date_cell = WriteOnlyCell(sheet, value=row[1])
            date_cell.number_format = "yyyy-mm-dd"
            sheet.append((row[0], date_cell, *row[2:]))
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def export_filename(lot: int | None, extension: str, created_at: datetime) -> str:
    scope = "osszes" if lot is None else f"tetel-{lot}"
    timestamp = created_at.astimezone(BUDAPEST).strftime("%Y-%m-%d_%H-%M-%S")
    return f"geoterroir_{scope}_{timestamp}.{extension}"

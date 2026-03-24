"""
Google Sheets MCP Server for Claude Code.

既存の gspread OAuth 認証を使って Google Sheets を読み書きする MCP サーバー。
"""

import os
from pathlib import Path
from functools import lru_cache
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("google-sheets")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    """Walk up from this file to find the repo root (contains .git)."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    # fallback: assume packages/mcp-google-sheets/ structure
    return Path(__file__).resolve().parent.parent.parent


@lru_cache(maxsize=1)
def _get_client():
    """Lazy-init gspread client, cached for process lifetime."""
    import gspread

    root = _find_repo_root()
    creds = os.environ.get(
        "GSHEETS_OAUTH_CREDENTIALS", str(root / "oauth_credentials.json")
    )
    token = os.environ.get(
        "GSHEETS_AUTHORIZED_USER", str(root / "token.json")
    )
    return gspread.oauth(
        credentials_filename=creds, authorized_user_filename=token
    )


def _get_worksheet(spreadsheet_id: str, worksheet: str = "", worksheet_index: int = 0):
    """Open a spreadsheet and return a worksheet by name or index."""
    gc = _get_client()
    sh = gc.open_by_key(spreadsheet_id)
    if worksheet:
        return sh.worksheet(worksheet)
    return sh.get_worksheet(worksheet_index)


def _rows_to_tsv(rows: list[list]) -> str:
    """Convert 2D list to tab-separated string."""
    return "\n".join("\t".join(str(c) for c in row) for row in rows)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

MAX_READ_ROWS = 500


@mcp.tool()
def list_worksheets(spreadsheet_id: str) -> str:
    """List all worksheets in a Google Spreadsheet.
    Returns worksheet names, row counts, and column counts.
    """
    try:
        gc = _get_client()
        sh = gc.open_by_key(spreadsheet_id)
        lines = [f"Spreadsheet: {sh.title}"]
        for i, ws in enumerate(sh.worksheets()):
            lines.append(f"  {i}: {ws.title} ({ws.row_count} rows × {ws.col_count} cols)")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def read_sheet(
    spreadsheet_id: str,
    worksheet: str = "",
    worksheet_index: int = 0,
) -> str:
    """Read all data from a worksheet. Specify either worksheet name or index (0-based).
    If neither is provided, reads the first sheet.
    Large sheets are truncated to 500 rows.
    """
    try:
        ws = _get_worksheet(spreadsheet_id, worksheet, worksheet_index)
        rows = ws.get_all_values()
        truncated = len(rows) > MAX_READ_ROWS
        if truncated:
            rows = rows[:MAX_READ_ROWS]
        header = f"Sheet: {ws.title} ({len(rows)}{'+' if truncated else ''} rows)\n"
        if truncated:
            header += f"⚠ Truncated to {MAX_READ_ROWS} rows. Use read_range for specific ranges.\n"
        return header + _rows_to_tsv(rows)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def read_range(
    spreadsheet_id: str,
    worksheet: str,
    range_notation: str,
) -> str:
    """Read a specific cell range from a worksheet.
    range_notation: A1 notation like 'A1:D10', 'B:B', '1:5'.
    """
    try:
        ws = _get_worksheet(spreadsheet_id, worksheet)
        rows = ws.get(range_notation)
        return f"Range: {worksheet}!{range_notation}\n" + _rows_to_tsv(rows)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def write_cells(
    spreadsheet_id: str,
    worksheet: str,
    range_notation: str,
    values: list[list[str]],
) -> str:
    """Write data to a specific range.
    values is a 2D array of strings.
    Example: range_notation='A1', values=[['Name','Age'],['Alice','30']]
    """
    try:
        ws = _get_worksheet(spreadsheet_id, worksheet)
        ws.update(range_name=range_notation, values=values, value_input_option="USER_ENTERED")
        rows = len(values)
        cols = max(len(r) for r in values) if values else 0
        return f"Written {rows} rows × {cols} cols to {worksheet}!{range_notation}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def append_rows(
    spreadsheet_id: str,
    worksheet: str,
    rows: list[list[str]],
) -> str:
    """Append rows to the end of existing data in a worksheet.
    rows is a 2D array of strings.
    """
    try:
        ws = _get_worksheet(spreadsheet_id, worksheet)
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        return f"Appended {len(rows)} rows to {worksheet}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def create_worksheet(
    spreadsheet_id: str,
    title: str,
    rows: int = 1000,
    cols: int = 26,
) -> str:
    """Create a new worksheet tab in an existing spreadsheet."""
    try:
        gc = _get_client()
        sh = gc.open_by_key(spreadsheet_id)
        ws = sh.add_worksheet(title=title, rows=rows, cols=cols)
        return f"Created worksheet '{ws.title}' ({rows} × {cols})"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def create_spreadsheet(title: str) -> str:
    """Create a new Google Spreadsheet. Returns the spreadsheet ID and URL."""
    try:
        gc = _get_client()
        sh = gc.create(title)
        return f"Created: {sh.title}\nID: {sh.id}\nURL: {sh.url}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def format_cells(
    spreadsheet_id: str,
    worksheet: str,
    range_notation: str,
    bold: bool | None = None,
    font_size: int | None = None,
    bg_color: str | None = None,
    fg_color: str | None = None,
    horizontal_alignment: str | None = None,
) -> str:
    """Apply formatting to a cell range.
    Colors as hex strings '#4472C4' or names: red, blue, green, yellow, white, black.
    horizontal_alignment: 'LEFT', 'CENTER', 'RIGHT'.
    """
    try:
        from gspread_formatting import (
            CellFormat,
            Color,
            TextFormat,
            format_cell_range,
        )

        NAMED_COLORS = {
            "red": "#FF0000",
            "blue": "#0000FF",
            "green": "#00FF00",
            "yellow": "#FFFF00",
            "white": "#FFFFFF",
            "black": "#000000",
            "gray": "#808080",
            "orange": "#FFA500",
        }

        def _parse_color(c: str) -> Color:
            c = NAMED_COLORS.get(c.lower(), c)
            c = c.lstrip("#")
            return Color(int(c[0:2], 16) / 255, int(c[2:4], 16) / 255, int(c[4:6], 16) / 255)

        ws = _get_worksheet(spreadsheet_id, worksheet)

        fmt_kwargs = {}
        text_fmt_kwargs = {}

        if bold is not None:
            text_fmt_kwargs["bold"] = bold
        if font_size is not None:
            text_fmt_kwargs["fontSize"] = font_size
        if fg_color is not None:
            text_fmt_kwargs["foregroundColor"] = _parse_color(fg_color)
        if text_fmt_kwargs:
            fmt_kwargs["textFormat"] = TextFormat(**text_fmt_kwargs)
        if bg_color is not None:
            fmt_kwargs["backgroundColor"] = _parse_color(bg_color)
        if horizontal_alignment is not None:
            fmt_kwargs["horizontalAlignment"] = horizontal_alignment.upper()

        if not fmt_kwargs:
            return "No formatting options specified."

        fmt = CellFormat(**fmt_kwargs)
        format_cell_range(ws, range_notation, fmt)
        return f"Formatted {worksheet}!{range_notation}"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")

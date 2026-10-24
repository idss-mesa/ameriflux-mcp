"""A minimal reader for the first worksheet of an xlsx file (BIF files; DESIGN.md D3).

xlsx is a zip of XML parts. The archive goes through :class:`SafeZip` and every part is
parsed with defusedxml (no entity expansion, no external references). Only what BIF
files use is supported: shared strings (plain and rich text), inline strings, formula
string results, booleans and numbers. Numbers keep the text Excel stored (``12764``,
``-83.347086``), so identifiers and coordinates are not reformatted.
"""

from __future__ import annotations

import re
from xml.etree.ElementTree import Element

from defusedxml import ElementTree

from ameriflux_mcp.ameriflux.files.zipsafe import SafeZip
from ameriflux_mcp.errors import ToolError

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
MAX_PART_BYTES = 64 * 1024 * 1024
_COL = re.compile(r"^([A-Z]+)")


def _text(node: Element | None) -> str:
    if node is None:
        return ""
    return "".join(t.text or "" for t in node.iter(f"{MAIN}t"))


def _column(ref: str) -> int:
    match = _COL.match(ref or "")
    if not match:
        return -1
    number = 0
    for char in match.group(1):
        number = number * 26 + (ord(char) - 64)
    return number - 1


def _parse(archive: SafeZip, part: str) -> Element:
    data = archive.read(part)
    if len(data) > MAX_PART_BYTES:
        raise ToolError(
            "invalid_argument",
            f"{part} is too large to read.",
            details={"reason": "xlsx_part_too_large"},
        )
    try:
        root: Element = ElementTree.fromstring(data)
    except Exception:
        raise ToolError(
            "invalid_argument",
            f"{archive.label} has an unreadable {part}.",
            details={"reason": "bad_xlsx"},
        ) from None
    return root


def _first_sheet(archive: SafeZip) -> str:
    names = {m.name for m in archive.members}
    try:
        workbook = _parse(archive, "xl/workbook.xml")
        rels = _parse(archive, "xl/_rels/workbook.xml.rels")
        sheet = workbook.find(f"{MAIN}sheets/{MAIN}sheet")
        rid = sheet.get(f"{REL}id") if sheet is not None else None
        for rel in rels.iter(f"{PKG_REL}Relationship"):
            if rel.get("Id") == rid:
                target = (rel.get("Target") or "").lstrip("/")
                target = target if target.startswith("xl/") else f"xl/{target}"
                if target in names:
                    return target
    except ToolError:
        pass
    if "xl/worksheets/sheet1.xml" in names:
        return "xl/worksheets/sheet1.xml"
    raise ToolError(
        "invalid_argument",
        f"{archive.label} has no worksheet.",
        details={"reason": "bad_xlsx"},
    )


def read_rows(data: bytes, *, label: str, max_bytes: int) -> list[list[str]]:
    """Every row of the first worksheet as strings (empty cells are ``""``)."""
    with SafeZip(data, max_member_bytes=max_bytes, label=label) as archive:
        names = {m.name for m in archive.members}
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            shared = [_text(si) for si in _parse(archive, "xl/sharedStrings.xml").iter(f"{MAIN}si")]
        sheet = _parse(archive, _first_sheet(archive))
    rows: list[list[str]] = []
    for row in sheet.iter(f"{MAIN}row"):
        cells: dict[int, str] = {}
        next_col = 0
        for cell in row.iter(f"{MAIN}c"):
            # A cell without a reference follows the previous one (ECMA-376 18.3.1.4).
            col = _column(cell.get("r", "")) if cell.get("r") else next_col
            next_col = max(col, 0) + 1
            kind = cell.get("t")
            value = cell.find(f"{MAIN}v")
            raw = value.text if value is not None and value.text is not None else ""
            if kind == "s":
                try:
                    text = shared[int(raw)]
                except (ValueError, IndexError):
                    text = ""
            elif kind == "inlineStr":
                text = _text(cell.find(f"{MAIN}is"))
            elif kind == "b":
                text = "TRUE" if raw == "1" else "FALSE"
            else:
                text = raw
            cells[max(col, 0)] = text.strip()
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(width)])
    return rows


__all__ = ["read_rows"]

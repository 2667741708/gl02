#!/usr/bin/env python3
"""Render the BF3D production DOCX with Microsoft Word for layout QA.

This verifier is intentionally separate from the generator. It opens the DOCX
read-only, updates fields in memory, repaginates it, exports a temporary PDF,
and reports the Word page count without modifying the source DOCX.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from win32com.client import DispatchEx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCX = (
    ROOT
    / "PT"
    / "高炉3D模型"
    / "高炉3D模型制作过程与内切面验收记录_20260717.docx"
)
DEFAULT_PDF = Path(r"C:\tmp\bf3d_process_docx_layout_preview.pdf")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the BF3D DOCX to PDF through Word for layout QA."
    )
    parser.add_argument("--docx", type=Path, default=DEFAULT_DOCX)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    docx_path = args.docx.resolve()
    pdf_path = args.pdf.resolve()
    if not docx_path.is_file():
        raise FileNotFoundError(docx_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    app = DispatchEx("Word.Application")
    app.Visible = False
    app.DisplayAlerts = 0
    document = None
    try:
        document = app.Documents.Open(
            FileName=str(docx_path),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            Visible=False,
        )
        for table_of_contents in document.TablesOfContents:
            table_of_contents.Update()
        document.Fields.Update()
        document.Repaginate()
        page_count = int(document.ComputeStatistics(2))  # wdStatisticPages
        document.ExportAsFixedFormat(
            OutputFileName=str(pdf_path),
            ExportFormat=17,  # wdExportFormatPDF
            OpenAfterExport=False,
            OptimizeFor=0,  # wdExportOptimizeForPrint
            Range=0,  # wdExportAllDocument
            Item=0,  # wdExportDocumentContent
            IncludeDocProps=True,
            KeepIRM=True,
            CreateBookmarks=1,  # wdExportCreateHeadingBookmarks
            DocStructureTags=True,
            BitmapMissingFonts=True,
            UseISO19005_1=False,
        )
        result = {
            "ok": pdf_path.is_file() and pdf_path.stat().st_size > 0,
            "docx": str(docx_path),
            "pdf": str(pdf_path),
            "page_count": page_count,
            "pdf_bytes": pdf_path.stat().st_size if pdf_path.exists() else 0,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    finally:
        if document is not None:
            document.Close(SaveChanges=False)
        app.Quit()


if __name__ == "__main__":
    raise SystemExit(main())

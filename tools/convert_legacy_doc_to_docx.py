from __future__ import annotations

import argparse
from pathlib import Path

import pythoncom
from win32com.client import dynamic


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a legacy Word .doc file to .docx with installed Microsoft Word.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    source = args.input.resolve(strict=True)
    target = args.output.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    pythoncom.CoInitialize()
    word = None
    document = None
    try:
        word = dynamic.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Open(str(source), False, True)
        document.SaveAs2(str(target), 16)
        print(f"converted={target}")
        return 0
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())

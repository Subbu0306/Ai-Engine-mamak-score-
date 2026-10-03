#!/usr/bin/env python3
import argparse
from pathlib import Path

import pymupdf
from openpyxl import Workbook

p = argparse.ArgumentParser()
p.add_argument("--output-dir", type=Path, required=True)
a = p.parse_args()
a.output_dir.mkdir(parents=True, exist_ok=True)
doc = pymupdf.open()
page = doc.new_page()
page.insert_textbox(
    pymupdf.Rect(72, 72, 520, 700),
    "Problem: Independent clinics lose 20 hours each week to manual follow-up. We interviewed 120 practice managers; 78% reported the same pain. Our working prototype automates reminders for a monthly fee of $50 per clinic. A six-month pilot has 100 paying clinics and 92% retention.",
    fontsize=11,
)
doc.save(a.output_dir / "deck.pdf")
doc.close()
wb = Workbook()
ws = wb.active
ws.title = "Forecast"
ws.append(["Metric", "Monthly"])
for row in [
    ("Paying Customers", 100),
    ("Average Revenue per Customer", 50),
    ("Gross Margin %", 60),
    ("Operating Expenses", 4000),
    ("Cash Balance", 12000),
    ("Customer Lifetime Months", 24),
    ("Customer Acquisition Cost", 300),
    ("EBITDA", 100),
]:
    ws.append(row)
wb.save(a.output_dir / "finance.xlsx")
print(a.output_dir)

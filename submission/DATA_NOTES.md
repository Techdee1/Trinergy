# Data notes (surprises found while building the evidence store)

Feeds the README "limitations" section. Everything here was checked against the 32 reports.

## Archive shape
- 32 daily drilling reports, each as XML (WITSML 1.4 `drillReport`), PDF and HTML. 8 wellbores:
  15/9-19-A, F-1, F-1-B, F-1-C, F-11-B, F-11-T2, F-12, F-15-D. There is **no report for 15/9-F-14**
  (it exists only among the out-of-scope wellbore files).
- The XML is the structured source of truth; the PDF is what we cite for page and section.
  The HTML contains no text that is not also in the PDF, so it adds nothing.
- All 54 PDF pages have a text layer (no OCR). One page (F-1-C 2014-03-26, p.2) holds only the
  two words "Test Temp HPHT () Comment".
- PyMuPDF splits some words ("Summar y", "Sur vey Station", "integrity tes\nt"); the locator
  removes all whitespace before matching.
- Encoding: 28 XML files declare ISO-8859-1; the four 15/9-19-A files declare nothing and are
  plain ASCII. `ElementTree` on the raw bytes reads both correctly (e.g. "MÆRSK INSPIRER").

- `metadata/document_manifest.csv` lists the 32 daily-report XML files correctly, but its `well_hint`
  column is unreliable: the year leaks into some hints (`15_9_F_12_2007`, `15_9_F_1_2013`), so counting
  distinct hints gives 11 "wells" instead of 8. We count wellbores from the file names instead.

## Dates
- **A report dated D covers D-1 00:00 to D 00:00** (`period_start`/`period_end` on every record).
  Events "on D-1" are in the report dated D. In all four sample questions that name a sample time
  on D, the sample is timestamped D-1 inside the report dated D.
- Question dates match **report (file) dates**. The router uses the exact date D, and D+1 only
  when no report exists for that well on D (recorded in `reason`).
- F-1-B and F-1-C both have a report dated 2014-02-22, so wells are always filtered before dates.

## Missing values
- `-999.99` is the only sentinel (174 occurrences). It becomes missing and is never output as a value.
  The PDF prints `-999.99` verbatim.
- The literal text `None` appears in 5 summary/forecast fields (19-A 1980-01-01 x2, 19-A 1997-11-10
  forecast, F-11-B 2016-10-22 x2). Treated as missing and counted.

## The 1980-01-01 15/9-19-A report is a placeholder
Spud date 1997, no summary or forecast text, survey stations not sorted by depth. It still carries
`mdKickoff = 2178 m`, which is **printed in the PDF** (page 1, "Summary report"), so evidence can
cite both the XML and the PDF page.

## Fields the archive does not have
No cost, AFE, spread cost, personnel on board, supervisor/engineer name or weather/sea-state
elements exist in any XML, PDF or HTML file (`store.has_field` returns False for all four). Free-text
remarks do mention weather in 6 records ("Waited on weather"), but that is narrative, not a field.
No record anywhere names a mud-logging company or engineer. Company names occur only in `logInfo`:
**Western Atlas** (19-A 1997-08-29) is the service company for a *wireline* logging run
(tool string FMT-MAC-ZDL-HDIL-GR), not a mud-logging company, and F-1-C 2014-02-22 lists
Baker Hughes Inteq with an OnTrak tool.

## PDF and XML disagree
- **Tight well / HPHT:** the PDF prints `Y` for both in all 32 reports; the XML has `0` in all 32.
  The XML is authoritative. The locator never assigns a PDF location to these fields.
- **Days Ahead/Behind:** the PDF leaves it blank when the XML has `daysBehind` (11 reports).
- **Bit table:** the PDF prints fewer values than the XML has fields and they do not line up
  (e.g. XML `mdHoleStop` 2577, PDF shows 2574 twice). Only 2 bit records exist; trust the XML.
- **Column order:** PDF fluid samples are sorted by time of day, the XML is in report order.
  Tables print empty cells as nothing, so PDF columns cannot be trusted by position.

## PDF location coverage (records.parquet, 1707 records)
- Located to the exact row/field: 99.2% of table-row and narrative records, 94.5% of all records
  the PDF prints, 78.8% of all records.
- 219 records are in fields the PDF has no label for (mdPlanned, wellheadElevation, fixedRig,
  hole-start fields, pre-spud date, rig-alias details); 64 are tight well/HPHT, excluded by design.
  Citations for these can only name the XML.
- 74 printed-or-narrative records are not located: the 31 rig-code aliases, 32 NPD-number aliases,
  11 `daysBehind` values (blank in the PDF), and 5 missing summary/forecast texts (heading only).

## Name styles in questions
"15/9-19-A", "15/9-F-11 B", "15/9-F-11-T2", "F-11-B", "F-1" all occur; the XML uses "NO 15/9-F-1 C".
Bare "F-1" means the main wellbore only. Questions name a well and date that are not in the archive
(F-14 2013-06-10) and a date missing for a known well (F-15-D 2013-12-15 and 12-16).

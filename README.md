# Recruiter Night

A template for a pre-career-fair matching event: recruiters and students each fill out a
form, and a matching engine turns those responses into a full event plan, printable
student cards, printable recruiter rosters, and a room map, without anyone manually
pairing people up. Originally built for a single fraternity chapter at Missouri S&T, this
repo is set up so any student org, department, or career center can adapt it. (Make sure to
unzip the recruiter-night-repo.zip before starting)

Full plain-language write-up: [`docs/Recruiter_Night_System_Overview.pdf`](docs/Recruiter_Night_System_Overview.pdf).

## Using this for your own event

The matching logic, the CSV format, and the Excel output have no school baked into them,
they work as-is. Three things do need your own details before you run anything:

1. **`forms/recruiter_night_forms.gs`** — fill in the `CONFIG` block at the top (your
   org name, school, event date, caterer). The `MAJORS` and `INDUSTRIES` arrays are one
   school's example taxonomy, replace both with your own.
2. **`forms_to_csv.py`** — its canonical majors list and industry buckets need to match
   whatever you put in the Apps Script, or it won't recognize the answers. Search for
   "CANONICAL VOCABULARIES" near the top of the file.
3. **`mst_data.py`** — this is Missouri S&T's real major distribution and historical
   employer mix, bundled only as example data for the `--mst` demo/test mode. It's not
   required for real use; write your own equivalent if you want a realistic test
   population for your own school, or skip it and just point the pipeline at your real
   form exports.

## How it fits together

```
Google Forms  →  forms_to_csv.py  →  recruiters.csv + students.csv  →  matching_algorithm.py  →  workbook + CSVs
 (collect)         (clean & convert)                                    (match & build)
```

- **Collect** — recruiters and students fill out Google Forms. Responses live in a linked
  Google Sheet; download as Excel to feed the pipeline.
- **Convert** — `forms_to_csv.py` turns messy raw exports into two clean CSVs, resolves each
  student's guaranteed "wildcard" picks, and flags anything that needs a human look.
- **Match & build** — `matching_algorithm.py` scores every possible student-recruiter pair and
  assigns matches in stages (guaranteed picks, equity floor, recruiter floor, general fill,
  backfill). With `--excel`, it calls `excel_out.py` to build the full printable workbook.

## Running it

```bash
pip install pandas numpy openpyxl reportlab

python3 forms_to_csv.py --recruiters recruiters_raw.xlsx --stage1 students_stage1.xlsx \
    --stage2 students_stage2.xlsx --out-recruiters recruiters.csv --out-students students.csv

python3 matching_algorithm.py --recruiters recruiters.csv --students students.csv \
    --matches 4 --wildcards 2 --equity 2 --excel
```

Read the terminal output before printing anything, it prints match quality, a timing
verdict (HEALTHY / TIGHT / TOO THIN), and flags any recruiter that fell short of its
guaranteed minimum.

## Files

| Path | What it does |
|---|---|
| `forms_to_csv.py` | Converts raw Google Forms exports into clean `recruiters.csv` / `students.csv`. Generic, customize the majors/industries lists. |
| `matching_algorithm.py` | The matching engine and CLI entry point. Fully generic, no school-specific logic. |
| `excel_out.py` | Builds the 8-tab Excel workbook. Generic. Called automatically by `matching_algorithm.py --excel`. |
| `mst_data.py` | Example only: Missouri S&T's real major distribution and historical employer industry mix, used by `--mst` demo mode. |
| `make_fake_forms.py` | Generates realistic messy test data for dry runs, built against `mst_data.py`'s example numbers. |
| `forms/recruiter_night_forms.gs` | Google Apps Script that builds the Google Forms. Generic, fill in the `CONFIG` block first. |
| `forms/RECRUITER_FORM.md`, `forms/STUDENT_FORMS.md` | The original Missouri S&T / SigEp question drafts these were built from. Historical reference, not a template. |
| `build_report.py` | Builds a specific chapter's COER partnership proposal PDF. Not a template, kept as a worked example of using the same visual style for a report. |
| `docs/` | The system overview report (generic) and that chapter's original proposal PDF (specific example). |

## Notes

- The exact/adjacent/off fit judgment the algorithm computes internally is never exposed
  on a recruiter roster, a student card, or any CSV export, recruiters and students see
  who they're meeting and why, not a machine-generated grade.
- Event timing is configurable via `--event-minutes`, `--food-minutes`, and `--open-minutes`,
  currently 30 min food, 120 min structured matching, 30 min open mingling.

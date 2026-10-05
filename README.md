# Recruiter Night

This is a template for a matching event that happens before a career fair. Recruiters and students
each fill out a form, and a matching engine turns those responses into a full event plan, printable
student cards, printable recruiter rosters, and a room map. Nobody has to pair people up by hand. I
originally built it for a single fraternity chapter at Missouri S&T, but this repo is set up so any
student org, department, or career center can adapt it. (Make sure to unzip
recruiter-night-repo.zip before you start!)

The full plain-language write-up is in
[`docs/Recruiter_Night_System_Overview.pdf`](docs/Recruiter_Night_System_Overview.pdf).

## Using this for your own event

The matching logic, the CSV format, and the Excel output don't have any school baked into them, so
they work as is. Three things do need your own details before you run anything:

1. **`forms/recruiter_night_forms.gs`:** fill in the `CONFIG` block at the top (your org name,
   school, event date, and caterer). The `MAJORS` and `INDUSTRIES` arrays are one school's example
   lists, so replace both with your own.
2. **`forms_to_csv.py`:** its master list of majors and its industry buckets have to match whatever
   you put in the Apps Script, or it won't recognize the answers. Search for "CANONICAL
   VOCABULARIES" near the top of the file.
3. **`mst_data.py`:** this is Missouri S&T's real major distribution and historical employer mix,
   included only as example data for the `--mst` demo/test mode. You don't need it for a real event.
   Write your own version if you want a realistic test population for your school, or skip it and
   point the pipeline straight at your real form exports.

## How it fits together

```
Google Forms  →  forms_to_csv.py  →  recruiters.csv + students.csv  →  matching_algorithm.py  →  workbook + CSVs
 (collect)         (clean & convert)                                    (match & build)
```

- **Collect:** recruiters and students fill out Google Forms. The responses land in a linked Google
  Sheet, which you download as Excel to feed the pipeline.
- **Convert:** `forms_to_csv.py` turns the messy raw exports into two clean CSVs, locks in each
  student's guaranteed "wildcard" picks, and flags anything a human should look at.
- **Match and build:** `matching_algorithm.py` scores every possible student-recruiter pair and
  assigns matches in stages (guaranteed picks, equity floor, recruiter floor, general fill, and
  backfill). With `--excel`, it calls `excel_out.py` to build the full printable workbook.

## Running it

```bash
pip install pandas numpy openpyxl reportlab

python3 forms_to_csv.py --recruiters recruiters_raw.xlsx --stage1 students_stage1.xlsx \
    --stage2 students_stage2.xlsx --out-recruiters recruiters.csv --out-students students.csv

python3 matching_algorithm.py --recruiters recruiters.csv --students students.csv \
    --matches 4 --wildcards 2 --equity 2 --excel
```

Read the terminal output before you print anything. It shows the match quality, a timing verdict
(HEALTHY / TIGHT / TOO THIN), and flags any recruiter that came up short of its guaranteed minimum.

## Files

| Path | What it does |
|---|---|
| `forms_to_csv.py` | Converts raw Google Forms exports into clean `recruiters.csv` / `students.csv`. Generic, but customize the majors/industries lists. |
| `matching_algorithm.py` | The matching engine and CLI entry point. Fully generic, with no school-specific logic. |
| `excel_out.py` | Builds the 8-tab Excel workbook. Generic. Called automatically by `matching_algorithm.py --excel`. |
| `mst_data.py` | Example only: Missouri S&T's real major distribution and historical employer industry mix, used by the `--mst` demo mode. |
| `make_fake_forms.py` | Generates realistic, messy test data for dry runs, built around the example numbers in `mst_data.py`. |
| `forms/recruiter_night_forms.gs` | Google Apps Script that builds the Google Forms. Generic, but fill in the `CONFIG` block first. |
| `forms/RECRUITER_FORM.md`, `forms/STUDENT_FORMS.md` | The original Missouri S&T / SigEp question drafts these were built from. Historical reference, not a template. |
| `build_report.py` | Builds one specific chapter's COER partnership proposal PDF. Not a template. It's kept as a worked example of reusing the same visual style for a report. |
| `docs/` | The system overview report (generic) and that chapter's original proposal PDF (a specific example). |

## Notes

- The algorithm grades each match internally as exact, adjacent, or off, but that grade never shows
  up on a recruiter roster, a student card, or any CSV export. Recruiters and students see who
  they're meeting and why, not a grade a machine gave them.
- You can change the event timing with `--event-minutes`, `--food-minutes`, and `--open-minutes`.
  Right now it's 30 minutes of food, 120 minutes of structured matching, and 30 minutes of open
  mingling.

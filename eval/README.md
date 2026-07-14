# Hand-labeled eval set — YOU fill this in (Week 1 milestone)

Place your labeled CSV here as `labels.csv` when ready.

## Columns (suggested)

| column | description |
|--------|-------------|
| `id` | unique id, e.g. `001` |
| `source_url` | career page URL you fetched |
| `raw_html_path` | optional path under `eval/fixtures/` if you save HTML |
| `company` | ground-truth company name |
| `role_title` | ground-truth role title |
| `location` | ground-truth location (or empty) |
| `deadline` | ground-truth deadline ISO date (or empty) |
| `is_relevant` | `yes` or `no` for your profile |
| `notes` | why you labeled it that way |

We paused automated eval until you finish labeling 40–50 real postings.

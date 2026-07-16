# Hand-labeled eval set

`labels.csv` is the ground-truth set the agent is scored against. Dead or unlisted
postings are moved to `labels_retired.csv` so scores reflect live jobs only.

## Columns

| column | description |
|--------|-------------|
| `id` | unique id, e.g. `1` |
| `source_url` | career page URL |
| `raw_html_path` | optional (unused for now) |
| `company` | ground-truth company name |
| `role_title` | ground-truth role title |
| `location` | ground-truth location (or empty) |
| `deadline` | ISO date or empty |
| `is_relevant` | `yes` or `no` for your profile |
| `notes` | why you labeled it that way |

## Run the harness

Start small (saves API credits):

```bash
source .venv/bin/activate
rolegrep-eval --limit 3
rolegrep-eval --ids 1,6,15
```

Full set (~31 live examples; dead URLs moved to `labels_retired.csv`):

```bash
rolegrep-eval
```

Results are saved under `eval/runs/` (JSON + `history.jsonl` score log).

## What it measures

- Per-field precision / recall / accuracy for `company`, `role_title`, `location`, `deadline`
- Classification accuracy (+ P/R for relevant=yes) for `is_relevant`
- Latency and token usage when the provider reports it
- A failure list with a short hypothesis per miss

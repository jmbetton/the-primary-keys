# Project plan

Agreed plan for the ECO 395M final project. Work is tracked in issues [#1–#12](https://github.com/jmbetton/the-primary-keys/issues); this file is the reference for how the pieces fit together.

## Context

The final project (presentations **Sat Dec 12**, 1–3pm) must load data into a database,
analyze and visualize it, and use one technology not covered in homework. AI use is
allowed on this project. The group (repo
[`jmbetton/the-primary-keys`](https://github.com/jmbetton/the-primary-keys), public,
collaborators `jmbetton`, `RamyL2022`, `Rhamnos`) picked:

- **Data:** LBNL "Queued Up" interconnection-queue data (already in the repo as
  `data/grid-queue-data.csv`: 38,201 rows, 30 columns; **7,666 PJM rows**).
- **Text corpus:** PJM System Impact Study (SIS) reports, one per project.
- **New technology:** vector search with **pgvector**, embeddings from **local
  Qwen3-Embedding-0.6B**.
- **Dashboard:** Streamlit, run locally.
- **Question:** *Among PJM projects that reached a System Impact Study, are projects
  whose reports describe major network upgrades more likely to withdraw?*

**Checked 2026-11-24:**
- **Join key works.** LBNL `q_id` uses PJM queue positions (`AD2-038`). The report URL
  is `https://www.pjm.com/pjmfiles/pub/planning/project-queues/impact_studies/<id lowercased, no dash>_imp.{pdf|htm}`.
- **Coverage.** A 48-project sample from queues W1–AH1 found a report for 6/6
  operational, 6/7 active and 17/34 withdrawn projects, and 0/4 from AH1. Expect about
  2,000–2,800 reports from queues ~W1–AG1 (about 4,300 PJM rows).
- **Hardware.** Will's laptop has an RTX 4070 GPU, so the full embedding run should
  take minutes, not hours (rough guess). Teammates develop on a `--limit` subset on CPU.
- **Repo today:** `data/grid-queue-data.csv`, `eda/eda.py` (Josh's EDA), an empty
  `requirements.txt`, and a `.gitignore` that only lists `.vscode`.

## Repo layout (target)

```
the-primary-keys/
  README.md               # the graded report + rerun instructions
  requirements.txt
  docker-compose.yml      # pgvector/pgvector:pg17, one service
  .env.example            # DB settings template; real .env gitignored
  data/grid-queue-data.csv            # existing
  data/raw/reports/                   # downloaded PDFs/HTML, gitignored
  sql/schema.sql
  code/
    db.py                 # get_connection() from .env; registers pgvector
    load_queue.py         # LBNL CSV -> projects table
    download_reports.py   # PJM SIS reports -> data/raw/reports + reports table
    extract_text.py       # pdf/htm -> plain text
    chunk_reports.py      # section split, boilerplate drop, length split
    embed_chunks.py       # Qwen3 vectors -> report_chunks.embedding
    pipeline.py           # ONE entry point: runs the five steps above in order
    upgrade_queries.py    # the upgrade-category query texts (shared by analysis + app)
    analysis.py           # SECOND entry point: tagging + withdrawal comparison + charts
    eval_retrieval.py     # labeled-query check of the embedding model
  app.py                  # THIRD entry point: streamlit run app.py
  artifacts/              # charts used in README
```

This follows the midterm repo's pattern (`midterm/bevo_big_data`: `code/`,
`artifacts/`, README sections Goal / Data / Findings / Methodology / Limitations).
`eda/eda.py` is Josh's; leave it to him whether it stays or moves to an appendix.

## Database schema (`sql/schema.sql`)

- `projects`: one row per LBNL row for `entity = 'PJM'`. Keep the columns the analysis
  uses: `q_id` (PK), `q_status`, `q_date`, `wd_date`, `on_date`, `ia_date`,
  `IA_phase_clean`, `state`, `county`, `poi_name`, `type_clean`, `mw_1`, `q_year`,
  `developer`.
- `reports`: `queue_id` (PK, FK → `projects`), `url`, `file_format`, `local_path`,
  `downloaded_at`, `http_status` (records misses too, so coverage is queryable),
  `full_text` (the whole extracted report, so the dashboard can show it in-app).
- `report_chunks`: `chunk_id` bigserial PK, `queue_id` FK → `reports`, `section`,
  `chunk_index`, `chunk_text`, `embedding vector(1024)`. HNSW index with
  `vector_cosine_ops`.

All SQL from Python uses `psycopg` with `%(name)s` parameters, never f-strings, as the
rubric requires. Krueger's `class-topics/python_api/loader.py` (named params, TRUNCATE +
one commit) is the in-class pattern to copy for `load_queue.py`.

## Pipeline steps

1. **Load.** Read the CSV with `encoding="utf-8-sig"` (it has a byte-order mark), filter
   to PJM, parse dates, then insert with `executemany` or COPY. Rerunnable via TRUNCATE.
2. **Download.** SELECT the `q_id`s for queues W1–AG1 from the DB → build slugs → try
   `.pdf`, then `.htm` → follow redirects, pause ~0.5 s between requests, skip files
   already on disk. About 4,300 IDs × up to 2 requests ≈ 1 hour on the first run.
3. **Extract.** `pypdf` for PDFs, BeautifulSoup (already in the course stack) for HTML.
   Normalize whitespace and keep heading lines. Save each report's full text to
   `reports.full_text`.
4. **Chunk.**
   - Split on the known SIS headings (Cost Summary, Transmission Owner Scope of Work,
     Summer/Winter Peak, Light Load, Short Circuit, Stability, Queue Dependencies,
     Affected Systems, System Reinforcements, …).
   - Drop the template sections (Preface, Introduction boilerplate) and any chunk whose
     normalized text appears in >20% of reports.
   - Split sections longer than ~800 words with a ~50-word overlap.
5. **Embed.** `SentenceTransformer("Qwen/Qwen3-Embedding-0.6B", revision=<pinned>)`,
   GPU if available, `batch_size` 16–32. Documents get no prefix; queries use
   `prompt_name="query"`. Write vectors with the `pgvector` adapter, then build the
   HNSW index after loading.

`pipeline.py --limit N` runs everything on N reports for development. The README
documents the full run.

## Analysis (`analysis.py`)

1. **Upgrade categories.** 3–5 query texts in `upgrade_queries.py`, e.g. "new
   substation or transmission line required", "line rebuild or reconductoring due to
   thermal overload", "stability or short-circuit breaker upgrades", "network upgrade
   cost exceeds $X million". The wording is the group's call.
2. **Project score.** For each category, SQL keeps each project's best chunk
   (`DISTINCT ON (queue_id) … ORDER BY queue_id, embedding <=> %(q)s`). Tag a project
   when its distance is below a threshold. Set the threshold by reading the top/bottom
   hits, and report how sensitive the results are to it.
3. **Outcome.** Withdrawn vs. reached operation, among projects with reports. Exclude
   `active`/`suspended` from the main comparison and report them separately.
4. **Comparison.** Withdrawal rate tagged vs. untagged, overall and within fuel type
   (`type_clean`), size band (`mw_1`) and queue cohort. Optionally a logit with those
   controls. 2–3 charts in `artifacts/`, all in one library (plotly, so the dashboard
   matches).
5. **README limitations to record:**
   - sample selection (only projects that reached the study stage have a report)
   - reports are snapshots and may predate a withdrawal for unrelated reasons
   - PJM-only, serial queues only
   - the threshold choice
   - correlation, not causation

## Dashboard (`app.py`)

Streamlit reading the same Postgres:
- free-text search box → embed query → ranked reports (one row per project) with the
  best-matching passage, project metadata and the PJM link
- each result's report name is a link-style button (`st.button(type="tertiary")`).
  Clicking it opens a **pop-up review window** (`@st.dialog`, `width="large"`) showing:
  - the project's details (status, fuel type, MW, queue date, withdrawal date)
  - the full report text from `reports.full_text`, with the matched passage
    highlighted
  - a button to open the original PJM file in a new tab
- the review stays inside the app, which also covers PJM's site being slow on
  presentation day
- **exact lookup box** next to the search box, for things vector search is bad at:
  queue ID (`AD2-038`), substation/point of interconnection (`Powerton`), or project
  name. Plain SQL on `projects` (`q_id`, `poi_name`, `project_name`) with
  `ILIKE %(pattern)s`. The `%…%` wildcards go into the parameter value in Python, never
  into the SQL string, and a literal `%`/`_` typed by the user is escaped. Matches list
  the same way and open the same pop-up.
- filters for fuel type, status and queue
- the findings charts

Reuse `db.py`, `upgrade_queries.py` and one cached model loader.

## Model check (`eval_retrieval.py`)

About 20 hand-labeled (query → correct queue_id/section) pairs. Report recall@5 for
Qwen3 vs. `bge-small-en-v1.5`. This goes in the README methodology section as the
answer to "why this model?"

## GitHub issues (each = branch → PR → merge)

Every member needs **≥2 issues and ≥5 meaningful commits merged to main**. The group
needs ≥30 commits. Suggested split (names are placeholders; the group assigns):

| # | Issue | Suggested owner (group assigns) |
|---|---|---|
| [#1](https://github.com/jmbetton/the-primary-keys/issues/1) | Repo setup: requirements.txt, .gitignore (`.env`, `data/raw/`), `.env.example`, docker-compose, README skeleton | A |
| [#2](https://github.com/jmbetton/the-primary-keys/issues/2) | `sql/schema.sql` + `db.py` + `load_queue.py` | B |
| [#3](https://github.com/jmbetton/the-primary-keys/issues/3) | `download_reports.py` + coverage table | C |
| [#4](https://github.com/jmbetton/the-primary-keys/issues/4) | `extract_text.py` (pdf + htm) + `reports.full_text` | A |
| [#5](https://github.com/jmbetton/the-primary-keys/issues/5) | `chunk_reports.py` incl. boilerplate removal | B |
| [#6](https://github.com/jmbetton/the-primary-keys/issues/6) | `embed_chunks.py` + HNSW index (run the full embed on the GPU laptop) | Will |
| [#7](https://github.com/jmbetton/the-primary-keys/issues/7) | `pipeline.py` entry point + `--limit` | C |
| [#8](https://github.com/jmbetton/the-primary-keys/issues/8) | Upgrade query texts + `eval_retrieval.py` labels | Will + 1 |
| [#9](https://github.com/jmbetton/the-primary-keys/issues/9) | `analysis.py` + charts | B / C |
| [#10](https://github.com/jmbetton/the-primary-keys/issues/10) | `app.py` Streamlit dashboard | A / Will |
| [#11](https://github.com/jmbetton/the-primary-keys/issues/11) | README: data documentation (LBNL columns used, what's missing, PJM SIS docs) | C |
| [#12](https://github.com/jmbetton/the-primary-keys/issues/12) | README: methodology, findings, limitations, extensions; final black/docstring cleanup pass | all |


## Timeline (Thanksgiving Nov 26–27 in the middle)

- **By Sun Nov 29:** issues 1–3 merged; full download started.
- **Tue Dec 1 (class work day):** get Krueger's goals for the vector-search component
  (his rubric requires it). Issues 4–5.
- **By Thu Dec 3 (work day):** issues 6–7; full DB built on Will's machine; `pg_dump`
  shared to teammates outside the repo for convenience.
- **By Sun Dec 6:** issues 8–10 first versions.
- **Dec 7–10:** README (11–12), cleanup pass, rehearse a ~10-minute talk, test the
  setup in the room.
- **Sat Dec 12:** present.


## Verification (end to end)

- `docker compose up -d`, then `python code/pipeline.py --limit 20` → `projects` has
  7,666 rows (`SELECT count(*)`), `reports` has 20 found rows, `report_chunks` has
  vectors (`SELECT count(*) WHERE embedding IS NOT NULL`).
- `EXPLAIN ANALYZE` on a top-10 `<=>` query shows the HNSW index scan.
- A known query (e.g. "new 500 kV substation required") returns sensible sections
  from the AD2-038-style reports.
- `python code/analysis.py` writes the charts to `artifacts/`; `streamlit run app.py`
  loads and searches.
- Lookup box: `AD2-038` returns exactly that project; `powerton` (any case) returns the
  Powerton projects; typing `%` doesn't return everything.
- Clean-clone test before the presentation: a fresh clone + README steps reproduces the
  charts. `black --check .` passes; `git grep -n "f\"SELECT\|f'SELECT"` finds nothing.

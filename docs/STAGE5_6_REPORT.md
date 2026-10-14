# Stage 5 and 6 report: web app and quick wins

Localhost only (127.0.0.1:8000), login required. Data: 38,371 Supreme Court judgments. Everything below was run on this machine on 2026-10-14. Cost: nothing is billed; LLM spend $0.00 of the $25 cap (no LLM feature built yet).

## What was built

| Area | Status | Notes |
|---|---|---|
| Search (Stage 5.1) | built | English full text and metadata, 7 scopes (everything, title words, English text, parties, typo-tolerant title, judge, identifier), filters for every filterable field that has data, facet counts that describe exactly the current result set, 4 sorts, highlighted snippets, “search within these results”, CSV of all results. Fields with no source data (case number, case type) are shown as such. |
| Judgment page (5.2) | built | Tabs: Overview (every `judgment` column with a source badge, “sources disagree” notes, report-an-error per field), Full text (search inside, chunk boundaries and page markers), Chunks (every column), Raw Vanga (all copies, including misfiled duplicates), Raw Vaquill, Identifiers, Judges, Provenance and conflicts, Original PDF (not loaded: Stage 10), Later phases (empty, “not built yet”). |
| Data explorer (5.3) | built | Reads the catalog; every table, view and materialised view the read-only role can read (credential tables excluded on purpose); sort, per-column filter, pagination, CSV. |
| Coverage dashboard (5.4) | built | Per year per source, null rate per field, conflicts, queue, text status, quality labels, PDF coverage (0). |
| Review queues (5.5) | built | Match queue (empty: no ambiguous matches), field conflicts (3), user error reports; admin accept/reject recorded in `review_decision` with the before-value. Decisions are recorded, not applied to merged data until the merge is rebuilt. |
| SQL console (5.6) | built | One SELECT/WITH/EXPLAIN, 10 s, 1,000 rows; the database role is read-only as well. |
| Benchmark page (5.7) | partial | Stores query lists and results; the scorecard and advocate test are Stage 8. |
| Feature inventory (5.8), Status (5.9) | built | Live catalog data; honest statuses. Status shows pipeline runs, row counts, sizes, last backup, LLM spend. |
| Quick win 1 Constitution Bench finder | built, with an estimate | See “Bench size” below. |
| Quick win 2 Judge pages | built, author unavailable | 279 judges; alias table; judgments, years active, companions, outcome mix. Who wrote each judgment is not in the sources. |
| Quick win 3 Facets with counts | built | Year (by decade), disposition, bench size, judge. Case type: unavailable. |
| Quick win 4 Time to decision | **unavailable** | `date_of_registration` is in neither source (0 rows). |
| Quick win 5 Permalinks and citation copy | built | `/j/<uuid>`, `/insc/<INSC-id>` (96 INSC ids are shared by several reports; that URL then lists them); copy INSC id, SCR citation, formatted citation, permalinks. No SCC/AIR citation is generated (0 such identifiers exist). |
| Quick win 6 Report an error | built | Every field; into `error_report` and the queue. |
| Quick win 7 Quality badge | built | clean / fair / noisy with hover explanation and filter. |
| Quick win 8 Export | built | CSV of results; text, Word, PDF of one judgment or a bundle of up to 25; notice and attribution inside every export. PDF uses Latin-1 fonts, so non-Latin text is only complete in the Word and text exports. Metadata-only judgments refuse export honestly. |
| Quick win 9 REST API and MCP | built | `/api/v1/search, judgment, judge, benches, facets`, API keys (hashed), per-key rate limit, usage log; MCP server `mcp/server.py` with the same four read operations, tested through a real stdio client. Every response carries attribution and the caveat. OpenAPI docs at /api/v1/docs (no login needed to read them; calls need a key). The docs page loads Swagger UI from a CDN, so the browser needs internet. |
| Stage 7 parts that need no public server | built | Footer, banner, hide-judgment with audit, backup script (see below). HTTPS, S3 and public takedown form deferred. |

## Data findings made while building

1. **Bench size.** Both sources list one judge for 91% of judgments; Kesavananda Bharati (13 judges, 1973) lists one. Fixed with a labelled, header-based estimate (`BENCH_ESTIMATE.md`): 88% coverage, 91% agreement where the source lists 2 or more judges, 23 of 24 hand-checked correct. With it the 1970s have 159 benches of 5 or more judges (7 from the source list alone); Rustom Cavasjee Cooper (1970, 11 judges) and Kesavananda Bharati (1973, 13 judges) appear. 1,415 judgments in all have 5 or more.
2. **Text quality.** English: 35,479 clean, 117 fair, none noisy. Other languages: 84,757 clean, 7,661 fair, 7,142 noisy. The 10 judgments whose text contained NUL are labelled noisy.
3. **Search had a 21-second trap:** a plain OR across metadata and full text defeated both indexes. Replaced with a UNION of two index scans (all searches now under 1.5 s).
4. **Stage 1 deliverables missing:** `LICENCES.md` and `SOURCE_PROFILE.md` had not been written; now written. The AWS registry page could not be read from here.

## Verification (47 tests, all passing)

`tests/test_app_http.py` (19): login required; all 12 navigation items load (14 URLs including two variants) with the notice; 5 judgments from the 1950s, 1970s, 1990s, 2010s and 2020s load all 10 tabs; the overview shows every `judgment` column; the explorer lists every readable table; the SQL console rejects 5 kinds of write and runs a select.
`tests/test_stage6.py` (13): one or more tests per quick win on real data, MCP over stdio, hide-judgment removes a judgment from the page, export, search and the view and is audited, API rejects missing, wrong and revoked keys and enforces the rate limit.
`tests/test_security.py` (15): viewer cannot use admin actions; five wrong passwords lock the user out; cross-origin POST refused; cookie is HttpOnly and SameSite=Strict; logout invalidates the session; the read-only role cannot write or read `app_user` and `api_key` (8 statements); the app role cannot touch judgment data; Postgres and the app listen on 127.0.0.1 only.
`tests/shots.py`: headless Chromium visits every nav page and the five sample judgments (plus the text tab with chunk boundaries and a search term) with no console errors; phone width checked by screenshot (`logs/shots/`).

## Speed (web, median of 8 requests, includes facets and snippets; backup was running at the same time)

| query | p50 ms | max ms |
|---|---|---|
| rare term (Kesavananda) | 1080 | 1437 |
| common phrase (natural justice, 10,305 hits) | 808 | 861 |
| common word (contract) | 746 | 962 |
| phrase plus exclusion | 347 | 995 |
| title words | 40 | 55 |
| party contains | 62 | 242 |
| typo-tolerant title | 68 | 88 |
| judge name | 53 | 69 |
| identifier prefix | 154 | 205 |
| filters only | 42 | 46 |
| text plus filters | 352 | 477 |

Targets from the brief: full-text over all judgments under 2 s met; facet counts under 500 ms met (the stored facet views read in about 1 ms; per-query facets are inside the timings above); party fuzzy under 300 ms met; `title_fuzzy` met after the threshold change (p95 197 ms).

## Backup

`infra/backup.sh` (pg_dump custom format to `/var/backups/eli`, archive listed end to end, keeps 2, refuses under 4 GB free) and `infra/backup_loop.sh` (nightly 02:15 stand-in, because the sandbox has no cron or systemd). 
First dump: 3.5 GB in 13 minutes (`/var/backups/eli`), 45 table-data entries. Checks run on it:
* `pg_restore -f /dev/null` read and decompressed the whole archive without error (1 minute).
* **Partial restore test:** 10 tables (court, judgment, judge, judge_alias, judgment_judge, judgment_source_map, judgment_identifier, judgment_language, field_conflicts, judgment_field_provenance) were restored into a scratch database; row counts and an md5 over the sorted key and value columns were identical to the live database for all 10. The scratch database was dropped.
* **Not done:** a full restore (including the 3.7 GB of text and the index rebuild) because it needs about 11 GB and 6.5 GB were free. Do it on a machine with more disk before relying on the dump as the only copy; the database is also reproducible from `raw/` (Stages 3 and 4).

## Limits to know

* Only English text is full-text searchable. Judgments with only translations show “no English text”.
* 2,775 judgments (1,357 no text, 1,418 translation only) are metadata-only until the targeted PDF step, which waits for your approval.
* Bench size from the header is an estimate; 289 header counts are lower than the source list and have not been examined; 12% of English judgments have no readable header.
* Review decisions are recorded but do not change merged data until the merge is rebuilt.
* Python changes need an app restart; the nightly backup loop dies with the container.
* Auth is simple local login, not hardened for the public internet. Do not expose the port.

## Next

Stage 7 remainder (HTTPS, off-machine backups, public takedown form) needs a public host and your go-ahead. Stage 8 (scorecard, advocate protocol) can start on your word. The targeted PDF step needs your yes. Stage 9 needs the OpenRouter key in `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` and your confirmation of the spend cap.

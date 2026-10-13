# Stage 3 validation report

Build `b2edb7915b851`, validated 2026-10-13 20:22 UTC by `pipeline/06_validate_stage3.py`. Every check below is computed from `build/*.parquet` and, where noted, re-derived independently from the raw files.

**Result: 41 PASS, 3 EXCEPTION (explained), 0 FAIL, 5 informational / not run.**

## Checks

| id | check | status | measured |
|---|---|---|---|
| A1 | raw/ unchanged since the first manifest (sha256 of all 43,786 files re-verified) | PASS | files: 43786 (manifest 43786); added 0, removed 0, changed 0 |
| A2 | Vanga: parquet rows = JSON files = source_vanga_raw rows | PASS | parquet 43,552, json 43,552, staged 43,552 |
| A3 | Vanga JSON and parquet agree on raw_html, nc_display and scraped_at for every row | PASS | 43,552 of 43,552 identical |
| A4 | Vaquill: source_vaquill_raw has one row per raw case_id | PASS | raw 37,014, staged 37,014 |
| A5 | source_vanga_raw JSON reproduces the original parquet values (title, case_id, citation, date, languages, judge) | PASS | 0 differing rows |
| B1 | canonical judgments = distinct Vanga paths = canonical copies in staging | PASS | judgments 38,371, distinct ids 38,371, distinct paths 38,371, canonical copies 38,371 |
| B2 | judgment_id is the stable uuid5 of the Vanga path (recomputed for every row) | PASS | 0 mismatches |
| B3 | duplicate resolution: staged rows = canonical + misfiled; exactly one canonical copy per path | PASS | 43,552 rows = 38,371 canonical + 5,181 misfiled; paths without exactly one canonical copy: 0 |
| B4 | folder-year rule: every misfiled copy has folder year != decision year; every kept duplicate has folder year = decision year | PASS | misfiled copies 5,181, kept duplicate copies 5,181, violations 0 |
| B5 | no two canonical judgments share both INSC id and citation | PASS | 0 duplicate (insc_id, citation) pairs |
| B6 | INSC ids shared by more than one canonical judgment (kept distinct, flagged `insc_id_shared`) | INFO | 96 ids |
| C1 | every Vaquill case is matched or in the review queue (none dropped) | PASS | 37,014 cases = 37,014 matched + 0 in review |
| C2 | judgments = matched + in_review + vanga_only | PASS | {'matched': 37014, 'vanga_only': 1357} |
| C3 | independent re-derivation from the raw files (INSC id + citation + date) gives the same matched count | PASS | raw re-derivation 37,014 pairs / 37,014 cases; build 37,014 |
| C4 | ambiguous / conflicting matches are queued, never merged (queue contents shown) | PASS | queue by kind: empty |
| C5 | no Vaquill case without a Vanga counterpart (Vaquill-only judgments) | PASS | 0 orphans |
| C6 | every matched pair agrees on decision date | PASS | 0 disagreements |
| D1 | chunk key (judgment_id, language_code, chunk_index) and vaquill_chunk_id are unique | PASS | duplicate keys 0, duplicate chunk ids 0 |
| D2 | every raw Vaquill chunk is preserved (row count) | PASS | raw 1,113,313, judgment_chunk 1,113,313 |
| D3 | per-case chunk counts equal the raw counts | PASS | 0 cases differ |
| D4 | raw chunks are byte-identical: text, offsets, pages, section, language (header NOT stripped in judgment_chunk) | PASS | text differs 0, other columns differ 0 |
| D5 | text_original is NULL only where it equals text in the raw data (lossless) | PASS | rows keeping text_original 0, rows where it was dropped but differed 0 |
| D6 | every chunk set is complete (chunks 0..n-1 present, n = total_chunks, no missing text) | EXCEPTION | 277 of 135,156 sets are incomplete: 180 with chunk indexes missing or a count different from total_chunks, 276 with a gap of more than 2 characters between chunks. English sets incomplete: 23. Most affected languages: hin 211, en 23, pun 17, mal 10.  Explanation: Vaquill delivers these sets with chunks missing. They are kept as delivered, flagged `is_complete = false` (and `incomplete_english_text` on the judgment for English), and not repaired or guessed. |
| E1 | one assembled text per (judgment, language) that has chunks | PASS | language rows with text 135,156, texts 135,156 |
| E2 | no Vaquill header left in any assembled text | PASS | 0 texts still contain a 'Case: ... Section: ...' header |
| E3 | every raw chunk began with the header (so stripping was uniform) | PASS | 0 chunks without a header |
| E4 | overlapping chunk windows agree with the text already assembled | EXCEPTION | 565 overlap regions disagreed in 362 texts (40 differ only in whitespace); English: 106 events in 80 texts, of 35,596 English texts  Explanation: Inside the overlap of two Vaquill chunks the characters differ (examples seen: redacted `xxx` passages, repeated list letters, broken glyphs in Indic scripts). The earlier chunk's characters are kept and the later chunk's overlapping part is dropped. Affected texts are listed by `overlap_mismatches > 0`. |
| E5 | chunk body length equals the char_end - char_start window | EXCEPTION | 501 chunks differ in length from their offset window (median \|difference\| 7, 95th percentile 68, max 553 characters)  Explanation: The offsets Vaquill supplies do not exactly match the body length for these chunks. Each chunk is still placed at its own char_start, so the drift does not propagate to later chunks. |
| E6 | assembled length vs the last chunk's char_end | INFO | equal for 134,828 texts, different for 328 (mean absolute difference 9.4 characters) |
| E7 | no empty assembled texts | PASS | 0 empty |
| E8 | positional check: in 1,500 sampled complete texts, every chunk body sits at its char_start in the assembled text | PASS | 0 of 1500 sampled texts failed |
| F1 | text_status reconciles: english + translation_only = matched judgments; none = unmatched | PASS | {'english': 35596, 'translation_only': 1418, 'none': 1357} |
| F2 | 'no English text' is distinct from 'no text at all' (none => no texts; translation_only => texts but no English; english => has English) | PASS | violations: none-with-text 0, translation-with-English 0, english-without-English 0 |
| F3 | metadata is complete for judgments without usable full text (searchable by metadata) | PASS | 2,775 of 2,775 judgments without English text have title, date and citation |
| F4 | language sets whose chunk count differs from total_chunks (same sets as D6) | INFO | 0 |
| G1 | decision_year equals the year of decision_date for every judgment | PASS | 0 mismatches |
| G2 | every judgment has a parsed decision date | PASS | 0 without |
| G3 | original source-year fields retained (Vanga on every row, Vaquill on every matched row) | PASS | vanga_year_field 38,371/38,371, vaquill_year_field 37,014/37,014 |
| G4 | source-year conflicts are recorded and resolved by one deterministic rule (decision_year from decision_date) | PASS | 3 conflicts between Vanga year and Vaquill year; all keep decision_year = year(decision_date) |
| G5 | source year fields that differ from the decision year (flagged, not corrected) | INFO | Vanga 5,179 (13.5%), Vaquill 5,152; INSC-id year differs: 52 |
| H1 | every judgment has provenance for all 12 tracked fields | PASS | 460,452 rows, expected 460,452 |
| H2 | the value stored in judgment equals the provenance chosen_value, field by field | PASS | mismatches: none |
| H3 | every field conflict is surfaced in field_conflicts and keeps the other value as alt_value | PASS | conflicts by field: {'source_year': 3} |
| H4 | fields with no source stay NULL (case_number, diary_number, pdf_url); OCR description is not used | PASS | non-null counts: (0, 0, 0) |
| H5 | bench_strength equals the number of judgment_judge rows | PASS | 0 mismatches |
| H6 | identifiers unique on (type, value, judgment_id) | PASS | 0 duplicates |
| H7 | judgment_judge rows by source | INFO | vaquill 42,841, vanga 1,564 |
| I1 | rebuilding from the same raw files gives identical table contents | PASS | 12/12 tables identical |
| J1 | every column written to build/*.parquet exists in the migration DDL (checked against a scratch PostgreSQL 16) | PASS | 22 tables inspected |

## Match outcomes (judgment_source_map)

| match_method | match_status | judgments |
|---|---|---|
| insc_id+citation | matched | 37,014 |
| none:no_vaquill_candidate | vanga_only | 1,111 |
| none:empty_insc_id | vanga_only | 128 |
| none:shared_insc_id_citation_differs | vanga_only | 118 |

## Sample of incomplete chunk sets

| judgment_id | language | chunks present | chunks expected | large gaps |
|---|---|---|---|---|
| 000265ee-aec9-59a0-81e4-7ab0dcaba7ac | hin | 4 | 4 | 1 |
| 016dc5b9-4c9d-52d9-be1d-5ae030464ebc | pun | 5 | 5 | 1 |
| 0185bc92-a9a7-5404-a828-2c799f75d7e8 | ben | 66 | 66 | 8 |
| 025c3999-7966-5880-955d-2a48e60e4be2 | hin | 19 | 19 | 1 |
| 02c6bb75-7746-540d-a5fe-833b53ceccfb | hin | 28 | 28 | 1 |
| 02dbd051-e214-58db-99d3-5e899ddb56d6 | hin | 35 | 35 | 1 |
| 03e4e326-c903-57f5-b044-90bda9f515a7 | pun | 11 | 11 | 1 |
| 043210b9-eea8-5138-afc3-8a5756a66c19 | hin | 32 | 32 | 2 |

## Text assembly quality by language

| language | texts | incomplete | gap = 2 chars (normal) | gap 3-24 | gap > 24 | overlap mismatches | texts with mismatch | length-drift chunks |
|---|---|---|---|---|---|---|---|---|
| pun | 36,127 | 17 | 71,617 | 10 | 8 | 96 | 61 | 110 |
| en | 35,596 | 23 | 67,140 | 16 | 7 | 106 | 80 | 149 |
| hin | 35,431 | 211 | 40,567 | 67 | 345 | 291 | 178 | 120 |
| ben | 4,973 | 5 | 1,744 | 24 | 2 | 6 | 2 | 3 |
| guj | 4,785 | 2 | 6,149 | 1 | 1 | 1 | 1 | 2 |
| mal | 3,739 | 10 | 3,628 | 6 | 8 | 37 | 14 | 62 |
| tam | 3,661 | 8 | 5,878 | 8 | 0 | 16 | 15 | 31 |
| mar | 3,097 | 0 | 3,959 | 0 | 0 | 1 | 1 | 2 |
| urd | 2,213 | 0 | 1,304 | 0 | 0 | 1 | 1 | 4 |
| tel | 2,198 | 0 | 1,316 | 0 | 0 | 2 | 2 | 5 |
| kan | 2,101 | 1 | 1,437 | 1 | 0 | 6 | 6 | 10 |
| ori | 662 | 0 | 803 | 0 | 0 | 2 | 1 | 3 |
| asm | 332 | 0 | 195 | 0 | 0 | 0 | 0 | 0 |
| nep | 171 | 0 | 179 | 0 | 0 | 0 | 0 | 0 |
| san | 55 | 0 | 160 | 0 | 0 | 0 | 0 | 0 |
| kok | 15 | 0 | 28 | 0 | 0 | 0 | 0 | 0 |

## Judgments by text status

| text_status | judgments |
|---|---|
| english | 35,596 |
| none | 1,357 |
| translation_only | 1,418 |

## English text coverage by decade of decision (all canonical judgments)

| decade | judgments | english text | translation only | no text | % english |
|---|---|---|---|---|---|
| 1950 | 1,004 | 981 | 2 | 21 | 97.7 |
| 1960 | 3,170 | 3,165 | 2 | 3 | 99.8 |
| 1970 | 2,928 | 2,926 | 2 | 0 | 99.9 |
| 1980 | 2,700 | 2,689 | 11 | 0 | 99.6 |
| 1990 | 6,497 | 6,454 | 20 | 23 | 99.3 |
| 2000 | 9,091 | 7,330 | 1,320 | 441 | 80.6 |
| 2010 | 7,931 | 7,757 | 38 | 136 | 97.8 |
| 2020 | 5,050 | 4,294 | 23 | 733 | 85.0 |

## Language availability (texts from Vaquill vs PDFs Vanga lists)

| language | text available | PDF listed | listed but no text | text but not listed |
|---|---|---|---|---|
| pun | 36,127 | 36,982 | 870 | 15 |
| en | 35,596 | 37,213 | 2,055 | 438 |
| hin | 35,431 | 36,443 | 1,030 | 18 |
| ben | 4,973 | 5,957 | 1,490 | 506 |
| guj | 4,785 | 4,509 | 85 | 361 |
| mal | 3,739 | 3,781 | 115 | 73 |
| tam | 3,661 | 3,190 | 184 | 655 |
| mar | 3,097 | 3,077 | 36 | 56 |
| urd | 2,213 | 2,619 | 407 | 1 |
| tel | 2,198 | 2,546 | 355 | 7 |
| kan | 2,101 | 2,067 | 20 | 54 |
| ori | 662 | 698 | 84 | 48 |
| asm | 332 | 344 | 13 | 1 |
| nep | 171 | 171 | 0 | 0 |
| san | 55 | 56 | 1 | 0 |
| kok | 15 | 17 | 2 | 0 |
| gar | 0 | 13 | 13 | 0 |
| kas | 0 | 1 | 1 | 0 |
| kha | 0 | 7 | 7 | 0 |

## Source-year conflicts (Vanga `year` vs Vaquill `year`)

| vanga_path | insc_id | vanga year | vaquill year | decision_date | decision_year |
|---|---|---|---|---|---|
| S_1996_3_548_559 | 1999 INSC 276 | 1996 | 1999 | 1999-07-15 | 1999 |
| S_1996_5_582_592 | 1998 INSC 349 | 1996 | 1998 | 1998-09-06 | 1998 |
| S_1997_3_386_395 | 1999 INSC 312 | 1997 | 1999 | 1999-08-08 | 1999 |

## Provenance: chosen source per field

| field | chosen_source | judgments |
|---|---|---|
| available_languages | none | 1,158 |
| available_languages | vanga | 37,213 |
| bench_strength | derived | 38,355 |
| bench_strength | none | 16 |
| citation | vanga | 38,371 |
| cnr | vanga | 38,371 |
| court | vanga | 38,371 |
| decision_date | vanga | 38,371 |
| decision_year | derived | 38,371 |
| disposal | none | 975 |
| disposal | vanga | 37,396 |
| judges | none | 16 |
| judges | vanga | 1,355 |
| judges | vaquill | 37,000 |
| petitioner | none | 18 |
| petitioner | vanga | 38,353 |
| respondent | none | 18 |
| respondent | vanga | 38,353 |
| title | vanga | 38,371 |

## Provenance: fills and conflicts

No fills and no conflicts were needed beyond those listed in the conflict table.

## Field conflicts by field

| field | conflicts |
|---|---|
| source_year | 3 |

## Identifiers by type (no SCC, AIR or diary numbers exist in either source)

| type | rows |
|---|---|
| CNR | 38,371 |
| INSC | 38,243 |
| NC_DISPLAY | 38,243 |
| SCR | 38,371 |
| VANGA_PATH | 38,371 |

## Null / empty rate per field, before (Vanga canonical rows) and after the merge

| field | before % | after % |
|---|---|---|
| available_languages | 3.02 | 3.02 |
| citation | 0.00 | 0.00 |
| cnr | 0.00 | 0.00 |
| court | 0.00 | 0.00 |
| decision_date | 0.00 | 0.00 |
| disposal | 2.54 | 2.54 |
| judges | 0.04 | 0.04 |
| petitioner | 0.05 | 0.05 |
| respondent | 0.05 | 0.05 |
| title | 0.00 | 0.00 |

## Sample of 10 merged records across eras (canonical row next to both raw sources)

#### 1954 INSC 61: KISHAN LAL AND ANOTHER versus BHANW AR LAL

**Canonical judgment**

```json
{
 "judgment_id": "bac4185f-b5b4-58d8-97c9-ae229bdb189e",
 "vanga_path": "1955_1_439_448",
 "insc_id": "1954 INSC 61",
 "title": "KISHAN LAL AND ANOTHER versus BHANW AR LAL",
 "petitioner": "KISHAN LAL AND ANOTHER",
 "respondent": "BHANW AR LAL",
 "decision_date": "1954-05-12",
 "decision_year": 1954,
 "citation": "[1955] 1 S.C.R. 439",
 "cnr": "ESCR010000571955",
 "disposal": null,
 "court": "Supreme Court of India",
 "bench_strength": 1,
 "case_number": null,
 "diary_number": null,
 "pdf_url": null,
 "vanga_year_field": 1955,
 "vaquill_year_field": 1955,
 "vanga_year_folder": 1954,
 "available_languages": [
  "ben",
  "en",
  "guj",
  "hin",
  "kan",
  "mal",
  "ori",
  "pun",
  "tel",
  "urd"
 ],
 "text_status": "english",
 "match_status": "matched",
 "quality_flags": [
  "report_year_differs_from_decision_year"
 ],
 "vanga_scraped_at": "2026-01-09 10:32:11.022304",
 "build_id": "b2edb7915b851"
}
```

**Raw Vanga** (folder year 1954)

```json
{
 "title": "KISHAN LAL AND ANOTHER versus BHANW AR LAL",
 "petitioner": "KISHAN LAL AND ANOTHER",
 "respondent": "BHANW AR LAL",
 "description": "",
 "judge": "MEHR CHAND MAHAJAN",
 "author_judge": null,
 "citation": "[1955] 1 S.C.R. 439",
 "case_id": "1954 INSC 61",
 "cnr": "ESCR010000571955",
 "decision_date": "12-05-1954",
 "disposal_nature": "",
 "court": "Supreme Court of India",
 "available_languages": "ENG,BEN,GUJ,HIN,KAN,MAL,ORI,PUN,TEL,URD",
 "raw_html": "<5182 chars>",
 "path": "1955_1_439_448",
 "nc_display": "1954INSC61",
 "scraped_at": "2026-01-09T10:32:11.022304",
 "year": "1955",
 "citation_year": "1955"
}
```

**Raw Vaquill** (37 chunk rows)

```json
{"case_id":"1954_INSC_61","title":"KISHAN LAL AND ANOTHER versus BHANW AR LAL","petitioner":"KISHAN LAL AND ANOTHER","respondent":"BHANW AR LAL","disposition":"","case_number":"","citation":"[1955] 1 S.C.R. 439","decision_date":"1954-05-12","date_of_registration":"","court":"Supreme Court of India","court_code":"SCI","court_type":"supreme_court","bench":"","bench_strength":1,"judges":["MEHR CHAND MAHAJAN"],"description":"","source_url":"","year":1955}
```

**First 160 characters of the assembled English text:** `[SECTION] ## S.C.R. SUPREME COURT REPORTS  It was not denied that if the present action of the State cannot be defended as an act of State it cannot be saved un`

#### 1958 INSC 116: PANDIT M. S. M. SHARMA versus SHRI SRI KRISHNA SINHA AND OTHERS

**Canonical judgment**

```json
{
 "judgment_id": "fd145bae-5dea-5e8c-a248-16d371a331b6",
 "vanga_path": "S_1959_1_806_891",
 "insc_id": "1958 INSC 116",
 "title": "PANDIT M. S. M. SHARMA versus SHRI SRI KRISHNA SINHA AND OTHERS",
 "petitioner": "PANDIT M. S. M. SHARMA",
 "respondent": "SHRI SRI KRISHNA SINHA AND OTHERS",
 "decision_date": "1958-12-12",
 "decision_year": 1958,
 "citation": "[1959] SUPP. 1 S.C.R. 806",
 "cnr": "ESCR010001161959",
 "disposal": "Dismissed",
 "court": "Supreme Court of India",
 "bench_strength": 1,
 "case_number": null,
 "diary_number": null,
 "pdf_url": null,
 "vanga_year_field": 1959,
 "vaquill_year_field": 1959,
 "vanga_year_folder": 1958,
 "available_languages": [
  "en",
  "pun"
 ],
 "text_status": "english",
 "match_status": "matched",
 "quality_flags": [
  "report_year_differs_from_decision_year"
 ],
 "vanga_scraped_at": "2025-10-22 04:07:37.051479",
 "build_id": "b2edb7915b851"
}
```

**Raw Vanga** (folder year 1958)

```json
{
 "title": "PANDIT M. S. M. SHARMA versus SHRI SRI KRISHNA SINHA AND OTHERS",
 "petitioner": "PANDIT M. S. M. SHARMA",
 "respondent": "SHRI SRI KRISHNA SINHA AND OTHERS",
 "description": "",
 "judge": "SUDHI RANJAN DAS",
 "author_judge": null,
 "citation": "[1959] SUPP. 1 S.C.R. 806",
 "case_id": "1958 INSC 116",
 "cnr": "ESCR010001161959",
 "decision_date": "12-12-1958",
 "disposal_nature": "Dismissed",
 "court": "Supreme Court of India",
 "available_languages": "ENG,PUN",
 "raw_html": "<4994 chars>",
 "path": "S_1959_1_806_891",
 "nc_display": "1958INSC116",
 "scraped_at": "2025-10-22T04:07:37.051479",
 "year": "1959",
 "citation_year": "1959"
}
```

**Raw Vaquill** (105 chunk rows)

```json
{"case_id":"1958_INSC_116","title":"PANDIT M. S. M. SHARMA versus SHRI SRI KRISHNA SINHA AND OTHERS","petitioner":"PANDIT M. S. M. SHARMA","respondent":"SHRI SRI KRISHNA SINHA AND OTHERS","disposition":"Dismissed","case_number":"","citation":"[1959] SUPP. 1 S.C.R. 806","decision_date":"1958-12-12","date_of_registration":"","court":"Supreme Court of India","court_code":"SCI","court_type":"supreme_court","bench":"","bench_strength":1,"judges":["SUDHI RANJAN DAS"],"description":"","source_url":"","year":1959}
```

**First 160 characters of the assembled English text:** `[TITLE] # 806  [TITLE] # SUPREME COURT REPORTS [1959] Supp.  •958 the Punjab Government would have authority to D. s. Ga.ew•I institute the enquiry against him.`

#### 1978 INSC 107: STATE THROUGH DELHI ADMINISTRATION  versus SANJA Y GANDHI

**Canonical judgment**

```json
{
 "judgment_id": "f8dec603-e307-53d9-8358-2fa78c887ae9",
 "vanga_path": "1978_3_950_962",
 "insc_id": "1978 INSC 107",
 "title": "STATE THROUGH DELHI ADMINISTRATION  versus SANJA Y GANDHI",
 "petitioner": "STATE THROUGH DELHI ADMINISTRATION",
 "respondent": "SANJA Y GANDHI",
 "decision_date": "1978-05-05",
 "decision_year": 1978,
 "citation": "[1978] 3 S.C.R. 950",
 "cnr": "ESCR010002141978",
 "disposal": "Case Partly allowed",
 "court": "Supreme Court of India",
 "bench_strength": 1,
 "case_number": null,
 "diary_number": null,
 "pdf_url": null,
 "vanga_year_field": 1978,
 "vaquill_year_field": 1978,
 "vanga_year_folder": 1978,
 "available_languages": [
  "en",
  "hin",
  "pun"
 ],
 "text_status": "english",
 "match_status": "matched",
 "quality_flags": [],
 "vanga_scraped_at": "2025-06-12 21:40:40.977468",
 "build_id": "b2edb7915b851"
}
```

**Raw Vanga** (folder year 1978)

```json
{
 "title": "STATE THROUGH DELHI ADMINISTRATION  versus SANJA Y GANDHI",
 "petitioner": "STATE THROUGH DELHI ADMINISTRATION",
 "respondent": "SANJA Y GANDHI",
 "description": "",
 "judge": "Y.V. CHANDRACHUD",
 "author_judge": null,
 "citation": "[1978] 3 S.C.R. 950",
 "case_id": "1978 INSC 107",
 "cnr": "ESCR010002141978",
 "decision_date": "05-05-1978",
 "disposal_nature": "Case Partly allowed",
 "court": "Supreme Court of India",
 "available_languages": "ENG,HIN,PUN",
 "raw_html": "<4966 chars>",
 "path": "1978_3_950_962",
 "nc_display": "1978INSC107",
 "scraped_at": "2025-06-12T21:40:40.977468",
 "year": "1978",
 "citation_year": "1978"
}
```

**Raw Vaquill** (31 chunk rows)

```json
{"case_id":"1978_INSC_107","title":"STATE THROUGH DELHI ADMINISTRATION  versus SANJA Y GANDHI","petitioner":"STATE THROUGH DELHI ADMINISTRATION","respondent":"SANJA Y GANDHI","disposition":"Case Partly allowed","case_number":"","citation":"[1978] 3 S.C.R. 950","decision_date":"1978-05-05","date_of_registration":"","court":"Supreme Court of India","court_code":"SCI","court_type":"supreme_court","bench":"","bench_strength":1,"judges":["Y.V. CHANDRACHUD"],"description":"","source_url":"","year":1978}
```

**First 160 characters of the assembled English text:** `A  [TITLE] # STATE THROUGH DELHI ADMINISTRATION  l'.  [TITLE] # SANJA Y GANDHI  [TITLE] # May 5, 1978  [Y. V. CHANDRACHUD, C.J., S. MVRTAZA FAZAL Au AND P. N. S`

#### 1974 INSC 34: MOHD. ALAM versus STATE OF WEST BENGAL

**Canonical judgment**

```json
{
 "judgment_id": "0e343c0e-bd45-5ff8-b001-569c09d3549c",
 "vanga_path": "1974_3_379_387",
 "insc_id": "1974 INSC 34",
 "title": "MOHD. ALAM versus STATE OF WEST BENGAL",
 "petitioner": "MOHD. ALAM",
 "respondent": "STATE OF WEST BENGAL",
 "decision_date": "1974-02-14",
 "decision_year": 1974,
 "citation": "[1974] 3 S.C.R. 379",
 "cnr": "ESCR010001961974",
 "disposal": "Case Allowed",
 "court": "Supreme Court of India",
 "bench_strength": 1,
 "case_number": null,
 "diary_number": null,
 "pdf_url": null,
 "vanga_year_field": 1974,
 "vaquill_year_field": 1974,
 "vanga_year_folder": 1974,
 "available_languages": [
  "en",
  "hin",
  "pun"
 ],
 "text_status": "english",
 "match_status": "matched",
 "quality_flags": [],
 "vanga_scraped_at": "2025-06-13 06:33:47.390297",
 "build_id": "b2edb7915b851"
}
```

**Raw Vanga** (folder year 1974)

```json
{
 "title": "MOHD. ALAM versus STATE OF WEST BENGAL",
 "petitioner": "MOHD. ALAM",
 "respondent": "STATE OF WEST BENGAL",
 "description": "",
 "judge": "V.R. KRISHNA IYER",
 "author_judge": null,
 "citation": "[1974] 3 S.C.R. 379",
 "case_id": "1974 INSC 34",
 "cnr": "ESCR010001961974",
 "decision_date": "14-02-1974",
 "disposal_nature": "Case Allowed",
 "court": "Supreme Court of India",
 "available_languages": "ENG,HIN,PUN",
 "raw_html": "<4908 chars>",
 "path": "1974_3_379_387",
 "nc_display": "1974INSC34",
 "scraped_at": "2025-06-13T06:33:47.390297",
 "year": "1974",
 "citation_year": "1974"
}
```

**Raw Vaquill** (22 chunk rows)

```json
{"case_id":"1974_INSC_34","title":"MOHD. ALAM versus STATE OF WEST BENGAL","petitioner":"MOHD. ALAM","respondent":"STATE OF WEST BENGAL","disposition":"Case Allowed","case_number":"","citation":"[1974] 3 S.C.R. 379","decision_date":"1974-02-14","date_of_registration":"","court":"Supreme Court of India","court_code":"SCI","court_type":"supreme_court","bench":"","bench_strength":1,"judges":["V.R. KRISHNA IYER"],"description":"","source_url":"","year":1974}
```

**First 160 characters of the assembled English text:** `A  [TITLE] # MOHD. ALAM  v.  STATE OF WEST BENGAL February 14, 1974  [V. R. KRISHNA IYER AND R. s. SARKARIA, JJ.]  B Prevention detention-' Services and Supplie`

#### 1995 INSC 472: BHAGWANT RAI AND ORS. versus STATE OF PUNJAB AND ORS

**Canonical judgment**

```json
{
 "judgment_id": "bd56e11f-fb92-5dfa-bc77-23573170ee51",
 "vanga_path": "S_1995_2_798_802",
 "insc_id": "1995 INSC 472",
 "title": "BHAGWANT RAI AND ORS. versus STATE OF PUNJAB AND ORS",
 "petitioner": "BHAGWANT RAI AND ORS.",
 "respondent": "STATE OF PUNJAB AND ORS",
 "decision_date": "1995-08-17",
 "decision_year": 1995,
 "citation": "[1995] SUPP. 2 S.C.R. 798",
 "cnr": "ESCR010004751995",
 "disposal": "Appeal(s) allowed",
 "court": "Supreme Court of India",
 "bench_strength": 2,
 "case_number": null,
 "diary_number": null,
 "pdf_url": null,
 "vanga_year_field": 1995,
 "vaquill_year_field": 1995,
 "vanga_year_folder": 1995,
 "available_languages": [
  "en",
  "guj",
  "hin",
  "kan",
  "mal",
  "mar",
  "pun",
  "tam"
 ],
 "text_status": "english",
 "match_status": "matched",
 "quality_flags": [],
 "vanga_scraped_at": "2025-06-13 23:55:51.921830",
 "build_id": "b2edb7915b851"
}
```

**Raw Vanga** (folder year 1995)

```json
{
 "title": "BHAGWANT RAI AND ORS. versus STATE OF PUNJAB AND ORS",
 "petitioner": "BHAGWANT RAI AND ORS.",
 "respondent": "STATE OF PUNJAB AND ORS",
 "description": "",
 "judge": "K. RAMASWAMY, B.L. HANSARIA",
 "author_judge": null,
 "citation": "[1995] SUPP. 2 S.C.R. 798",
 "case_id": "1995 INSC 472",
 "cnr": "ESCR010004751995",
 "decision_date": "17-08-1995",
 "disposal_nature": "Appeal(s) allowed",
 "court": "Supreme Court of India",
 "available_languages": "ENG,GUJ,HIN,KAN,MAL,MAR,PUN,TAM",
 "raw_html": "<5078 chars>",
 "path": "S_1995_2_798_802",
 "nc_display": "1995INSC472",
 "scraped_at": "2025-06-13T23:55:51.921830",
 "year": "1995",
 "citation_year": "1995"
}
```

**Raw Vaquill** (25 chunk rows)

```json
{"case_id":"1995_INSC_472","title":"BHAGWANT RAI AND ORS. versus STATE OF PUNJAB AND ORS","petitioner":"BHAGWANT RAI AND ORS.","respondent":"STATE OF PUNJAB AND ORS","disposition":"Appeal(s) allowed","case_number":"","citation":"[1995] SUPP. 2 S.C.R. 798","decision_date":"1995-08-17","date_of_registration":"","court":"Supreme Court of India","court_code":"SCI","court_type":"supreme_court","bench":"","bench_strength":2,"judges":["K. RAMASWAMY","B.L. HANSARIA"],"description":"","source_url":"","year":1995}
```

**First 160 characters of the assembled English text:** `A  [SECTION] ## BHAGWANT RAI AND ORS.  [SECTION] ## v.  STATE OF PUNJAB AND ORS.-  B  [SECTION] ## AUGUST 17, 1995  (K. RAMASWAMY AND B.L. HANSARIA, JJ.)  The P`

#### 1992 INSC 95: STATE OF U. P. versus HANIF

**Canonical judgment**

```json
{
 "judgment_id": "4d732123-98b6-5b9a-bc30-0cdedaf2aa2b",
 "vanga_path": "1992_2_371_377",
 "insc_id": "1992 INSC 95",
 "title": "STATE OF U. P. versus HANIF",
 "petitioner": "STATE OF U. P.",
 "respondent": "HANIF",
 "decision_date": "1992-03-31",
 "decision_year": 1992,
 "citation": "[1992] 2 S.C.R. 371",
 "cnr": "ESCR010000911992",
 "disposal": "Appeal(s) allowed",
 "court": "Supreme Court of India",
 "bench_strength": 1,
 "case_number": null,
 "diary_number": null,
 "pdf_url": null,
 "vanga_year_field": 1992,
 "vaquill_year_field": 1992,
 "vanga_year_folder": 1992,
 "available_languages": [
  "en",
  "hin",
  "pun"
 ],
 "text_status": "english",
 "match_status": "matched",
 "quality_flags": [],
 "vanga_scraped_at": "2025-06-13 23:42:10.511519",
 "build_id": "b2edb7915b851"
}
```

**Raw Vanga** (folder year 1992)

```json
{
 "title": "STATE OF U. P. versus HANIF",
 "petitioner": "STATE OF U. P.",
 "respondent": "HANIF",
 "description": "",
 "judge": "KULDIP SINGH",
 "author_judge": null,
 "citation": "[1992] 2 S.C.R. 371",
 "case_id": "1992 INSC 95",
 "cnr": "ESCR010000911992",
 "decision_date": "31-03-1992",
 "disposal_nature": "Appeal(s) allowed",
 "court": "Supreme Court of India",
 "available_languages": "ENG,HIN,PUN",
 "raw_html": "<4869 chars>",
 "path": "1992_2_371_377",
 "nc_display": "1992INSC95",
 "scraped_at": "2025-06-13T23:42:10.511519",
 "year": "1992",
 "citation_year": "1992"
}
```

**Raw Vaquill** (15 chunk rows)

```json
{"case_id":"1992_INSC_95","title":"STATE OF U. P. versus HANIF","petitioner":"STATE OF U. P.","respondent":"HANIF","disposition":"Appeal(s) allowed","case_number":"","citation":"[1992] 2 S.C.R. 371","decision_date":"1992-03-31","date_of_registration":"","court":"Supreme Court of India","court_code":"SCI","court_type":"supreme_court","bench":"","bench_strength":1,"judges":["KULDIP SINGH"],"description":"","source_url":"","year":1992}
```

**First 160 characters of the assembled English text:** `[SECTION] ## 'r«~ ~  ).--  --\ I  •  A  [SECTION] ## STATE OF U. P. v. HANIF  [SECTION] ## MARCH 31, 1992  B  [SECTION] ## [KULDIP SINGH AND K. RAMASWAMY, JJ.] `

#### 2015 INSC 271: P. R. YELUMALAI versus N.M. RAVI

**Canonical judgment**

```json
{
 "judgment_id": "6ac2c07f-9b39-5c0c-9442-6d997b749df1",
 "vanga_path": "2015_4_163_176",
 "insc_id": "2015 INSC 271",
 "title": "P. R. YELUMALAI versus N.M. RAVI",
 "petitioner": "P. R. YELUMALAI",
 "respondent": "N.M. RAVI",
 "decision_date": "2015-03-27",
 "decision_year": 2015,
 "citation": "[2015] 4 S.C.R. 163",
 "cnr": "ESCR010004422015",
 "disposal": "Disposed off",
 "court": "Supreme Court of India",
 "bench_strength": 1,
 "case_number": null,
 "diary_number": null,
 "pdf_url": null,
 "vanga_year_field": 2015,
 "vaquill_year_field": 2015,
 "vanga_year_folder": 2015,
 "available_languages": [
  "en",
  "hin",
  "pun",
  "tam"
 ],
 "text_status": "english",
 "match_status": "matched",
 "quality_flags": [],
 "vanga_scraped_at": "2025-06-13 21:47:38.955712",
 "build_id": "b2edb7915b851"
}
```

**Raw Vanga** (folder year 2015)

```json
{
 "title": "P. R. YELUMALAI versus N.M. RAVI",
 "petitioner": "P. R. YELUMALAI",
 "respondent": "N.M. RAVI",
 "description": "",
 "judge": "JASTI CHELAMESWAR",
 "author_judge": null,
 "citation": "[2015] 4 S.C.R. 163",
 "case_id": "2015 INSC 271",
 "cnr": "ESCR010004422015",
 "decision_date": "27-03-2015",
 "disposal_nature": "Disposed off",
 "court": "Supreme Court of India",
 "available_languages": "ENG,HIN,PUN,TAM",
 "raw_html": "<4951 chars>",
 "path": "2015_4_163_176",
 "nc_display": "2015INSC271",
 "scraped_at": "2025-06-13T21:47:38.955712",
 "year": "2015",
 "citation_year": "2015"
}
```

**Raw Vaquill** (27 chunk rows)

```json
{"case_id":"2015_INSC_271","title":"P. R. YELUMALAI versus N.M. RAVI","petitioner":"P. R. YELUMALAI","respondent":"N.M. RAVI","disposition":"Disposed off","case_number":"","citation":"[2015] 4 S.C.R. 163","decision_date":"2015-03-27","date_of_registration":"","court":"Supreme Court of India","court_code":"SCI","court_type":"supreme_court","bench":"","bench_strength":1,"judges":["JASTI CHELAMESWAR"],"description":"","source_url":"","year":2015}
```

**First 160 characters of the assembled English text:** `[2015] 4 S.C.R. 163  [SECTION] ## P. R. YELUMALAI  A  v.  [SECTION] ## N.M. RAVI  B  (Civil Appeal No. 3213 of 2015)  [TITLE] # MARCH 27, 2015  [SECTION] ## [J.`

#### 2015 INSC 865: A. R. DAHIYA versus SEBI

**Canonical judgment**

```json
{
 "judgment_id": "581b2111-0e0b-5ece-be69-be684a6b54ac",
 "vanga_path": "2015_12_202_221",
 "insc_id": "2015 INSC 865",
 "title": "A. R. DAHIYA versus SEBI",
 "petitioner": "A. R. DAHIYA",
 "respondent": "SEBI",
 "decision_date": "2015-11-26",
 "decision_year": 2015,
 "citation": "[2015] 12 S.C.R. 202",
 "cnr": "ESCR010001312015",
 "disposal": "Dismissed",
 "court": "Supreme Court of India",
 "bench_strength": 1,
 "case_number": null,
 "diary_number": null,
 "pdf_url": null,
 "vanga_year_field": 2015,
 "vaquill_year_field": 2015,
 "vanga_year_folder": 2015,
 "available_languages": [
  "en",
  "hin",
  "pun"
 ],
 "text_status": "english",
 "match_status": "matched",
 "quality_flags": [],
 "vanga_scraped_at": "2025-06-13 21:50:50.847062",
 "build_id": "b2edb7915b851"
}
```

**Raw Vanga** (folder year 2015)

```json
{
 "title": "A. R. DAHIYA versus SEBI",
 "petitioner": "A. R. DAHIYA",
 "respondent": "SEBI",
 "description": "",
 "judge": "VIKRAMAJIT SEN",
 "author_judge": null,
 "citation": "[2015] 12 S.C.R. 202",
 "case_id": "2015 INSC 865",
 "cnr": "ESCR010001312015",
 "decision_date": "26-11-2015",
 "disposal_nature": "Dismissed",
 "court": "Supreme Court of India",
 "available_languages": "ENG,HIN,PUN",
 "raw_html": "<4871 chars>",
 "path": "2015_12_202_221",
 "nc_display": "2015INSC865",
 "scraped_at": "2025-06-13T21:50:50.847062",
 "year": "2015",
 "citation_year": "2015"
}
```

**Raw Vaquill** (28 chunk rows)

```json
{"case_id":"2015_INSC_865","title":"A. R. DAHIYA versus SEBI","petitioner":"A. R. DAHIYA","respondent":"SEBI","disposition":"Dismissed","case_number":"","citation":"[2015] 12 S.C.R. 202","decision_date":"2015-11-26","date_of_registration":"","court":"Supreme Court of India","court_code":"SCI","court_type":"supreme_court","bench":"","bench_strength":1,"judges":["VIKRAMAJIT SEN"],"description":"","source_url":"","year":2015}
```

**First 160 characters of the assembled English text:** `[SECTION] ## [2015] 12 S.C.R. 202  [TITLE] # A A. R. DAHIYA  v.  [SECTION] ## SEBI  (Civil Appeal No. 2127 of 2006)  B  [SECTION] ## NOVEMBER 26, 2015  [SECTION`

#### 2024 INSC 836: OM RATHOD versus THE DIRECTOR GENERAL OF HEALTH SERVICES & ORS.

**Canonical judgment**

```json
{
 "judgment_id": "7311d7b6-b422-50b6-b022-8fac6bdb011c",
 "vanga_path": "2024_10_2187_2226",
 "insc_id": "2024 INSC 836",
 "title": "OM RATHOD versus THE DIRECTOR GENERAL OF HEALTH SERVICES & ORS.",
 "petitioner": "OM RATHOD",
 "respondent": "THE DIRECTOR GENERAL OF HEALTH SERVICES & ORS.",
 "decision_date": "2024-10-25",
 "decision_year": 2024,
 "citation": "[2024] 10 S.C.R. 2187",
 "cnr": "ESCR010006632024",
 "disposal": "Appeal(s) allowed",
 "court": "Supreme Court of India",
 "bench_strength": 1,
 "case_number": null,
 "diary_number": null,
 "pdf_url": null,
 "vanga_year_field": 2024,
 "vaquill_year_field": 2024,
 "vanga_year_folder": 2024,
 "available_languages": null,
 "text_status": "english",
 "match_status": "matched",
 "quality_flags": [],
 "vanga_scraped_at": "2025-06-13 11:14:46.850995",
 "build_id": "b2edb7915b851"
}
```

**Raw Vanga** (folder year 2024)

```json
{
 "title": "OM RATHOD versus THE DIRECTOR GENERAL OF HEALTH SERVICES & ORS.",
 "petitioner": "OM RATHOD",
 "respondent": "THE DIRECTOR GENERAL OF HEALTH SERVICES & ORS.",
 "description": "Issue for Consideration Appellant had lower limb myopathy, a locomotor disability. He secured an all India PwD rank of 84 and a State PwD rank of 4 in NEET UG Examination 2024. However, was held ineligible to pursue MBBS course by the designated Medical Board holding that the appellant was 88% disabled which was higher than the maximum permissible disability fixed by the regulation governing admission in the PWD category for MBBS course. By way of the impugned judgment, High Court held that the certification of the degree of disability was in",
 "judge": "D.Y. CHANDRACHUD",
 "author_judge": null,
 "citation": "[2024] 10 S.C.R. 2187",
 "case_id": "2024 INSC 836",
 "cnr": "ESCR010006632024",
 "decision_date": "25-10-2024",
 "disposal_nature": "Appeal(s) allowed",
 "court": "Supreme Court of India",
 "available_languages": "",
 "raw_html": "<2162 chars>",
 "path": "2024_10_2187_2226",
 "nc_display": "2024INSC836",
 "scraped_at": "2025-06-13T11:14:46.850995",
 "year": "2024",
 "citation_year": "2024"
}
```

**Raw Vaquill** (25 chunk rows)

```json
{"case_id":"2024_INSC_836","title":"OM RATHOD versus THE DIRECTOR GENERAL OF HEALTH SERVICES & ORS.","petitioner":"OM RATHOD","respondent":"THE DIRECTOR GENERAL OF HEALTH SERVICES & ORS.","disposition":"Appeal(s) allowed","case_number":"","citation":"[2024] 10 S.C.R. 2187","decision_date":"2024-10-25","date_of_registration":"","court":"Supreme Court of India","court_code":"SCI","court_type":"supreme_court","bench":"","bench_strength":1,"judges":["D.Y. CHANDRACHUD"],"description":"","source_url":"","year":2024}
```

**First 160 characters of the assembled English text:** `[2024] 10 S.C.R. 2187 : 2024 INSC 836  [TITLE] # Om Rathod  [TITLE] # v.  [TITLE] # The Director General of Health Services & Ors.  (Civil Appeal No. 12110 of 2`

#### 2022 INSC 461: DR. JACOB THUDIPARA versus THE STATE OF MADHYA PRADESH & ORS.

**Canonical judgment**

```json
{
 "judgment_id": "6f35a292-5183-5bd7-aaeb-5d575784af52",
 "vanga_path": "2022_3_68_72",
 "insc_id": "2022 INSC 461",
 "title": "DR. JACOB THUDIPARA versus THE STATE OF MADHYA PRADESH & ORS.",
 "petitioner": "DR. JACOB THUDIPARA",
 "respondent": "THE STATE OF MADHYA PRADESH & ORS.",
 "decision_date": "2022-04-21",
 "decision_year": 2022,
 "citation": "[2022] 3 S.C.R. 68",
 "cnr": "ESCR010001032022",
 "disposal": "Appeal(s) allowed",
 "court": "Supreme Court of India",
 "bench_strength": 1,
 "case_number": null,
 "diary_number": null,
 "pdf_url": null,
 "vanga_year_field": 2022,
 "vaquill_year_field": 2022,
 "vanga_year_folder": 2022,
 "available_languages": [
  "en",
  "hin",
  "pun"
 ],
 "text_status": "english",
 "match_status": "matched",
 "quality_flags": [],
 "vanga_scraped_at": "2025-06-13 22:35:23.842680",
 "build_id": "b2edb7915b851"
}
```

**Raw Vanga** (folder year 2022)

```json
{
 "title": "DR. JACOB THUDIPARA versus THE STATE OF MADHYA PRADESH & ORS.",
 "petitioner": "DR. JACOB THUDIPARA",
 "respondent": "THE STATE OF MADHYA PRADESH & ORS.",
 "description": "",
 "judge": "M.R. SHAH",
 "author_judge": null,
 "citation": "[2022] 3 S.C.R. 68",
 "case_id": "2022 INSC 461",
 "cnr": "ESCR010001032022",
 "decision_date": "21-04-2022",
 "disposal_nature": "Appeal(s) allowed",
 "court": "Supreme Court of India",
 "available_languages": "ENG,HIN,PUN",
 "raw_html": "<4912 chars>",
 "path": "2022_3_68_72",
 "nc_display": "2022INSC461",
 "scraped_at": "2025-06-13T22:35:23.842680",
 "year": "2022",
 "citation_year": "2022"
}
```

**Raw Vaquill** (10 chunk rows)

```json
{"case_id":"2022_INSC_461","title":"DR. JACOB THUDIPARA versus THE STATE OF MADHYA PRADESH & ORS.","petitioner":"DR. JACOB THUDIPARA","respondent":"THE STATE OF MADHYA PRADESH & ORS.","disposition":"Appeal(s) allowed","case_number":"","citation":"[2022] 3 S.C.R. 68","decision_date":"2022-04-21","date_of_registration":"","court":"Supreme Court of India","court_code":"SCI","court_type":"supreme_court","bench":"","bench_strength":1,"judges":["M.R. SHAH"],"description":"","source_url":"","year":2022}
```

**First 160 characters of the assembled English text:** `68  [TITLE] # [2022] 3 S.C.R. 68  SUPREME COURT REPORTS  [2022] 3 S.C.R.  A  [SECTION] ## DR. JACOB THUDIPARA  v.  [SECTION] ## THE STATE OF MADHYA PRADESH & OR`

# Schema comparison: Vanga vs Vaquill (Supreme Court)

Generated 2026-10-13 by `pipeline/03_profile_schemas.py` (DuckDB over the untouched files in `raw/`). Regenerate by re-running the script.

## Summary of findings

1. **Vaquill is a subset of Vanga, not a complement.** 37,014 judgments are in both, 1,109 are Vanga-only and **0 are Vaquill-only** (exact `case_id` key, empty keys excluded). Vanga-only decision years: 2025 (456), 2008 (381), 2026 (219), 2006 (51).

2. **Where both have a value they agree almost perfectly** (section 4.4). Vaquill adds **full text, chunk structure and a judges list**; Vanga adds `cnr`, language availability, the raw HTML and the extra judgments. There is little metadata for Vaquill to fill and none for Vanga to fix.

3. **Vanga contains 5,181 duplicate rows** (misfiled copies under the wrong `year=` folder) and **152 rows with an empty `case_id`**. A verified rule picks the right copy.

4. **Vaquill metadata is constant across every case's chunks** (0 exceptions), so one canonical row per `case_id` is safe.

5. **1,418 cases have no English text** in Vaquill (mostly the 2000s).

6. **Not present in either source:** `case_number`, diary number, PDF URL, `author_judge`, `date_of_registration`, `section_priority`. These canonical fields will be empty; they are not merge failures.

7. **Year:** `year` is not the decision year in 23.78% of Vanga rows and 14.51% of Vaquill rows. No decision date is before 1950 or in the future, so the `1902` vs `2002` problem is **not present** in these files.

## 1. Headline facts

|  | Vanga (metadata parquet) | Vaquill (SC judgments) |
|---|---|---|
| grain | one row per metadata record (a judgment) | one row per text **chunk** |
| rows | 43,552 | 1,113,313 |
| columns | 18 | 31 |
| distinct judgments (`case_id`) | 38,124 (distinct `case_id`)  /  38,371 (distinct `path`) | 37,014 |
| json files vs parquet rows | 43,552 JSON files = 43,552 parquet rows | n/a |

## 2. Column profiles

`null %` is SQL NULL; `empty-string %` counts `''` and `[]`. Both mean 'no value'. `~` = approximate distinct count.

### 2.1 Vanga: 43,552 rows

| column | type | null % | empty-string % | distinct | 3 samples |
|---|---|---|---|---|---|
| title | VARCHAR | 0.00% | 0.00% | 38,066 | COMMISSIONER OF INCOME-TAX; MADRAS versus MTT. AR. S. AR. AR ¦ THE STATE OF BOMBAY  AND ANOTHER versus THE UNITED MOTORS (I ¦ SHA MULCHAND & CO. LTD. (IN LIQUIDATION) versus JAWAHAR MILL |
| petitioner | VARCHAR | 0.00% | 0.04% | 31,245 | BASIR-UL-HUQ AND OTHERS ¦ NALINAKHYA BYSACK ¦ SISIR KUMAR DUTTA |
| respondent | VARCHAR | 0.00% | 0.04% | 25,864 | THE STATE OF UTTAR PRADESH AND OTHERS ¦ THE STATE OF WEST BENGAL ¦ RM. N. N. NAGAPPA CHETTIAR |
| description | VARCHAR | 0.00% | 97.30% | 1,156 | • .. Ghaio /!fall 6- So11s v. 1'he Sltde of Delhi ~ Others D ¦ • • • S.C.R. • ~UPREJ\j:E COURT REPORT.S 1403 alienation Cop ¦ • • • • 1350 ~UPREME COURT REPORTS [1959] SALES TAX OFFICER, |
| judge | VARCHAR | 0.00% | 0.04% | 1,729 | M. PATANJALI SASTRI ¦ N. CHANDRASEKHARA AIYAR ¦ MEHR CHAND MAHAJAN, VIVIAN BOSE, B. JAGANNADHADAS |
| author_judge | VARCHAR | 100.00% | 0.00% | 0 |  |
| citation | VARCHAR | 0.00% | 0.00% | 38,371 | [1953] 1 S.C.R. 476 ¦ [1953] 1 S.C.R. 758 ¦ [1953] 1 S.C.R. 533 |
| case_id | VARCHAR | 0.00% | 0.35% | 38,124 | 1953 INSC 50 ¦ 1953 INSC 41 ¦ 1952 INSC 50 |
| cnr | VARCHAR | 0.00% | 0.00% | 38,371 | ESCR010000421953 ¦ ESCR010000061953 ¦ ESCR010000751953 |
| decision_date | VARCHAR | 0.00% | 0.00% | 11,104 | 18-05-1953 ¦ 10-04-1953 ¦ 16-04-1953 |
| disposal_nature | VARCHAR | 0.00% | 2.48% | 32 | Case Partly allowed ¦ Case Allowed ¦ Leave granted |
| court | VARCHAR | 0.00% | 0.00% | 1 | Supreme Court of India |
| available_languages | VARCHAR | 0.00% | 2.70% | 488 | ENG,HIN ¦ ENG,BEN,GUJ,HIN,KAN,MAL,MAR,PUN,TEL,URD ¦ ENG,BEN,HIN,MAL,ORI,PUN,TEL,URD |
| raw_html | VARCHAR | 0.00% | 0.00% | 47,159~ | <select class='form-select form-select-sm me-2' id='language ¦ <button type='button' role='link' class='btn btn-link p-0 te |
| path | VARCHAR | 0.00% | 0.00% | 38,371 | 1953_1_848_864 ¦ 1953_1_708_713 ¦ 1953_1_1169_1183 |
| nc_display | VARCHAR | 0.00% | 0.35% | 38,124 | 1953INSC47 ¦ 1953INSC38 ¦ 1953INSC41 |
| scraped_at | VARCHAR | 0.00% | 0.00% | 43,552 | 2025-06-12T22:11:49.545868 ¦ 2025-06-12T22:11:53.681387 ¦ 2025-06-12T22:11:51.872608 |
| year | VARCHAR | 0.00% | 0.00% | 77 | 1960 ¦ 1962 ¦ 1964 |

### 2.2 Vaquill Supreme Court: 1,113,313 rows

| column | type | null % | empty-string % | distinct | 3 samples |
|---|---|---|---|---|---|
| case_id | VARCHAR | 0.00% | 0.00% | 37,014 | 2023_INSC_200 ¦ 2007_INSC_405 ¦ 1996_INSC_196 |
| chunk_id | VARCHAR | 0.00% | 0.00% | 1,113,313 | 2025_INSC_862_006 ¦ 1990_INSC_176_003 ¦ 2003_INSC_720_002_hin |
| chunk_index | BIGINT | 0.00% | 0.00% | 852 | 1 ¦ 5 ¦ 6 |
| total_chunks | BIGINT | 0.00% | 0.00% | 239 | 5 ¦ 6 ¦ 15 |
| text | VARCHAR | 0.00% | 0.00% | 1,168,898~ | Case: STATE OF MAHARASHTRA THROUGH CBI versus VIKRAM ANANTRA ¦ Case: A. NADAMUNI AND ORS. versus THE PROHIBITION AND EXCISE ¦ Case: STATE OF BIHAR AND ORS. versus CHANDRESHWAR PATHAK [[2 |
| text_original | VARCHAR | 0.00% | 0.00% | 1,168,898~ | Case: M/S. NEW INDIA MOTORS (P) LTD.  NEW DELHI versus K. T. ¦ Case: KASTURI versus IYYAMPERUMAL AND ORS. [[2005] 3 S.C.R.  ¦ Case: MAJOR GENERAL IPS DEWAN versus UNION OF INDIA AND ORS. |
| char_start | BIGINT | 0.00% | 0.00% | 168,007 | 28302 ¦ 2816 ¦ 16263 |
| char_end | BIGINT | 0.00% | 0.00% | 172,106 | 3912 ¦ 7730 ¦ 29312 |
| page_start | BIGINT | 0.00% | 0.00% | 1,311 | 13 ¦ 17 ¦ 21 |
| page_end | BIGINT | 0.00% | 0.00% | 1,318 | 8 ¦ 19 ¦ 41 |
| section_type | VARCHAR | 0.00% | 0.00% | 16 | paragraph ¦ body ¦ judgment |
| section_priority | BIGINT | 100.00% | 0.00% | 0 |  |
| box_aware | BOOLEAN | 0.00% | 0.00% | 2 | true ¦ false |
| court | VARCHAR | 0.00% | 0.00% | 1 | Supreme Court of India |
| court_code | VARCHAR | 0.00% | 0.00% | 1 | SCI |
| court_type | VARCHAR | 0.00% | 0.00% | 1 | supreme_court |
| bench | VARCHAR | 0.00% | 100.00% | 1 |  |
| bench_strength | BIGINT | 0.00% | 0.00% | 9 | 0 ¦ 1 ¦ 5 |
| judges | VARCHAR[] | 0.00% | 0.03% | 1,667 | [ASHOK BHAN] ¦ [ASHOK BHUSHAN] ¦ [RUMA PAL] |
| title | VARCHAR | 0.00% | 0.00% | 36,753 | BIMLESH & ORS. versus NEW INDIA ASSURANCE CO. LTD. ¦ APOORVA SHANTILAL SHAH versus COMMISSIONER OF INCOME TAX  GU ¦ LAXMANRAO BAPURAO JADHAV AND ANR. versus THE STATE OF MAHARA |
| description | VARCHAR | 0.00% | 100.00% | 1 |  |
| petitioner | VARCHAR | 0.00% | 0.07% | 30,193 | COMMISSIONER OF INCOME TAX, PATIALA ¦ RAM NATH MAHTO ¦ CHANDRAKANT UTTAM CHODANKAR |
| respondent | VARCHAR | 0.00% | 0.07% | 25,066 | VIKRAM ANANTRAI DOSHI AND OTHERS ¦ OIL AND NATURAL GAS COMMISSION ¦ KUNISETTY SATYANARAYANA |
| disposition | VARCHAR | 0.00% | 3.16% | 31 | Disposed off ¦ Leave Granted & Dismissed ¦ Matter referred to larger bench |
| case_number | VARCHAR | 0.00% | 100.00% | 1 |  |
| citation | VARCHAR | 0.00% | 0.00% | 37,014 | [1955] 2 S.C.R. 872 ¦ [2006] SUPP. 9 S.C.R. 401 ¦ [2021] 1 S.C.R. 249 |
| decision_date | VARCHAR | 0.00% | 0.00% | 10,879 | 1974-11-12 ¦ 1996-04-10 ¦ 1992-03-31 |
| date_of_registration | VARCHAR | 0.00% | 100.00% | 1 |  |
| year | BIGINT | 0.00% | 0.00% | 76 | 2014 ¦ 2025 ¦ 1975 |
| source_url | VARCHAR | 0.00% | 100.00% | 1 |  |
| language_code | VARCHAR | 0.00% | 0.00% | 16 | ben ¦ tam ¦ pun |

### 2.3 Vaquill central legislation: 74,484 rows (loaded for Phase 2 statute linking)

| column | type | null % | empty-string % | distinct | 3 samples |
|---|---|---|---|---|---|
| act_id | VARCHAR | 0.00% | 0.00% | 1,568 | IND_central_1866 ¦ IND_REP_3277_1968 ¦ IND_REP_813_1866 |
| chunk_id | VARCHAR | 0.00% | 0.00% | 74,484 | IND_central_2435_s142_p4 ¦ IND_REP_2775_1954_s027_5 ¦ IND_central_20099_s050 |
| title | VARCHAR | 0.00% | 0.00% | 1,568 | The Rajiv Gandhi University Act, 2006 ¦ The Calcutta Metro Railway (Operation and Maintenance) Tempo ¦ The Arbitration and Conciliation Act, 1996 |
| chapter | VARCHAR | 0.00% | 39.89% | 124 | III ¦ II ¦ V |
| section_number | VARCHAR | 0.00% | 1.49% | 1,898 | 80 ¦ 142 ¦ 58 |
| section_title | VARCHAR | 0.00% | 0.00% | 1,568 | The Rajiv Gandhi University Act, 2006 ¦ The Calcutta Metro Railway (Operation and Maintenance) Tempo ¦ The Arbitration and Conciliation Act, 1996 |
| text | VARCHAR | 0.00% | 0.00% | 73,468~ | Act: The Oudh Laws Act, 1876 (Act 18 of 1876) \| India \| Cent ¦ Act: The Provisional collection of Taxes Act,2023 (2023) \| I ¦ Act: The Calcutta Metro Railway (Operation and Maintenance)  |
| jurisdiction | VARCHAR | 0.00% | 0.00% | 1 | central |
| state | VARCHAR | 0.00% | 100.00% | 1 |  |
| instrument_type | VARCHAR | 0.00% | 0.00% | 1 | legislation |
| act_status | VARCHAR | 0.00% | 0.00% | 3 | in_force ¦ spent ¦ repealed |
| in_force | BOOLEAN | 0.00% | 0.00% | 2 | true ¦ false |
| doc_type | VARCHAR | 0.00% | 0.00% | 1 | legislation |
| provision_type | VARCHAR | 0.00% | 0.00% | 6 | general ¦ overriding ¦ mandatory |
| section_type | VARCHAR | 0.00% | 0.00% | 10 | amendment_provision ¦ definition_clause ¦ body |
| legal_subject | VARCHAR | 0.00% | 0.00% | 42 | ['tax_law'] ¦ ['family_law'] ¦ ['civil_procedure'] |
| has_proviso | BOOLEAN | 0.00% | 0.00% | 2 | false ¦ true |
| has_non_obstante | BOOLEAN | 0.00% | 0.00% | 2 | false ¦ true |
| delegation_type | VARCHAR | 91.78% | 0.00% | 4 | notification ¦ order ¦ regulations |
| department | VARCHAR | 0.00% | 100.00% | 1 |  |
| regulatory_body | INTEGER | 100.00% | 0.00% | 0 |  |
| acts_referenced | VARCHAR[] | 0.00% | 82.18% | 2,302 | ['Registration Act, 1908'] ¦ ['Aircraft Act, 1934', 'Merchant Shipping Act, 1958', 'Atomi ¦ ['Development Authority Act, 1999', 'Insurance Act, 1938', ' |
| defined_terms | VARCHAR[] | 0.00% | 98.05% | 570 | [declared provision] ¦ [appointed day, board, chairperson, director, fund, general  ¦ [estate officer, premises, prescribed, public premises] |
| amendment_count | BIGINT | 0.00% | 0.00% | 17 | 0 ¦ 17 ¦ 19 |
| year | DOUBLE | 0.01% | 0.00% | 190 | 1996.0 ¦ 1925.0 ¦ 1975.0 |
| source_url | VARCHAR | 0.00% | 0.00% | 850 | https://www.indiacode.nic.in/handle/123456789/19217?view_typ ¦ https://www.indiacode.nic.in/handle/123456789/2087?view_type ¦ https://www.indiacode.nic.in/handle/123456789/1866?view_type |
| language_code | VARCHAR | 0.00% | 0.00% | 1 | en |
| source_publisher | VARCHAR | 0.00% | 0.00% | 1 | Legislative Department, Ministry of Law and Justice (India C |
| mirror_url | VARCHAR | 0.00% | 0.00% | 1,568 | https://oss-data-in.vaquill.ai/legislation/IND_central_1978/ ¦ https://oss-data-in.vaquill.ai/legislation/IND_central_2435/ ¦ https://oss-data-in.vaquill.ai/legislation/IND_central_13053 |

## 3. Join key and overlap (preview only, nothing is merged here)

Vanga `case_id` is an INSC identifier with a space (`1960 INSC 103`); Vaquill `case_id` is the same with an underscore (`1960_INSC_103`). Normalising the space gives an exact key. This is a preview of how far the key alone gets us; the tiered matching in Stage 3 still applies.

|  | judgments |
|---|---|
| in both (exact normalised key) | 37,014 |
| Vanga only | 1,109 |
| Vaquill only | 0 |

By decade of decision date (NULL = no parseable date):

| decade | both | Vanga only | Vaquill only |
|---|---|---|---|
| 1950 | 983 | 0 | 0 |
| 1960 | 3167 | 0 | 0 |
| 1970 | 2928 | 0 | 0 |
| 1980 | 2700 | 0 | 0 |
| 1990 | 6474 | 1 | 0 |
| 2000 | 8650 | 433 | 0 |
| 2010 | 7800 | 0 | 0 |
| 2020 | 4312 | 675 | 0 |

## 4. Field mapping

### 4.1 Same field, possibly different name or format

| concept | Vanga column | Vaquill column | format difference |
|---|---|---|---|
| judgment id (INSC) | `case_id` (`1960 INSC 103`), `nc_display` (`1960INSC103`) | `case_id` (`1960_INSC_103`) | space vs underscore |
| title | `title` | `title` | none expected |
| petitioner / respondent | `petitioner`, `respondent` | `petitioner`, `respondent` | none expected |
| description | `description` | `description` | see profile (mostly empty) |
| decision date | `decision_date` (`DD-MM-YYYY`, string) | `decision_date` (`YYYY-MM-DD`, string) | date format |
| judges | `judge` (comma-separated string) | `judges` (list of strings) and `bench` (string) | string vs list |
| disposal | `disposal_nature` | `disposition` | name |
| report citation | `citation` (`[1960] 3 S.C.R. 880`) | `citation` | none expected |
| court | `court` | `court` | none expected |
| year | `year` (law-report year, **not** decision year) | `year` | see section 6 |
| language | `available_languages` (list of all languages, comma string) | `language_code` (language of this chunk set) | different meaning |

### 4.2 Only in Vanga

| column | note |
|---|---|
| `path` | report key (`1960_3_880_887`); likely also the PDF file key in the S3 `data/` tree (to be confirmed in Stage 8). Not unique (see 6.1) |
| `cnr` | CNR-style identifier (`ESCR...`); one per distinct `path` |
| `author_judge` | **100% NULL**, carries no data |
| `available_languages` | languages the PDF exists in |
| `raw_html` | scraped HTML fragment; contains only a language dropdown and no PDF link (`href='#'`) |
| `nc_display` | compact INSC id |
| `scraped_at` | scrape timestamp |
| JSON only: `citation_year` | present in every JSON file, **absent from the parquet**; keep from the raw JSON |

### 4.3 Only in Vaquill

| column | note |
|---|---|
| `chunk_id`, `chunk_index`, `total_chunks`, `char_start`, `char_end`, `page_start`, `page_end`, `section_type`, `section_priority`, `box_aware` | chunk structure |
| `text`, `text_original` | identical on every row (see 7.4) |
| `bench_strength` | always equals the length of `judges` (checked: 0 exceptions), so it is derived, not independent data |
| `court_code`, `court_type` | court coding |
| `case_number`, `date_of_registration`, `source_url`, `bench`, `description` | **100% empty** in the file, so they cannot fill anything |
| `section_priority` | **100% NULL** |

### 4.4 Fields in both, with measured agreement

Computed on judgments present in both sources. Values are whitespace-collapsed and case-folded; dates are parsed; judges compared as sorted upper-case sets. `agree` = at least one non-empty value matches; `conflict` = both non-empty and none match; `only Vanga` / `only Vaquill` = the other side is empty (this is what filling can recover).

| field | judgments in both | agree | conflict (of comparable) | only Vanga | only Vaquill | both empty |
|---|---|---|---|---|---|---|
| title | 37,014 | 37,014 | 0 (0.00%) | 0 | 0 | 0 |
| petitioner | 37,014 | 37,003 | 0 (0.00%) | 0 | 0 | 11 |
| respondent | 37,014 | 37,003 | 0 (0.00%) | 0 | 0 | 11 |
| description | 37,014 | 0 | 0 (n/a) | 438 | 0 | 36,576 |
| decision_date | 37,014 | 37,014 | 0 (0.00%) | 0 | 0 | 0 |
| citation | 37,014 | 37,014 | 0 (0.00%) | 0 | 0 | 0 |
| disposal / disposition | 37,014 | 36,087 | 0 (0.00%) | 5 | 0 | 922 |
| year | 37,014 | 37,011 | 3 (0.01%) | 0 | 0 | 0 |
| court | 37,014 | 37,014 | 0 (0.00%) | 0 | 0 | 0 |
| judges | 37,014 | 37,000 | 0 (0.00%) | 0 | 0 | 14 |

Example conflicts (key, Vanga value(s), Vaquill value(s)):

- **year**: `1998_INSC_349`: [1996] vs [1998]; `1999_INSC_276`: [1996] vs [1999]; `1999_INSC_312`: [1997] vs [1999]

## 5. Vaquill is chunk-level

- Distinct `case_id` values: **37,014** across 1,113,313 chunk rows (average 30.1 chunks per case).

Chunk sets exist **per language**; the chunk_id carries a language suffix (e.g. `_hin`). A case can therefore have several chunk sets.

| language_code | cases | chunks |
|---|---|---|
| pun | 36,127 | 306,477 |
| en | 35,596 | 371,247 |
| hin | 35,431 | 307,509 |
| ben | 4,973 | 14,825 |
| guj | 4,785 | 27,077 |
| mal | 3,739 | 18,991 |
| tam | 3,661 | 25,264 |
| mar | 3,097 | 16,601 |
| urd | 2,213 | 4,309 |
| tel | 2,198 | 8,002 |
| kan | 2,101 | 6,954 |
| ori | 662 | 3,551 |
| asm | 332 | 957 |
| nep | 171 | 882 |
| san | 55 | 551 |
| kok | 15 | 116 |

Cases with more than one language chunk set: **36,412**.

### 5.1 Is metadata constant across a case's chunks?

| metadata column | cases where it varies across chunks (all languages) | cases where it varies within one language set | example |
|---|---|---|---|
| title | 0 | 0 |  |
| petitioner | 0 | 0 |  |
| respondent | 0 | 0 |  |
| disposition | 0 | 0 |  |
| case_number | 0 | 0 |  |
| citation | 0 | 0 |  |
| decision_date | 0 | 0 |  |
| date_of_registration | 0 | 0 |  |
| year | 0 | 0 |  |
| court | 0 | 0 |  |
| court_code | 0 | 0 |  |
| court_type | 0 | 0 |  |
| bench | 0 | 0 |  |
| bench_strength | 0 | 0 |  |
| judges | 0 | 0 |  |
| description | 0 | 0 |  |
| source_url | 0 | 0 |  |

Cases with **any** of the core metadata columns varying across chunks: **0** of 37,014.

### 5.2 Chunk completeness

Chunk sets (case × language): 135,156. Sets whose row count or max `chunk_index`+1 differs from `total_chunks` (missing or extra chunks): **180**.

Duplicate `chunk_id` values: **0**.

| section_type | chunks |
|---|---|
| body | 554,296 |
| paragraph | 454,820 |
| section | 92,766 |
| conclusion | 7,628 |
| issues | 1,630 |
| header | 446 |
| facts | 435 |
| statutes | 306 |
| arguments | 271 |
| procedure | 224 |
| analysis | 205 |
| precedents | 122 |
| ratio_decidendi | 97 |
| obiter_dicta | 34 |
| relief | 17 |
| judgment | 16 |

## 6. Known upstream issues, tested and quantified

### 6.1 Vanga duplicates and repeated judgments

| measure | value |
|---|---|
| parquet rows | 43,552 |
| distinct `path` | 38,371 |
| distinct non-empty `case_id` | 38,123 |
| distinct `cnr` | 38,371 |
| extra rows (rows − distinct path) | 5,181 |
| `path` values appearing in more than one row | 5,181 (covering 10,362 rows) |
| …of which sit under different `year=` partitions | 5,181 |
| …of which all columns are identical (pure copies) | 476 |
| …of which some column differs | 4,705 |
| columns that differ between the two copies (paths affected) | `available_languages` 562, `raw_html` 4,705, `scraped_at` 5,181 |
| duplicated paths where **exactly one** copy has decision-date year = partition year | 5,181 of 5,181 |
| rows with an **empty** `case_id` (and empty `nc_display`) | 152 rows / 128 paths (matchable to Vaquill on title+date: 0) |
| non-empty `case_id` values mapping to more than one `path` | 96 |
| `case_id` with more than one distinct decision date | 70 |
| `path` with more than one distinct decision date | 0 |

Examples of one `case_id` under several decision dates (id, dates, paths):

| case_id | dates | paths |
|---|---|---|
| 2014_INSC_168 | 2014-03-05 ¦ 2015-08-19 ¦ 2015-09-22 | 2015_9_552_565 ¦ 2014_9_571_779 ¦ 2015_12_769_770 |
| 2014_INSC_182 | 2014-03-12 ¦ 2018-09-14 | 2014_14_279_305 ¦ 2018_11_654_663 |
| 2014_INSC_351 | 2014-04-29 ¦ 2014-04-07 | 2014_5_56_66 ¦ 2014_7_348_370 |
| 2014_INSC_428 | 2016-09-15 ¦ 2014-06-30 | 2016_5_221_226 ¦ 2014_8_32_45 |
| 2014_INSC_479 | 2014-12-18 ¦ 2014-07-08 | 2014_8_228_238 ¦ 2014_13_1343_1361 |

**Dedupe rule (verified):** the second copy of each duplicated `path` is a misfiled copy under the wrong `year=` folder. Keep the copy whose partition year equals the year of its parsed decision date; this picks exactly one copy for every duplicated path.

### 6.2 Wrong or misleading year

Decision year is derived from the **parsed decision date**, never from `year`. Supreme Court first sat 28 Jan 1950, so any date earlier than that, or later than today, is wrong.

| test | Vanga (rows) | Vaquill (case×language rows) |
|---|---|---|
| rows tested | 43,552 | 135,156 |
| decision date missing or unparseable | 0 (0.00%) | 0 (0.00%) |
| decision date before 1950-01-28 | 0 | 0 |
| decision date in the future | 0 | 0 |
| `year` column ≠ `year=` partition folder | 5,181 (11.90%) | n/a (single file) |
| decision-date year ≠ `year=` partition folder | 5,181 (11.90%) | n/a |
| decision-date year ≠ `year` column | 10,358 (23.78%) | 19,612 (14.51%) |
| INSC-id year ≠ decision-date year | 52 (0.12%) | 82 (0.06%) |
| earliest / latest decision date | 1950-03-14 / 2026-09-01 | 1950-03-14 / 2025-11-06 |

Worst Vanga year anomalies (case_id, decision_date, `year`, partition, INSC-id year):

| case_id | decision_date | year | partition | id year |
|---|---|---|---|---|
| 2014 INSC 623 | 25-09-2019 | 2019 | 2019 | 2014 |
| 2019 INSC 372 | 26-11-2015 | 2015 | 2015 | 2019 |
| 2020 INSC 412 | 28-09-2016 | 2016 | 2016 | 2020 |
| 2015 INSC 891 | 08-05-2019 | 2019 | 2019 | 2015 |
| 2014 INSC 182 | 14-09-2018 | 2018 | 2018 | 2014 |
| 2018 INSC 223 | 25-02-2014 | 2014 | 2014 | 2018 |
| 2017 INSC 583 | 22-04-2020 | 2020 | 2020 | 2017 |
| 2019 INSC 1111 | 04-05-2016 | 2016 | 2016 | 2019 |

Worst Vaquill year anomalies (case_id, decision_date, `year`):

| case_id | decision_date | year |
|---|---|---|
| 2014_INSC_623 | 2019-09-25 | 2019 |
| 2015_INSC_891 | 2019-05-08 | 2019 |
| 2014_INSC_182 | 2018-09-14 | 2018 |
| 2017_INSC_583 | 2020-04-22 | 2020 |
| 2017_INSC_64 | 2020-02-19 | 2020 |
| 2017_INSC_265 | 2019-12-05 | 2019 |
| 2018_INSC_216 | 2020-08-05 | 2020 |
| 2018_INSC_332 | 2020-08-31 | 2020 |

### 6.3 Same judgment under more than one decision date

- Vanga: **70** `case_id` values and **0** `path` values carry more than one decision date (examples in 6.1).
- Vaquill: **0** `case_id` values carry more than one decision date.

**What these are:** after applying the dedupe rule from 6.1, Vanga has 38,371 rows for 38,371 distinct paths (one row per path). Of the 96 INSC ids that still map to more than one path, **96 have a different report citation per path** and 70 have different decision dates. These are separate reported judgments (often related proceedings between the same parties, e.g. `2014_INSC_168`) that share one INSC id, not one judgment filed under several dates. Consequences: (1) the INSC id alone is **not** a unique judgment key in Vanga; (2) Vaquill keeps one record per id, so it holds fewer judgments than Vanga's distinct paths; (3) Stage 3 matching must use the INSC id **plus citation** and send any id that still has several candidates to the review queue.

### 6.4 `judis/NNNN.pdf` links needing a `jonew/` prefix

| where searched | `judis/` | `jonew/` | any PDF link |
|---|---|---|---|
| Vanga `raw_html` / `path` | 0 | 0 | 0 |
| Vaquill `source_url` | 0 | 0 | 0 |
| Vaquill chunk `text` (chunks containing the string) | 0 | 0 | n/a |

**Result:** neither source stores a PDF URL. Vanga's only link is `href='#'` and Vaquill `source_url` is empty on every row. The `judis/` → `jonew/` problem therefore cannot occur in the metadata. `pdf_url` has to be derived later from the Vanga `path` and `year` and the S3 `data/` key layout (Stage 8), not copied from the data.

## 7. Other observations that affect the merge design

### 7.1 Fields the prompt expects that are absent

- **diary number:** no column in either source. Not derivable from these files; `judgment.diary_number` stays empty until a source exists.
- **language of the judgment:** Vanga has only the list of available languages; Vaquill has a per-chunk-set `language_code`.
- **bench strength:** Vaquill only. Vanga's `judge` list could give a count; compare in Stage 3.
- **identifier types:** see the citation formats in the profile. SCC and AIR identifiers are checked in the Stage 7 readiness tests.

### 7.2 Judges

Vanga `judge` is a comma-separated string (5,110 rows list more than one judge, 18 rows are empty). Vaquill `judges` is a proper list. Both go into `judgment_judge` one row per judge.

### 7.3 Languages

Vanga `available_languages` example: `ENG,BEN,GUJ,HIN,MAL,MAR,PUN,TEL,URD`. Vaquill stores regional-language chunk sets in the same table, so the unique chunk key is (`case_id`, `language_code`, `chunk_index`) (checked: 0 duplicates), not (`case_id`, `chunk_index`).

### 7.4 `text` vs `text_original`

Chunks where `text` ≠ `text_original`: **0**; identical: **1,113,313**; empty text: **0**. `text_original` is therefore a redundant copy.

Every chunk (1,113,313 of 1,113,313) starts with a `Case: … Section: …` header that Vaquill adds; it is not judgment text and must be stripped before assembling `judgment_text`.

### 7.5 English text coverage in Vaquill

Cases with **no `en` chunk set**: **1,418** of 37,014 (3.83%). They only have translations (`hin`, `pun`, ...). By decade of decision year:

| decade | cases without English text |
|---|---|
| 1950 | 1 |
| 1960 | 3 |
| 1970 | 2 |
| 1980 | 11 |
| 1990 | 20 |
| 2000 | 1320 |
| 2010 | 38 |
| 2020 | 23 |

Script sanity check (share of chunks containing Gurmukhi / Devanagari characters): `en` 0.0% / 0.0%; `hin` 0.0% / 76.3%; `pun` 98.8% / 98.8%. The language labels are trustworthy.

### 7.6 Bench strength

Vaquill `bench_strength` ≠ `len(judges)` in 0 of 135,156 rows. Counting the comma-separated Vanga `judge` string instead disagrees with Vaquill for 24 of 37,024 judgments, so the two sources agree on bench size almost everywhere.

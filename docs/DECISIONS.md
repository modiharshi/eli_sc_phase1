# Decisions

- **2026-10-13 · Localhost, no AWS.** Siddhant asked for no AWS provisioning and no cloud hosting: everything runs on localhost with Docker Compose. Stage 0's VM, HTTPS and S3-backup steps are replaced by local equivalents.
- **Vanga via tar, not 43k JSON objects.** The per-year `metadata.tar` bundles exactly the files in `metadata/json/`. Downloading 77 tars and unpacking them takes under a minute, versus hours for 43,552 small objects. Raw JSON is still kept, unpacked under `raw/vanga/metadata/json/`.
- **Download provenance as a CSV for now.** No database yet, so `docs/manifests/vanga_downloads.csv` holds the `downloads` rows (source, remote path, local path, bytes, sha256, downloaded_at). It loads into the `downloads` table in Stage 4.
- **Vanga `case_id` is the neutral citation, not a case number.** The real case number only exists in `raw_html` (`Case No :`). The canonical `case_number` must come from there.
- **Vanga primary key = `path`.** It is unique per judgment; `nc_display` is not (70 NCs carry two different decision dates).
- **Year = parsed decision date.** The partition year is wrong for the 5,181 judgments duplicated across years.

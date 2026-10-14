"""Stage 5 prerequisites, run after the load and the index step. Idempotent.

  migrate   apply db/migrations/0008_* and later
  role      create the limited write role eli_app (password goes to the git-ignored .env)
  judges    judge + judge_alias from judgment_judge, link judgment_judge.judge_id
  quality   judgment_text_quality for every text (about 135k texts, streamed)
  refresh   refresh the facet materialised views, record the run in pipeline_runs

Usage: 11_derive.py [phase ...]   (no argument = all phases in that order)
"""
import collections
import pathlib
import re
import secrets
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pgconn  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
PHASES = sys.argv[1:] or ["migrate", "role", "judges", "quality", "refresh"]
INDIC = re.compile("[ऀ-෿]")
LETTER = re.compile("[^\\W\\d_]")
GARBAGE = re.compile("[�␀\x00-\x08\x0b\x0c\x0e-\x1f]")


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def migrate(conn):
    cur = conn.cursor()
    for m in sorted((ROOT / "db" / "migrations").glob("00[0-9][0-9]_*.sql")):
        if int(m.name[:4]) >= 8:
            cur.execute(m.read_text())
            log(f"applied {m.name}")
    conn.commit()


def role(conn):
    env = pgconn.env()
    pw = env.get("POSTGRES_APP_PASSWORD")
    if not pw:
        pw = secrets.token_urlsafe(24)
        with open(ROOT / ".env", "a") as f:
            f.write(f"\nPOSTGRES_APP_PASSWORD={pw}\n")
        log("generated POSTGRES_APP_PASSWORD in .env")
    cur = conn.cursor()
    cur.execute("select 1 from pg_roles where rolname='eli_app'")
    if not cur.fetchone():
        cur.execute(f"create role eli_app login password '{pw}' nosuperuser nocreatedb nocreaterole")
    cur.execute("grant usage on schema public to eli_app")
    cur.execute("grant select on all tables in schema public to eli_app")
    cur.execute("revoke insert, update, delete, truncate on all tables in schema public from eli_app")
    writable = ["app_session", "saved_search", "bookmark", "note", "highlight", "error_report", "review_decision",
                "api_usage", "benchmark_result", "benchmark_query", "ai_case_brief", "ai_question_log", "takedown_request",
                "review_audit", "judgment_hidden", "api_key", "match_review_queue", "field_conflicts"]
    for t in writable:
        cur.execute(f"grant insert, select, update, delete on {t} to eli_app")
    cur.execute("grant update (last_login_at) on app_user to eli_app")
    cur.execute("grant insert on app_user to eli_app")
    cur.execute("grant usage, select on all sequences in schema public to eli_app")
    conn.commit()
    log("role eli_app ready")


def judges(conn):
    cur = conn.cursor()
    cur.execute("select judge_name_norm, count(*) from judgment_judge group by 1")
    groups = collections.defaultdict(list)
    for name, n in cur.fetchall():
        groups[re.sub(r"[\s.]", "", name.upper())].append((n, name))
    for key, members in groups.items():
        canonical = max(members)[1]
        cur.execute("insert into judge (canonical_name, alias_key) values (%s, %s) on conflict (alias_key) do nothing", (canonical, key))
    cur.execute("select alias_key, judge_id from judge")
    ids = dict(cur.fetchall())
    for key, members in groups.items():
        for _, name in members:
            cur.execute("insert into judge_alias (alias_name, judge_id) values (%s, %s) on conflict (alias_name) do nothing", (name, ids[key]))
    cur.execute("update judgment_judge g set judge_id = a.judge_id from judge_alias a where a.alias_name = g.judge_name_norm and g.judge_id is distinct from a.judge_id")
    cur.execute("select count(*), count(judge_id) from judgment_judge")
    total, linked = cur.fetchone()
    cur.execute("select count(*) from judge")
    log(f"judges: {cur.fetchone()[0]} judges from {sum(len(m) for m in groups.values())} names; {linked}/{total} rows linked")
    assert total == linked
    conn.commit()


def label(r):
    reasons = []
    en = r["lang"] == "en"
    bad = []
    if r["nul"]:
        bad.append("contains_substituted_nul")
    if r["garbage"] >= 0.01:
        bad.append("garbage_characters>=1%")
    if en and r["nes"] is not None and r["nes"] >= 0.20:
        bad.append("non_latin_share>=20%")
    if r["cpp"] is not None and r["cpp"] < 200:
        bad.append("under_200_chars_per_page")
    if r["chunks"] and r["empty"] / r["chunks"] >= 0.2:
        bad.append("empty_chunks>=20%")
    if bad:
        return "noisy", bad
    if r["garbage"] >= 0.001:
        reasons.append("garbage_characters>=0.1%")
    if en and r["nes"] is not None and r["nes"] >= 0.02:
        reasons.append("non_latin_share>=2%")
    if r["cpp"] is not None and r["cpp"] < 1000:
        reasons.append("under_1000_chars_per_page")
    if not r["complete"]:
        reasons.append("incomplete_text")
    if r["mismatch"]:
        reasons.append("overlap_mismatch")
    if r["drift"]:
        reasons.append("offset_drift")
    return ("fair", reasons) if reasons else ("clean", [])


def quality(conn):
    cur = conn.cursor()
    cur.execute("""select judgment_id, language_code, max(page_end) - min(page_start) + 1, count(*) filter (where char_end <= char_start), count(*)
                   from judgment_chunk group by 1, 2""")
    chunk_stats = {(r[0], r[1]): r[2:] for r in cur.fetchall()}
    cur.execute("""select distinct c.judgment_id, c.language_code from text_sanitization_log l
                   join judgment_chunk c on l.table_name = 'judgment_chunk' and l.row_key = c.vaquill_chunk_id""")
    nul = set(cur.fetchall())
    cur.execute("select table_name, row_key from text_sanitization_log where table_name <> 'judgment_chunk' limit 3")
    log(f"non-chunk sanitisation keys (sample): {cur.fetchall()}")
    log(f"texts with a substituted NUL (via chunks): {len(nul)} texts in {len({j for j, _ in nul})} judgments")
    read = conn.cursor(name="q")
    read.itersize = 200
    read.execute("select judgment_id, language_code, text, char_length, is_complete, overlap_mismatches, offset_drift_chunks from judgment_text")
    ins = conn.cursor()
    rows, n, t0 = [], 0, time.time()
    counts = collections.Counter()
    for jid, lang, text, clen, complete, mismatch, drift in read:
        pages, empty, chunks = chunk_stats.get((jid, lang), (None, 0, 0))
        nes = None
        if lang == "en":
            letters = len(LETTER.findall(text))
            nes = len(INDIC.findall(text)) / letters if letters else 1.0
        r = dict(lang=lang, nul=(jid, lang) in nul, garbage=len(GARBAGE.findall(text)) / max(clen, 1), nes=nes,
                 cpp=(clen / pages) if pages else None, empty=empty, chunks=chunks, complete=complete, mismatch=mismatch, drift=drift)
        lab, reasons = label(r)
        counts[(lang == "en", lab)] += 1
        rows.append((jid, lang, nes, r["garbage"], r["cpp"], empty, lab, reasons))
        n += 1
        if len(rows) >= 2000:
            _flush(ins, rows)
            rows = []
            if n % 20000 == 0:
                log(f"quality {n} texts, {time.time() - t0:.0f}s")
    _flush(ins, rows)
    conn.commit()
    log(f"quality done: {n} texts; (is_english, label) counts: {dict(counts)}")


def _flush(cur, rows):
    cur.executemany("""insert into judgment_text_quality (judgment_id, language_code, non_english_share, garbage_ratio, chars_per_page, empty_chunks, label, reasons)
                       values (%s,%s,%s,%s,%s,%s,%s,%s)
                       on conflict (judgment_id, language_code) do update set non_english_share = excluded.non_english_share,
                         garbage_ratio = excluded.garbage_ratio, chars_per_page = excluded.chars_per_page, empty_chunks = excluded.empty_chunks,
                         label = excluded.label, reasons = excluded.reasons, computed_at = now()""", rows)


def refresh(conn):
    cur = conn.cursor()
    for mv in ["facet_year", "facet_disposition", "facet_bench", "facet_judge", "facet_case_type", "analytics_bench_by_year"]:
        cur.execute(f"refresh materialized view {mv}")
    cur.execute("insert into pipeline_runs (stage, finished_at, status, detail) values ('11_derive', now(), 'succeeded', %s)", (",".join(PHASES),))
    conn.commit()
    log("materialised views refreshed")


if __name__ == "__main__":
    conn = pgconn.connect("admin")
    for p in PHASES:
        log(f"== {p}")
        globals()[p](conn)

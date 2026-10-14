"""Estimate bench size from the header of the English text, e.g.
   (S. M. SIKRI, C. J., J. M. SHELAT, ..., A. K. MUKHERJEA AND Y. V. CHANDRACHUD, JJ.)  ->  13
Reads only text we already hold. Writes judgment_bench_estimate (idempotent) and docs/BENCH_ESTIMATE.md with agreement figures.
Rule (header_regex_v1): first bracketed group in the first 3,000 characters that ends in J. / JJ. / C.J.; remove the Chief Justice
marker, split on commas, AND and &, count fragments with at least two letters; accept 1 to 15."""
import pathlib, re, sys, time, collections
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import pgconn
ROOT = pathlib.Path(__file__).resolve().parent.parent
PAT = re.compile(r"[\(\[]([^()\[\]]{15,700}?)\b(?:JJ|J|CJI|C\.\s?J|C\.J\.I)\.?\s*[\)\]]", re.S)
CJ = re.compile(r"\b(?:ACTING\s+)?C\s*\.?\s*J\s*\.?(?:\s*I\s*\.?)?(?=\s*[,)\]]|\s*$)", re.I)


def estimate(head):
    m = PAT.search(head)
    if not m:
        return None
    body = re.sub(r"\s+", " ", m.group(1))
    body = CJ.sub("", body)
    parts = [p.strip(" ,.;") for p in re.split(r",|\band\b|&", body, flags=re.I)]
    n = sum(1 for p in parts if len(re.findall(r"[A-Za-z]", p)) >= 2)
    return (n, re.sub(r"\s+", " ", m.group(0))[:400]) if 1 <= n <= 15 else None


if __name__ == "__main__":
    conn = pgconn.connect("admin"); cur = conn.cursor(); t0 = time.time()
    cur.execute("select count(*) from judgment_text where language_code = 'en'"); total = cur.fetchone()[0]
    read = conn.cursor(name="r"); read.itersize = 500
    read.execute("select judgment_id, left(text, 3000) from judgment_text where language_code = 'en'")
    rows = []
    for jid, head in read:
        e = estimate(head)
        if e:
            rows.append((jid, e[0], e[1]))
    cur.execute("delete from judgment_bench_estimate")
    cur.executemany("insert into judgment_bench_estimate (judgment_id, judges_in_header, header) values (%s,%s,%s)", rows)
    conn.commit()
    cur.execute("""select count(*), count(*) filter (where e.judges_in_header = j.bench_strength), count(*) filter (where e.judges_in_header > j.bench_strength),
                          count(*) filter (where e.judges_in_header < j.bench_strength) from judgment_bench_estimate e join judgment j using (judgment_id) where j.bench_strength >= 2""")
    both, agree, higher, lower = cur.fetchone()
    cur.execute("select judges_in_header, count(*) from judgment_bench_estimate group by 1 order by 1"); dist = cur.fetchall()
    cur.execute("select (decision_year/10)*10 d, count(*) filter (where e.judgment_id is not null)*100/count(*) from judgment j left join judgment_bench_estimate e using (judgment_id) where text_status='english' group by 1 order by 1"); cov = cur.fetchall()
    out = [f"English texts: {total}; header found and counted for {len(rows)} ({100*len(rows)//total}%) in {time.time()-t0:.0f}s.",
           f"Distribution of header counts: {dict(dist)}",
           f"Coverage by decade (% of English judgments): {dict(cov)}",
           f"Where the source lists 2 or more judges ({both} rows): header count equals the listed count {agree} times, is higher {higher}, is lower {lower}."]
    print("\n".join(out))
    (ROOT / "logs" / "bench_estimate.txt").write_text("\n".join(out))

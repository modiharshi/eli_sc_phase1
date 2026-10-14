"""Stage 4 follow-up: one cheap fix for title_fuzzy (raise pg_trgm.similarity_threshold), re-measured once.
Same method as 09_index_benchmark.py: 100 titles, one typo each, top-20 by similarity, p50/p95 in ms.
Both thresholds are timed in the same run so the comparison is fair. Writes logs/title_fuzzy_check.json."""
import json, pathlib, random, statistics, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import pgconn
ROOT = pathlib.Path(__file__).resolve().parent.parent
random.seed(20241014)
c = pgconn.connect("admin", autocommit=True); cur = c.cursor()
cur.execute("select title from judgment where title is not null order by md5(title) limit 100")
titles = [r[0] for r in cur.fetchall()]
def typo(s):
    i = random.randrange(1, max(2, len(s) - 1)); return s[:i] + s[i + 1:]
queries = [typo(t) for t in titles]
out = {}
for thr in (0.3, 0.4):
    cur.execute(f"set pg_trgm.similarity_threshold = {thr}")
    for q in queries[:5]: cur.execute("select judgment_id from judgment where title %% %s limit 1", (q,)); cur.fetchall()   # warm cache
    ms, hits = [], 0
    for t, q in zip(titles, queries):
        s = time.perf_counter(); cur.execute("select title, similarity(title, %s) s from judgment where title %% %s order by s desc limit 20", (q, q)); rows = cur.fetchall(); ms.append((time.perf_counter() - s) * 1000)
        hits += any(r[0] == t for r in rows)
    ms.sort(); out[str(thr)] = dict(p50=round(statistics.median(ms), 1), p95=round(ms[int(len(ms) * .95) - 1], 1), recall_of_original_title=f"{hits}/{len(titles)}")
print(json.dumps(out, indent=1)); (ROOT / "logs" / "title_fuzzy_check.json").write_text(json.dumps(out, indent=1))

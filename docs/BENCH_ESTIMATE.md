# Bench size: what the sources say and the header estimate

**Finding.** Neither source gives the bench. They list the judge(s) named in the record, which for 91% of judgments is exactly one (usually the first-named or authoring judge). Kesavananda Bharati (1973) lists one judge, S.M. Sikri, although 13 judges sat. So `judgment.bench_strength` (number of judges listed) badly under-counts real benches, and a finder built on it alone cannot find the Constitution Benches it exists for.

**What was done (migration 0009, `pipeline/13_bench_estimate.py`).** The English text we already hold begins with a bench header such as `(S. M. SIKRI, C. J., J. M. SHELAT, … AND Y. V. CHANDRACHUD, JJ.)`. Rule `header_regex_v1`: first bracketed group in the first 3,000 characters ending in J. / JJ. / C.J.; remove the Chief Justice marker; split on commas, AND and &; count fragments with two or more letters; accept 1 to 15. The matched header text is stored with every estimate (`judgment_bench_estimate.header`). `judgment.bench_strength` is not changed; the view `judgment_bench` gives listed, header and effective (the larger of the two) with the basis.

**Results (this build).** Header found for 31,351 of 35,596 English texts (88%); coverage by decade 65 to 96%. Where the source itself lists two or more judges (4,115 rows) the header count equals the listed count 3,738 times (91%), is higher 88 times and lower 289 times. Header counts: 1 judge 1,193; 2 judges 22,528; 3 judges 5,798; 4 judges 456; 5 judges 1,228; 6 judges 76; 7 judges 48; 8 judges 10; 9 judges 11; 11 judges 2; 13 judges 1 (Kesavananda Bharati).

**Hand check.** I read 24 randomly ordered estimates of size 5 or 7 to 9: 23 were right. One was wrong: an OCR comma split “SHRI HARILAJ, KANIA” and gave 7 instead of 6. The estimate is therefore labelled as an estimate everywhere. The 289 “lower than listed” cases have not been examined and are the first place to look for rule errors.

**Not covered.** 12% of English judgments have no readable header; judgments with no English text have no estimate. The `Present:` style used in some older reports is not parsed.

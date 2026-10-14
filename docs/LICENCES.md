# Licences and attribution

Written from the dataset cards fetched on 2026-10-14 (copies are not stored in the repo). **Not legal advice.** Items marked **Check** need your decision.

| Source | Licence as stated by the publisher | Where stated |
|---|---|---|
| Vanga / Dattam Labs, Supreme Court judgments (metadata and PDFs) | Creative Commons Attribution 4.0 (CC-BY-4.0): free to use, share and adapt with appropriate attribution | `README.md` of github.com/vanga/indian-supreme-court-judgments. The repo has no LICENSE file (404). The AWS Open Data Registry page could not be fetched from this environment (proxy denied), so its own terms text was not read. |
| Vaquill / Open India Law, data and compilation | CC BY 4.0 | HF dataset card (`license: cc-by-4.0`) and `data/LICENSE.md` |
| Vaquill scripts | Apache-2.0 | HF dataset card |
| Underlying legal text | Government work, Copyright Act 1957 s.17(d); reproducible under s.52(1)(q). The card says Vaquill holds and grants no rights in it | HF dataset card |

## Commercial use
The Vaquill card says the dataset is free for everyone "including for commercial products, as long as you attribute it". It does not say the Hugging Face gating form adds any further condition; the card's gating text was not part of the file we fetched, and the files downloaded without a token (see `DECISIONS.md` E3). **Check:** accept the conditions on the dataset page yourself and read them once before any public or paid use. I have not decided this for you.

## Attribution text shown in the app footer and on every export
> Judgment data: Vanga / Dattam Labs, *Indian Supreme Court Judgments* (CC BY 4.0), and Vaquill, *Open India Law* (CC BY 4.0). Underlying judgments are Government of India works from the Supreme Court of India / eCourts. This is not the official record; verify against the court's own copy.

## Other points
* The Vaquill card says attribution is a condition imposed by the sources (eCourts and others), which is why it is CC BY and not CC0.
* **Check:** courts have ordered some judgments removed for privacy reasons. The admin "hide judgment" action (`judgment_hidden`) removes a judgment from search, API and exports and keeps an audit record. A public takedown form is deferred until the app is public.
* Vaquill's own table counts 34,954 Supreme Court judgments for its snapshot; our merge uses what the downloaded file contains (see `STAGE3_VALIDATION.md`).

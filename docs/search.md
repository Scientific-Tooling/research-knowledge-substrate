# Local search behavior

`rks search "How does donor replication affect variance?" --mode lexical` ranks
records containing any complete query term. A stored passage no longer has to
contain the entire question as a continuous substring. The CLI, HTTP
`/api/search?q=...&mode=lexical`, repository methods and default hybrid search
use the same shared ranker.

## Modes and response contract

- `lexical`: `bm25-terms-v1`, BM25 with fixed `k1=1.2`, `b=0.75`. Unicode NFKC and
  casefold normalization precede alphanumeric tokenization; underscores and
  punctuation are boundaries. Distinct query terms are OR matched, with no
  stemming, stop-word removal, query rewriting or implicit method switching.
- `phrase`: `literal-phrase-v1`, a case-insensitive, NFKC-normalized literal
  substring within one searchable field. Leading/trailing query whitespace is
  stripped; interior whitespace and punctuation are literal. `%`, `_`, quotes,
  `OR` and `*` have no SQL/full-text-query operator meaning. No term or semantic
  fallback runs after an empty phrase result.
- `hybrid` (default): the ranked lexical groups plus the existing separate
  `semantic_matches` list. Results are not fused into one ranking.
- `semantic`: the existing separate local-hash similarity list, accompanied by
  the same ranked lexical groups. The hash model, 0.2 threshold and global top-ten
  semantic cap remain unchanged. Method/dataset hash candidates retain explicit
  phrase preselection.

The JSON response keeps its `papers`, `claims`, `concepts`, `methods`, `datasets`
and `semantic_matches` arrays, and adds `lexical_retrieval` with method identity,
normalization, ranking, corpus scope, parameters and query policy. Each object
type is ranked independently using all of its live records for BM25 document
frequency and mean length. Scores are summed in sorted query-term order, with
descending BM25 order and ascending stable ID ties. Phrase results use ascending
stable IDs. There is no cross-type lexical result cap. Scores are internal;
rank position is retrieval relevance, not evidence strength or answer confidence.

Blank queries return no lexical matches. Punctuation-only term queries return no
matches. Unsupported modes are rejected (HTTP 400; argparse rejects invalid CLI
choices; `QueryService.search` raises `ValueError`).

## Searchable fields

| Object | Fields |
| --- | --- |
| Paper | Title, abstract, source reference |
| Claim | Text, object text, string context values for `subject_text`, `dataset`, `metric`, `task`, `section`; names/abbreviations/aliases of linked subject and object concepts |
| Concept | Name, canonical abbreviation, aliases |
| Method | Name, description |
| Dataset | Name, description, source |

Fields contribute equally. Claims remain searchable by a linked canonical name
even when their source wording uses a different form. JSON keys, workflow IDs,
evaluation passage identifiers and review metadata are excluded from claim text
ranking. A claim's source quote and provenance are returned without alteration.

## Compatibility and limits

Previously `lexical` used `LIKE '%<entire query>%'` and generally sorted by update
time. Its interpretation and ordering intentionally change. Clients needing a
literal substring should select `phrase`; callers needing enumeration should
use list commands instead of an empty search. Phrase mode also makes `%` and `_`
literal, excludes raw JSON metadata, and uses Unicode casefold rather than SQL
LIKE's case rules. It is not a byte-for-byte recreation of the old SQL behavior.
Term mode matches complete tokens, so a prefix of a word requires phrase mode;
linked concept names/aliases remain available for canonical concept searches.

The portable standard-library implementation scans live records per query and
builds transient term counts. It introduces no persisted derived index, schema
migration, extension dependency or stale-index lifecycle. Cost grows with corpus
text and query length; large-corpus latency has not been qualified. A future
persistent index must retain these versioned semantics and cover import, update,
merge and deletion consistency before replacing this implementation.

Lexical overlap cannot establish entailment, complete answerability, negation,
units or experimental-design correctness. The scRNA-seq starter comparison in
Structured Intelligence uses draft relevance labels; independent scientific
review and newly held-out questions remain necessary. Neither this ranker nor
the unchanged local-hash provider is a validated scientific answering system.

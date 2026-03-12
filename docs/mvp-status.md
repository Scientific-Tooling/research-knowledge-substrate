# MVP Status

## Status

RKS currently meets the core MVP goal:

`paper/reference ingestion -> text artifacts -> structured claims -> concept links -> graph edges -> CLI inspection/query`

The MVP is implemented as a local, inspectable system rather than a production-scale platform.

## Success Criteria Coverage

### 1. Ingest a PDF, DOI, or arXiv paper reference

Status: done

Implemented commands:

- `rks ingest pdf <path>`
- `rks ingest doi <doi>`
- `rks ingest arxiv <id>`

### 2. Persist paper metadata and source artifacts

Status: done

Implemented artifacts include:

- `source_pdf`
- `metadata`
- `extracted_text`
- `sections`
- `claim_candidates`
- `normalized_claims`
- `structured_claims`
- `paper_summary`

### 3. Extract 3 to 10 structured claims from a paper

Status: partially done

The pipeline supports structured claims and often produces multiple claims on suitable input, but the current heuristic extraction quality still depends heavily on source text quality and sentence patterns.

This is functionally sufficient for the MVP, but not yet robust enough for broad real-world paper coverage without LLM assistance.

### 4. Link major terms to normalized concepts

Status: done

Concept normalization and linking are implemented for extracted claims, with stable concept IDs and alias-aware matching.

### 5. Persist graph edges with provenance and confidence

Status: done

Implemented edge types:

- `contains`
- `supported_by`
- `about`

Claim evidence also records extraction mode and section when available.

### 6. Answer a small set of stable CLI queries

Status: done

Implemented commands include:

- `rks claims <paper_id>`
- `rks concepts <paper_id>`
- `rks show claim <claim_id>`
- `rks search <query>`
- `rks query claims-about <concept>`
- `rks query papers-supporting <claim_id>`
- `rks summarize paper <paper_id>`

### 7. Show evidence trails for extracted claims

Status: done

`rks show claim <claim_id>` exposes:

- linked evidence payload
- section-aware provenance
- graph edges connected to the claim

## Dual-Track LLM Requirement

All current LLM-backed tasks follow the dual-track contract:

- `llm-api`
- `agent`

Current covered tasks:

- text extraction
- claim parsing
- paper summarization

See [dual-track-llm-contract.md](/mnt/c/Users/mingz/Codes/research-knowledge-substrate/docs/dual-track-llm-contract.md).

## Known Limitations

- PDF text extraction still uses a lightweight local fallback and is not yet robust on arbitrary scientific PDFs.
- Heuristic claim parsing is intentionally simple and should be treated as a baseline, not a final extractor.
- The graph model currently emphasizes claims and concepts; methods and datasets are not yet extracted as first-class persisted nodes.
- Search is lexical and local, not semantic.
- There is no web UI and no remote service deployment layer.

## Practical Conclusion

The MVP is achieved.

What exists now is a functioning local research substrate with:

- stable IDs
- stable storage
- inspectable artifacts
- repeatable extraction
- dual-track LLM integration
- basic graph querying and reasoning

The next work is quality improvement and expansion, not first-time MVP completion.

# Research Knowledge Substrate: Project Positioning

## What This Project Is

Research Knowledge Substrate (RKS) is an AI-native research knowledge infrastructure.

Its purpose is not to manage papers as files, but to turn research knowledge into structured, machine-operable objects that both researchers and AI agents can query, extend, and reason over.

In RKS, papers are evidence sources. The real system center is the research graph built from claims, methods, datasets, concepts, and their relationships.

## Core Product Definition

RKS is:

- a structured knowledge substrate for research work
- agent-first, with CLI/API style interfaces instead of UI-first workflows
- centered on computable research objects rather than PDF libraries
- designed for traceable reasoning, not just retrieval

RKS is not:

- a Zotero-style reference manager
- a PDF annotation tool
- a generic note-taking app
- a pure vector search system

## Design Goal

The design goal is to build the minimal stable foundation for research knowledge operations.

That foundation should let an agent:

- ingest a paper or corpus
- extract structured claims and methods
- link claims to concepts, datasets, and evidence
- query the resulting graph
- synthesize answers with explicit traceability

The project optimizes first for structural stability and long-term evolvability, not for feature count.

## Core Abstraction

The key abstraction shift is:

`Paper -> Knowledge Node`

Instead of organizing research around documents, RKS organizes it around structured research objects:

- `Paper`
- `Claim`
- `Method`
- `Dataset`
- `Concept`
- optional human or agent `Note`

Among these, `Claim` is the primary knowledge unit because it can be supported, contradicted, refined, compared, and aggregated across papers.

## Why This Exists

Traditional literature tools are stable for storing files and citations, but weak for AI reasoning because:

- tags do not carry strict semantics
- PDFs are not directly computable
- knowledge remains trapped in natural language

RKS exists to provide a substrate where research knowledge becomes:

- structured
- addressable
- linkable
- versionable
- queryable by both graph structure and semantic similarity

## System Shape

RKS is best understood as four coordinated layers:

1. Research objects
2. Research graph
3. Semantic retrieval
4. Reasoning and agent workflows

Typical flow:

`paper -> text extraction -> claim extraction -> concept linking -> graph insertion -> semantic indexing -> reasoning`

## Primary Users

The primary operator is an AI research agent.

The human role is to:

- define research goals
- review outputs
- inspect evidence trails
- correct or extend knowledge when needed

This is an important product decision: the interface should prioritize stable research operations over manual browsing workflows.

## MVP Boundary

The MVP only needs to prove that the substrate model is viable.

That means it should reliably support:

- paper ingestion
- structured claim extraction
- minimal concept normalization
- a small stable research graph
- CLI query and inspection

It does not need to solve every ontology, UX, or automation problem up front.

## Success Criteria

RKS is successful if it becomes a reliable base layer for research tasks such as:

- finding claims about a concept
- tracing evidence for a conclusion
- comparing methods across papers
- identifying contradictions and consensus
- supporting agent-generated research summaries with explicit provenance

In short, RKS should evolve into a research operating substrate, not a document library.

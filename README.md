# Coruscant

Coruscant exists to help every investor understand how geopolitical, economic, climate, and supply-chain events propagate into financial outcomes through explainable reasoning built on public information.

This repository is intentionally documentation-first. The software comes after the operating model, ontology, and reasoning standards are defined.

No code is merged unless the documentation explaining why it exists is merged with it.

## Repository Principles

- Explain rather than predict.
- Make every conclusion traceable to evidence.
- Keep reasoning alongside implementation.
- Prefer modular, maintainable systems over novelty.
- Keep the knowledge model explicit.
- Avoid unnecessary frameworks and hidden behavior.

## Repository Structure

- `docs/` - Core product, governance, and operating documentation.
- `backend/` - Backend application boundary and future service implementation.
- `frontend/` - Frontend application boundary and future interface implementation.
- `graph/` - Knowledge graph modeling, schema, and reasoning support.
- `ingestion/` - Source acquisition, parsing, normalization, and evidence capture.
- `llm/` - Model interfaces, prompts, evaluation, and local LLM experiments.
- `infrastructure/` - Docker, deployment, and environment definitions.
- `experiments/` - Isolated prototypes, research, and disposable investigations.
- `scripts/` - Operational and maintenance scripts.
- `tests/` - Automated verification and quality checks.
- `docker/` - Docker assets and container-related configuration.

## Status

This repository currently contains the foundation for documentation, architecture, and governance only. No application code is included yet.

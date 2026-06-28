# Contributing to Coruscant

Coruscant is a documentation-first and evidence-first project. Contributions should improve clarity, traceability, maintainability, or the quality of the knowledge model.

## Contribution Rules

- Start with the problem, the evidence, and the assumptions.
- Prefer small, reviewable changes.
- Update documentation when behavior, structure, or intent changes.
- No code is merged unless the documentation explaining why it exists is merged with it.
- Do not introduce unnecessary frameworks or abstraction.
- Keep changes aligned with the project mission.

## Suggested Workflow

1. Review the relevant documentation before changing code.
2. Open an issue or document the rationale for significant changes.
3. Make the smallest useful change.
4. Update tests, documentation, and decision logs as needed.
5. Verify the change locally.

## Documentation Expectations

Significant contributions should include updates to:

- relevant README files
- architecture documentation
- decision logs
- assumption register entries

Documentation should explain:

- why the change exists
- what assumptions it encodes
- what trade-offs were accepted
- what evidence supports it

## Code Quality Expectations

- Prefer explicit, readable code.
- Avoid cleverness that harms maintainability.
- Keep dependencies minimal.
- Use deterministic behavior where possible.

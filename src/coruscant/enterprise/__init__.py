"""Enterprise + ecosystem primitives: roles (RBAC), audit log, and API keys.

API keys enable programmatic / third-party access to the public API (the same
endpoints, authenticated by key instead of a session token). SSO, private
deployment, and customer-managed LLMs are configuration seams documented in
ADR-0005.

Boundary: PLATFORM primitive — see docs/PLATFORM.md §7.
"""

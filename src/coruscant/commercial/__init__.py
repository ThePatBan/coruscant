"""Commercial readiness: organizations, plans, billing, and usage analytics.

A v1 multi-tenancy/billing layer: organizations group users, carry a plan with
limits, and aggregate usage. Per-resource tenant isolation (sharing a corpus
across an org) is the documented next step; today resources remain user-scoped
and the org is the management + billing boundary.
"""

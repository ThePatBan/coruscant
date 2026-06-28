"""Authentication: password hashing, signed tokens, and a user store.

Dependency-free (stdlib only) so it runs offline and in tests: PBKDF2-SHA256 for
password hashing and HS256-signed JWT-style tokens.
"""

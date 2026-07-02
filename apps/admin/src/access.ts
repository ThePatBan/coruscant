// The single, pure access decision for the internal admin app. The backend is the
// real authority — every /admin/* route is guarded by `require_admin` (role == "admin",
// see src/coruscant/apps/api.py). This mirror only decides what the shell shows, so it
// stays framework-light and unit-testable (see access.test.ts). It must never be the
// only gate — a non-admin who bypassed it would still be 403'd by the API.

/** The only role the internal admin surfaces are for. Kept in one place. */
export const ADMIN_ROLE = "admin";

/**
 * Whether an authenticated principal may use the internal admin console. A session is
 * required (role is null until /auth/me resolves), and the role must be exactly admin.
 */
export function canAccessAdmin(role: string | null | undefined): boolean {
  return role === ADMIN_ROLE;
}

# Contributing

Keep this project focused on multibody simulation. General finite-element
analysis is outside the current scope.

Run the backend/API tests, the real MBDyn regressions and the browser smoke test
documented in README.md. A UI change needs a reviewed screenshot at desktop and
small-screen sizes. A new physical model needs an independent equation, known
reference or conservation/constraint check, plus an actual MBDyn run. Keep units
visible and declare every idealization.

Validate finite numeric inputs and supported fields before deck generation.
Do not accept arbitrary shell commands or execute user-submitted deck text
through the HTTP API. Keep the service loopback-only. Preserve failed-run logs
and the model snapshot; a reference preview must never replace a failed solve.

Use Python's standard library for the small backend and local browser modules
for the frontend. Keep geometry illustrative unless a mass-property calculation
is explicitly implemented and checked. Reuse the existing CSS tokens, physical
model functions and process boundary. Add dependencies only when they address a
demonstrated need.

Do not commit machine-specific `backend/solver.json`, solver source/build caches,
run data, node_modules or incidental test screenshots. Curated documentation
screenshots should show the actual application and correspond to their examples. Preserve all third-party
notices. If packaging an external solver binary, include the corresponding
source and license required by that solver; the application's MIT license does
not cover it.

# Design search

Design search evaluates a small, explicit grid with the configured MBDyn solver.
It reports the best feasible **evaluated** design. It does not estimate a global
optimum or replace a convergence or hardware check.

1. Solve the current model with MBDyn. In Solve, open **Design search**.
2. Choose one or two numeric inputs and supply two to nine distinct values each.
   At most 25 combinations are allowed. Every candidate is validated before the
   first candidate runs; joint positions, CAD placements and geometry vectors
   are excluded by the existing parameter-study input rules.
3. Choose an objective from the current run's complete CSV, its RMS, peak
   magnitude or final value, and minimize, maximize or match a target. Optionally
   bound one other response, in its displayed units.
4. Run the search. Failed runs and missing/non-finite/incomplete responses cannot
   win. Stop cancels the current owned run and prevents subsequent cases.
5. Export the evaluated table or explicitly apply the best inputs. Applying is
   one Undo step. Run the updated model to inspect its motion and results.

The current model, CAD attachments and baseline result stay intact while cases
run. Applying changes the selected inputs; the previous result becomes stale.
Any intervening project edit disables application of old rankings. Project files
and native autosave retain the search configuration. Evaluated rankings are kept
for the session; export the table to retain them. Candidate native artifacts stay
in the normal run store. A restored baseline requires its embedded full CSV.

For robotics, start with joint stiffness, damping, actuator gains or mass and a
tracking-error, torque or reaction objective. Use physically justified candidate
values and response bounds. A coarse grid can miss better values between samples.

## Verification

Six unit checks cover deterministic grids, overlapping inputs, finite values,
budgets, feasibility, failed/incomplete responses, stable ties, CSV export and
response identifiers. `npm run test:design` also drives the real browser controls
against an isolated native MBDyn service. Six actual two-input candidates plus
their baseline are solved. Independently integrated full-CSV RMS values agree
with all six displayed results; 8 N·s/m damping and 0.8 kg win this illustrative
sample set (0.0471842 m RMS). The check verifies explicit Apply/Undo/Redo, exact
baseline CSV preservation, configuration save/reopen, oversized-grid rejection
before solver calls, and token cancellation with no later cases. No live model
provider or Computer Use is involved.

The graphical checks write their report and reviewed screenshots to
`tests/evidence/design-search.json` and `tests/evidence/design-search.png`.

# Design backlog

This document records deferred product-design simplifications. Items here are
not committed roadmap work and should be revalidated against the current UI and
API before implementation.

## Collection-native analysis control

**Priority:** Low
**Status:** Implemented; pending release

Evolve the existing collection Analyze action so eligibility and confirmation
are native to the parent collection surface and follow the app's Material 3
Expressive interaction language. This is deliberately not a new control or a
new lifecycle concept. `CollectionsWorkspace` previously moved eligibility,
confirmation, and queueing into a detached bulk-action modal; the selected
direction keeps that context inline.

The collection-level expressive action surface should show, without leaving the
collection context:

- how many members are source-ready, already analyzed, eligible, or blocked;
- the exact work that will be queued and why other members are excluded;
- a compact confirmation step when queueing meaningful work; and
- an explicit guarantee that existing graph output will not be regenerated.

Active run progress and member-level recovery may be considered later, but are
not part of this focused simplification.

Treat this as a simplification project, not as an additional analysis workflow.
The implementation should converge collection analysis on one canonical
eligibility and queueing contract, then remove redundant client state and API
paths where compatibility permits. It must preserve the current safety rule:
normal Generate analyzes only source-backed companies without completed graph
output. Full reanalysis must remain a separate, explicit intent.

The selected interaction was validated at desktop, tablet, and compact widths,
including keyboard-readable button/group semantics and zero-eligible behavior.
Success means fewer concepts and transitions for the user, less duplicated
orchestration in the codebase, and no change to which companies are analyzed
without explicit user intent.

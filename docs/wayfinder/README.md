# Local Wayfinder Tracker

This directory is the local issue tracker for the MedicalRAG Wayfinder map.

- `map.md` is the single canonical map and carries the `wayfinder:map` label.
- `tickets/` contains child decision tickets.
- A ticket is available when `status: open`, it has no `assignee`, and every path in `depends_on` points to a closed ticket.
- Ticket titles are the human-facing identity. Filenames are only local storage paths.
- `wayfinder:grilling` tickets are resolved through one-at-a-time discussion; `wayfinder:research` tickets require primary-source research; `wayfinder:task` tickets are preparatory work that unblocks a decision.

The map is an index. Detailed decisions belong in their ticket and, where appropriate, in the related ADR or research note.

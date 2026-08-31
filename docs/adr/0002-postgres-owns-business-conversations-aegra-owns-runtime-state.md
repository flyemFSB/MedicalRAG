---
status: accepted
---

# PostgreSQL owns business conversations and Aegra owns runtime state

PostgreSQL is the source of truth for users, permissions, Conversations, Messages, Evidence, Feedback, and medical business metadata. Aegra is the source of truth for production Thread execution, checkpoints, worker leases, Run recovery, and Agent Protocol stream state. The two systems are linked by persisted `aegra_thread_id` and `aegra_run_id` values, but neither system is allowed to replace the other's ownership. This split keeps clinical records queryable and permission-scoped in the application database while allowing Aegra to evolve its runtime storage and recovery protocol independently.

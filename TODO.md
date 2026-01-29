# Procast AI - Next Tasks

- [ ] Cache data session management (define cache scope by user/session, set `DSPY_CACHEDIR` strategy, document cache cleanup)
- [ ] SQL scope control (implement plan in `.cursor/plans/sql_scope_control_implementation_91514c0c.plan.md`)
- [ ] Add scoped DB session using user context for RLS policies
- [ ] Wire user context through agent pipeline to DB query execution
- [ ] Add audit logging for SQL execution with user context
- [ ] Write integration tests verifying scoped access

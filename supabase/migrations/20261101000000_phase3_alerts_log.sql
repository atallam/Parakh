-- Phase 3: the alert delivery log, including alerts that were suppressed or shadowed (plan 10 §13).
-- Append-only like the audit tables: a decision is never edited after the fact.

create table public.alerts_log (
  alert_id         text primary key,
  run_id           text references public.runs (run_id),
  asof             date not null,
  isin             text,
  symbol           text,
  code             text not null,   -- signal or rule id, e.g. M21, E03, THESIS.BROKEN, SYS.HEARTBEAT
  kind             text not null,
  severity         text not null check (severity in ('High', 'Medium', 'Low')),
  source           text not null,   -- watcher | events | monthly | agent | system
  decision         text not null
                   check (decision in ('sent', 'shadow', 'suppressed', 'failed', 'digest', 'digest_sent', 'digest_failed')),
  reason           text not null default '',
  payload_hash     text not null,
  channel          text,
  delivery_status  text,
  provider_msg_id  text,
  ts_utc           timestamptz not null default now()
);
create index alerts_log_code_idx on public.alerts_log (code, asof);
create index alerts_log_isin_idx on public.alerts_log (isin, asof);

create trigger alerts_log_append_only before update or delete on public.alerts_log
  for each row execute function public.reject_mutation();

alter table public.alerts_log enable row level security;
revoke all on public.alerts_log from anon, authenticated;
grant select on public.alerts_log to parakh_mcp, parakh_staging;
create policy mcp_read     on public.alerts_log for select to parakh_mcp     using (true);
create policy staging_read on public.alerts_log for select to parakh_staging using (true);

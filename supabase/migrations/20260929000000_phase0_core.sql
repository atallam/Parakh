-- Parakh Phase 0 core schema (plan 09 Phase 0: "migrations + RLS skeleton").
-- Sources: plan 05 §3.4 (securities), plan 10 §4.2 and §13 (audit, runs, steps, MCP tables),
-- plan 15 §4.1 (parakh_mcp role), plan 14 §3 / plan 13 D17 (staging schema and role).
-- Holdings, prices, fundamentals and the other operational tables arrive in Phase 1.

-- ---------------------------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------------------------
create or replace function public.reject_mutation() returns trigger
language plpgsql as $$
begin
  raise exception '% is append-only: % rejected (plan 10 §4.2; corrections are new events)',
    tg_table_name, tg_op
    using errcode = '42501';
end;
$$;

-- ---------------------------------------------------------------------------------------------
-- Securities (keyed on ISIN, never deleted: survivorship, plan 04 §4 #5)
-- ---------------------------------------------------------------------------------------------
create table public.securities (
  isin          text primary key check (isin ~ '^[A-Z]{2}[A-Z0-9]{9}[0-9]$'),
  symbol        text not null,
  name          text not null,
  sector        text,
  industry      text,
  listing_date  date,
  status        text not null default 'active'
                check (status in ('active', 'suspended', 'delisted', 'merged')),
  created_at    timestamptz not null default now()
);
create unique index securities_active_symbol on public.securities (symbol) where status = 'active';
create trigger securities_no_delete before delete on public.securities
  for each row execute function public.reject_mutation();

create table public.symbol_history (
  isin        text not null references public.securities (isin),
  symbol      text not null,
  valid_from  date not null,
  valid_to    date,
  primary key (isin, valid_from)
);

-- ---------------------------------------------------------------------------------------------
-- Runs and the step ledger (plan 10 §5, §13)
-- ---------------------------------------------------------------------------------------------
create table public.runs (
  run_id             text primary key check (run_id ~ '^[0-9A-HJKMNP-TV-Z]{26}$'),
  mode               text not null,
  env                text not null check (env in ('dev', 'test', 'staging', 'prod')),
  asof               date not null,
  trigger_type       text not null,
  triggered_by       text not null,
  started_at         timestamptz not null,
  finished_at        timestamptz,
  status             text not null check (status in (
                       'RUNNING', 'SUCCESS', 'SUCCESS_AUDIT_PENDING', 'FAILED', 'INVALIDATED')),
  code_version       text not null,
  config_hash        text not null,
  framework_version  text not null,
  lens_versions      jsonb not null default '{}',
  prompt_versions    jsonb not null default '{}',
  dq_score           numeric,
  llm_tokens         integer not null default 0,
  llm_cost_inr       numeric not null default 0,
  audit_chain_head   text
);

create table public.run_steps (
  step_id        text primary key,
  run_id         text not null references public.runs (run_id),
  name           text not null,
  seq            integer not null,
  started_at     timestamptz not null,
  ended_at       timestamptz,
  status         text not null check (status in ('running', 'ok', 'failed')),
  input_hashes   jsonb not null default '{}',
  output_hashes  jsonb not null default '{}',
  rows_in        integer,
  rows_out       integer,
  error          text
);
create index run_steps_run on public.run_steps (run_id, seq);

-- ---------------------------------------------------------------------------------------------
-- Audit events: append-only and hash-chained (ADR-007; AC-F21.3)
-- ---------------------------------------------------------------------------------------------
create table public.audit_events (
  event_id           text primary key,
  event_type         text not null check (event_type ~ '^AUD\.[A-Z_]+(\.[A-Z_]+)?$'),
  ts_utc             timestamptz not null,
  trading_date_ist   date not null,
  run_id             text,
  step_id            text,
  actor_type         text not null,
  actor_id           text not null,
  channel            text,
  entity_type        text,
  entity_id          text,
  isin               text,
  action             text,
  before             jsonb,
  after              jsonb,
  reason             text,
  evidence_ref       text,
  details            jsonb not null default '{}',
  code_version       text not null,
  config_hash        text not null,
  framework_version  text not null,
  prev_hash          text not null,
  record_hash        text not null unique,
  synced_at          timestamptz not null default now()
);
create index audit_events_run on public.audit_events (run_id);
create index audit_events_type_ts on public.audit_events (event_type, ts_utc);
create index audit_events_isin on public.audit_events (isin) where isin is not null;
create trigger audit_events_append_only before update or delete on public.audit_events
  for each row execute function public.reject_mutation();
create trigger audit_events_no_truncate before truncate on public.audit_events
  for each statement execute function public.reject_mutation();

-- ---------------------------------------------------------------------------------------------
-- MCP and agent tables (plan 10 §13, plan 15 §4.1)
-- ---------------------------------------------------------------------------------------------
create table public.mcp_tool_calls (
  mcp_call_id    text primary key,
  run_id         text,
  agent_run_id   text,
  client         text not null,
  tool_id        text not null check (tool_id ~ '^TOOL\.[a-z]+\.[a-z0-9_]+$'),
  tier           text not null check (tier in ('R', 'P', 'N', 'J')),
  args_hash      text not null,
  result_hash    text,
  masked         boolean not null default false,
  status         text not null,
  latency_ms     numeric,
  ts_utc         timestamptz not null default now()
);
create trigger mcp_tool_calls_append_only before update or delete on public.mcp_tool_calls
  for each row execute function public.reject_mutation();

create table public.proposals (
  proposal_id    text primary key,
  kind           text not null check (kind in ('watchlist', 'thesis_flag', 'journal')),
  isin           text references public.securities (isin),
  payload        jsonb not null,
  reason         text not null,
  evidence_refs  jsonb not null default '[]',
  agent_run_id   text,
  status         text not null default 'pending'
                 check (status in ('pending', 'approved', 'rejected', 'snoozed', 'expired')),
  decided_by     text,
  decided_at     timestamptz,
  expires_at     timestamptz,
  created_at     timestamptz not null default now()
);

create table public.notify_queue (
  item_id        text primary key,
  agent_run_id   text,
  template_id    text not null,
  isin           text,
  severity       text not null check (severity in ('High', 'Medium', 'Low')),
  dedupe_key     text not null,
  vars           jsonb not null default '{}',
  status         text not null default 'queued'
                 check (status in ('queued', 'sent', 'suppressed', 'failed')),
  created_at     timestamptz not null default now()
);

create table public.job_requests (
  item_id        text primary key,
  agent_run_id   text,
  kind           text not null,
  isin           text,
  reason_code    text not null,
  status         text not null default 'queued'
                 check (status in ('queued', 'running', 'done', 'refused')),
  created_at     timestamptz not null default now()
);

-- ---------------------------------------------------------------------------------------------
-- Row-level security: on for every table; nothing is readable by anon or authenticated
-- ---------------------------------------------------------------------------------------------
alter table public.securities      enable row level security;
alter table public.symbol_history  enable row level security;
alter table public.runs            enable row level security;
alter table public.run_steps       enable row level security;
alter table public.audit_events    enable row level security;
alter table public.mcp_tool_calls  enable row level security;
alter table public.proposals       enable row level security;
alter table public.notify_queue    enable row level security;
alter table public.job_requests    enable row level security;

revoke all on all tables in schema public from anon, authenticated;
alter default privileges in schema public revoke all on tables from anon, authenticated;

-- ---------------------------------------------------------------------------------------------
-- parakh_mcp: what the MCP server connects as (plan 15 §4.1; AC-F24.5)
-- SELECT on read models; INSERT only on proposals, queues and the audit tables; never UPDATE
-- or DELETE. Login and password are set by hand in the dashboard, never in a migration.
-- ---------------------------------------------------------------------------------------------
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'parakh_mcp') then
    create role parakh_mcp nologin;
  end if;
end $$;
grant usage on schema public to parakh_mcp;
grant select on public.securities, public.symbol_history, public.runs, public.run_steps,
  public.audit_events, public.proposals to parakh_mcp;
grant insert on public.proposals, public.notify_queue, public.job_requests,
  public.audit_events, public.mcp_tool_calls to parakh_mcp;

create policy mcp_read on public.securities     for select to parakh_mcp using (true);
create policy mcp_read on public.symbol_history for select to parakh_mcp using (true);
create policy mcp_read on public.runs           for select to parakh_mcp using (true);
create policy mcp_read on public.run_steps      for select to parakh_mcp using (true);
create policy mcp_read on public.audit_events   for select to parakh_mcp using (true);
create policy mcp_read on public.proposals      for select to parakh_mcp using (true);
create policy mcp_insert on public.proposals      for insert to parakh_mcp with check (status = 'pending');
create policy mcp_insert on public.notify_queue   for insert to parakh_mcp with check (status = 'queued');
create policy mcp_insert on public.job_requests   for insert to parakh_mcp with check (status = 'queued');
create policy mcp_insert on public.audit_events   for insert to parakh_mcp with check (true);
create policy mcp_insert on public.mcp_tool_calls for insert to parakh_mcp with check (true);

-- ---------------------------------------------------------------------------------------------
-- Staging / shadow environment (plan 13 D17): its own schema and a role that can't write public
-- ---------------------------------------------------------------------------------------------
create schema if not exists staging;
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'parakh_staging') then
    create role parakh_staging nologin;
  end if;
end $$;
revoke all on schema staging from public;
grant usage, create on schema staging to parakh_staging;
alter default privileges in schema staging grant all on tables to parakh_staging;
grant usage on schema public to parakh_staging;
grant select on public.securities, public.symbol_history to parakh_staging;
create policy staging_read on public.securities     for select to parakh_staging using (true);
create policy staging_read on public.symbol_history for select to parakh_staging using (true);

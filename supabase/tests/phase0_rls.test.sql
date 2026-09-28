-- pgTAP checks for the Phase 0 schema (plan 14 L4). Run with `supabase test db`.
-- Role checks use has_table_privilege, so the test never needs to switch roles.
begin;
select plan(16);

insert into public.runs (run_id, mode, env, asof, trigger_type, triggered_by, started_at, status,
  code_version, config_hash, framework_version)
values ('01K0000000000000000000TEST', 'dummy', 'test', '2026-09-30', 'manual', 'ci:github', now(),
  'SUCCESS', 'test', 'sha256:test', '0.1.0');
insert into public.audit_events (event_id, event_type, ts_utc, trading_date_ist, run_id, actor_type,
  actor_id, code_version, config_hash, framework_version, prev_hash, record_hash)
values ('01K0000000000000000000EVT1', 'AUD.RUN.START', now(), current_date,
  '01K0000000000000000000TEST', 'ci', 'github', 'test', 'sha256:test', '0.1.0', 'sha256:0', 'sha256:1');

-- AC-F21.3: audit_events is append-only, even for the owner role
select throws_ok($$update public.audit_events set reason = 'x'$$, '42501', null, 'audit_events rejects UPDATE');
select throws_ok($$delete from public.audit_events$$, '42501', null, 'audit_events rejects DELETE');
select throws_ok($$truncate public.audit_events$$, '42501', null, 'audit_events rejects TRUNCATE');
select throws_ok($$delete from public.securities$$, '42501', null, 'securities are never deleted');

-- the pilot seed is present and keyed by ISIN
select is((select count(*)::int from public.securities), 7, 'seven pilot securities seeded');
select is((select symbol from public.securities where isin = 'INE101A01026'), 'M&M', 'M&M keyed by ISIN');

-- AC-F24.5: parakh_mcp reads and proposes, never updates or deletes
select ok(has_table_privilege('parakh_mcp', 'public.runs', 'SELECT'), 'parakh_mcp can read runs');
select ok(has_table_privilege('parakh_mcp', 'public.proposals', 'INSERT'), 'parakh_mcp can insert proposals');
select ok(not has_table_privilege('parakh_mcp', 'public.proposals', 'UPDATE'), 'parakh_mcp cannot approve (UPDATE)');
select ok(not has_table_privilege('parakh_mcp', 'public.runs', 'INSERT'), 'parakh_mcp cannot write runs');
select is(
  (select count(*)::int from information_schema.role_table_grants
    where grantee = 'parakh_mcp' and privilege_type in ('UPDATE', 'DELETE', 'TRUNCATE')),
  0, 'parakh_mcp holds no UPDATE, DELETE or TRUNCATE grant anywhere');

-- RLS is on everywhere; anon and authenticated see nothing
select is(
  (select count(*)::int from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity),
  0, 'row-level security enabled on every public table');
select ok(not has_table_privilege('anon', 'public.securities', 'SELECT'), 'anon cannot read securities');
select ok(not has_table_privilege('authenticated', 'public.audit_events', 'SELECT'), 'authenticated cannot read audit');

-- staging role (D17): its own schema, can't write public
select ok(has_schema_privilege('parakh_staging', 'staging', 'CREATE'), 'staging role owns its schema');
select ok(not has_table_privilege('parakh_staging', 'public.securities', 'INSERT'), 'staging role cannot write public');

select * from finish();
rollback;

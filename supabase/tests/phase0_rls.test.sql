-- pgTAP checks for the Phase 0 schema (plan 14 L4). Run with `supabase test db`.
begin;
select plan(12);

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
set local role parakh_mcp;
select lives_ok($$select * from public.runs$$, 'parakh_mcp can read runs');
select lives_ok($$insert into public.proposals (proposal_id, kind, payload, reason)
  values ('p1', 'journal', '{}', 'test')$$, 'parakh_mcp can insert a pending proposal');
select throws_ok($$update public.proposals set status = 'approved'$$, '42501', null,
  'parakh_mcp cannot approve (UPDATE)');
select throws_ok($$insert into public.runs (run_id, mode, env, asof, trigger_type, triggered_by,
  started_at, status, code_version, config_hash, framework_version) values
  ('01K0000000000000000000TST2', 'x', 'test', current_date, 'm', 'x', now(), 'SUCCESS', 'x', 'x', 'x')$$,
  '42501', null, 'parakh_mcp cannot write runs');
reset role;

-- anon sees nothing; the staging role can't write public (D17)
set local role anon;
select throws_ok($$select * from public.securities$$, '42501', null, 'anon cannot read securities');
reset role;
set local role parakh_staging;
select throws_ok($$insert into public.securities (isin, symbol, name) values ('INE000000000', 'X', 'X')$$,
  '42501', null, 'staging role cannot write public');
reset role;

select * from finish();
rollback;

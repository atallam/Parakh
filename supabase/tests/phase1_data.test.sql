-- pgTAP checks for the Phase 1 schema (plan 14 L4). Run with `supabase test db`.
-- Role checks use has_table_privilege, so the test never needs to switch roles.
begin;
select plan(18);

-- seeds: source registry and the MAZDOCK split
select ok((select count(*) from public.sources) >= 9, 'source registry seeded');
select is((select new_isin from public.isin_history where old_isin = 'INE249Z01012'),
  'INE249Z01020', 'MAZDOCK pre-split ISIN resolves to the current one');

-- fundamentals are bitemporal and append-only (corrections are new versions)
insert into public.fundamentals (isin, metric_id, period_type, period_end, value, unit, source_id, raw_hash)
values ('INE101A01026', 'annual_pl.Sales', 'annual', '2026-03-31', 1.0, 'cr', 'screener_export', 'sha256:t');
select throws_ok($$update public.fundamentals set value = 2$$, '42501', null, 'fundamentals reject UPDATE');
select throws_ok($$delete from public.fundamentals$$, '42501', null, 'fundamentals reject DELETE');
select lives_ok($$insert into public.fundamentals (isin, metric_id, period_type, period_end, value,
  unit, source_id, raw_hash, version) values ('INE101A01026', 'annual_pl.Sales', 'annual',
  '2026-03-31', 2.0, 'cr', 'screener_export', 'sha256:t2', 2)$$, 'a correction is a new version');
select throws_ok($$insert into public.fundamentals (isin, metric_id, period_type, period_end, value,
  unit, source_id, raw_hash) values ('INE101A01026', 'x', 'annual', '2026-03-31', 1, 'cr',
  'no_such_source', 'h')$$, '23503', null, 'every value names a registered source');

-- holdings: account references only, never a DP or client ID (P6, AC-F03.7)
insert into public.holdings_lots (lot_id, account_ref, isin, qty, trade_date, settle_date, price_inr, source)
values ('01K00000000000000000000AB1', 'acct_0123456789ab', 'INE101A01026', 10, '2026-08-31',
  '2026-09-01', 3000, 'broker_pnl');
select throws_ok($$insert into public.holdings_lots (lot_id, account_ref, isin, qty, trade_date,
  settle_date, source) values ('01K00000000000000000000AB2', 'IN30000010000001', 'INE101A01026', 1,
  '2026-09-01', '2026-09-02', 'cli')$$, '23514', null, 'a DP/client ID is refused as an account reference');
select lives_ok($$insert into public.holdings_lots (lot_id, account_ref, isin, qty, trade_date,
  settle_date, price_inr, source) values ('01K00000000000000000000AB3', 'acct_0123456789ab',
  'INE101A01026', 5, '2026-09-30', '2026-10-01', null, 'cas_prompt')$$,
  'a cost-pending lot has no price (AC-F03.6)');
select throws_ok($$insert into public.holdings_lots (lot_id, account_ref, isin, qty, trade_date,
  settle_date, source) values ('01K00000000000000000000AB4', 'acct_0123456789ab', 'INE101A01026', 1,
  '2026-09-02', '2026-09-01', 'cli')$$, '23514', null, 'settlement never precedes the trade');
insert into public.transactions (txn_id, lot_id, account_ref, isin, side, qty, price_inr, trade_date, source)
values ('01K00000000000000000000CD1', '01K00000000000000000000AB1', 'acct_0123456789ab',
  'INE101A01026', 'buy', 10, 3000, '2026-08-31', 'broker_pnl');
select throws_ok($$delete from public.transactions$$, '42501', null, 'transactions are append-only');
insert into public.cas_statements (statement_id, file_sha256, file_type, period_from, period_to)
values ('stmt-test', 'sha256:cas', 'NSDL', '2026-08-01', '2026-08-31');
insert into public.cas_positions (statement_id, account_ref, isin, kind, qty)
values ('stmt-test', 'acct_0123456789ab', 'INE101A01026', 'equity', 10);
select throws_ok($$update public.cas_positions set qty = 1$$, '42501', null, 'CAS positions are append-only');

-- parakh_mcp reads market data, never holdings (plan 15 AG-07)
select ok(has_table_privilege('parakh_mcp', 'public.fundamentals', 'SELECT'), 'parakh_mcp reads fundamentals');
select ok(has_table_privilege('parakh_mcp', 'public.isin_history', 'SELECT'), 'parakh_mcp reads isin_history');
select ok(not has_table_privilege('parakh_mcp', 'public.holdings_lots', 'SELECT'), 'parakh_mcp cannot read lots');
select ok(not has_table_privilege('parakh_mcp', 'public.transactions', 'SELECT'), 'parakh_mcp cannot read transactions');
select ok(not has_table_privilege('parakh_mcp', 'public.cas_positions', 'SELECT'), 'parakh_mcp cannot read CAS positions');
select ok(not has_table_privilege('parakh_staging', 'public.holdings_lots', 'SELECT'), 'staging cannot read lots');
select ok(not has_table_privilege('anon', 'public.holdings_lots', 'SELECT'), 'anon cannot read lots');

select * from finish();
rollback;

-- pgTAP checks for the shareholding table (plan 14 L4).
begin;
select plan(7);

insert into public.securities (isin, symbol, name) values ('INE000T01011', 'TESTCO', 'Test Co')
  on conflict do nothing;
select lives_ok($$insert into public.shareholding (isin, period_end, reported_on, total_shares,
  promoter_shares, public_shares, promoter_pledged_shares, promoter_encumbered_shares,
  promoter_pct, public_pct, pledge_pct, encumbered_pct, source_id, raw_hash)
  values ('INE000T01011', '2026-06-30', '2026-07-20', 1000, 600, 400, 60, 60, 60, 40, 10, 10,
  'nse_archives', 'sha256:x')$$, 'a quarter is stored');
select lives_ok($$insert into public.shareholding (isin, period_end, reported_on, total_shares,
  promoter_shares, public_shares, promoter_pct, public_pct, pledge_pct, encumbered_pct,
  source_id, raw_hash)
  values ('INE000T01011', '2026-06-30', '2026-08-05', 1000, 590, 410, 59, 41, 0, 0,
  'nse_archives', 'sha256:y')$$, 'a revised filing is a new row');
select throws_ok($$update public.shareholding set promoter_pct = 1$$, '42501', null,
  'shareholding rejects UPDATE');
select throws_ok($$delete from public.shareholding$$, '42501', null, 'shareholding rejects DELETE');
select throws_ok($$insert into public.shareholding (isin, period_end, reported_on, total_shares,
  promoter_shares, public_shares, promoter_pledged_shares, promoter_encumbered_shares,
  promoter_pct, public_pct, pledge_pct, encumbered_pct, source_id, raw_hash)
  values ('INE000T01011', '2026-03-31', '2026-04-20', 1000, 600, 400, 700, 700, 60, 40, 100, 100,
  'nse_archives', 'sha256:z')$$, '23514', null, 'more pledged than held is refused');
select ok(has_table_privilege('parakh_mcp', 'public.shareholding', 'SELECT'), 'parakh_mcp reads shareholding');
select ok(not has_table_privilege('anon', 'public.shareholding', 'SELECT'), 'anon cannot read shareholding');

select * from finish();
rollback;

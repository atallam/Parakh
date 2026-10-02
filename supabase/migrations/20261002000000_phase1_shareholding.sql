-- Parakh Phase 1: quarterly shareholding pattern and promoter pledge (plan 01 §3; plan 09 Phase 1).
-- One row per (ISIN, quarter end, filing date). A revised filing is a new row, never an update,
-- so scoring for date D reads only rows with reported_on <= D (AC-F02.3).
-- Share counts are stored as filed; the *_pct columns are computed from them at load time.
create table public.shareholding (
  isin                        text not null references public.securities (isin),
  period_end                  date not null,
  reported_on                 date not null,
  total_shares                bigint not null check (total_shares > 0),
  promoter_shares             bigint not null check (promoter_shares >= 0),
  public_shares               bigint not null check (public_shares >= 0),
  fii_shares                  bigint check (fii_shares >= 0),
  dii_shares                  bigint check (dii_shares >= 0),
  mf_shares                   bigint check (mf_shares >= 0),
  promoter_pledged_shares     bigint not null default 0 check (promoter_pledged_shares >= 0),
  promoter_encumbered_shares  bigint not null default 0 check (promoter_encumbered_shares >= 0),
  promoter_pct                numeric not null check (promoter_pct between 0 and 100),
  public_pct                  numeric not null check (public_pct between 0 and 100),
  fii_pct                     numeric check (fii_pct between 0 and 100),
  dii_pct                     numeric check (dii_pct between 0 and 100),
  mf_pct                      numeric check (mf_pct between 0 and 100),
  pledge_pct                  numeric not null check (pledge_pct between 0 and 100),      -- of promoter holding
  encumbered_pct              numeric not null check (encumbered_pct between 0 and 100),  -- of promoter holding
  source_id                   text not null references public.sources (source_id),
  raw_hash                    text not null,
  run_id                      text references public.runs (run_id),
  ingested_at                 timestamptz not null default now(),
  primary key (isin, period_end, reported_on),
  check (reported_on >= period_end),
  check (promoter_shares + public_shares <= total_shares),
  check (promoter_pledged_shares <= promoter_encumbered_shares or promoter_encumbered_shares = 0),
  check (promoter_encumbered_shares <= promoter_shares)
);
create trigger shareholding_append_only before update or delete on public.shareholding
  for each row execute function public.reject_mutation();

alter table public.shareholding enable row level security;
revoke all on public.shareholding from anon, authenticated;
grant select on public.shareholding to parakh_mcp, parakh_staging;
create policy mcp_read     on public.shareholding for select to parakh_mcp     using (true);
create policy staging_read on public.shareholding for select to parakh_staging using (true);

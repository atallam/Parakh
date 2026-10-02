-- Parakh Phase 1: data layer and holdings (plan 09 Phase 1).
-- Sources: plan 05 §3 (reference data, fundamentals, holdings), plan 10 §13 (sources, lineage,
-- data quality), plan 13 D8 / P6 (CAS privacy), spike ④ (isin_history).
-- Prices live in Parquet (ADR-004); `price_files` records each file's lineage.

-- ---------------------------------------------------------------------------------------------
-- Source registry (plan 10 §13): every stored number names its source
-- ---------------------------------------------------------------------------------------------
create table public.sources (
  source_id         text primary key check (source_id ~ '^[a-z][a-z0-9_]*$'),
  tier              text not null check (tier in ('T1', 'T2', 'T3')),
  data_types        text[] not null,
  access_method     text not null,
  terms_note        text not null,
  refresh_cadence   text not null,
  last_success_at   timestamptz,
  failure_rate_30d  numeric check (failure_rate_30d between 0 and 1)
);

-- ---------------------------------------------------------------------------------------------
-- Reference data (plan 05 §3.4)
-- ---------------------------------------------------------------------------------------------
-- A split or face-value change issues a new ISIN (spike ④: MAZDOCK INE249Z01012 → INE249Z01020);
-- exchange feeds keep using the old one, so adapters resolve through this table.
create table public.isin_history (
  old_isin    text not null check (old_isin ~ '^[A-Z]{2}[A-Z0-9]{9}[0-9]$'),
  new_isin    text not null references public.securities (isin),
  changed_on  date not null,
  reason      text not null check (reason in ('split', 'face_value', 'merger', 'other')),
  source_id   text not null references public.sources (source_id),
  primary key (old_isin, new_isin),
  check (old_isin <> new_isin)
);

create table public.corporate_actions (
  isin        text not null references public.securities (isin),
  ex_date     date not null,
  kind        text not null check (kind in (
                'split', 'bonus', 'dividend', 'rights', 'demerger', 'buyback', 'face_value')),
  ratio_new   numeric check (ratio_new > 0),   -- e.g. a 1:2 split: new 2, old 1
  ratio_old   numeric check (ratio_old > 0),
  amount_inr  numeric,                          -- dividends
  source_id   text not null references public.sources (source_id),
  raw_hash    text not null,
  fetched_at  timestamptz not null default now(),
  primary key (isin, ex_date, kind)
);

create table public.cap_classification (
  isin            text not null references public.securities (isin),
  effective_date  date not null,
  amfi_rank       integer check (amfi_rank > 0),
  bucket          text not null check (bucket in ('large', 'mid', 'small', 'micro')),
  source_id       text not null references public.sources (source_id),
  primary key (isin, effective_date)
);

create table public.index_membership (
  index_id    text not null,
  isin        text not null references public.securities (isin),
  valid_from  date not null,
  valid_to    date,
  source_id   text not null references public.sources (source_id),
  primary key (index_id, isin, valid_from),
  check (valid_to is null or valid_to >= valid_from)
);

-- ---------------------------------------------------------------------------------------------
-- Fundamentals: bitemporal, long format, append-only (plan 05 §3.4; plan 04 §4 #3)
-- A correction is a new version, never an update, so any past run can be reproduced.
-- ---------------------------------------------------------------------------------------------
create table public.fundamentals (
  isin          text not null references public.securities (isin),
  metric_id     text not null,        -- source line item, e.g. 'annual_pl.Sales'
  period_type   text not null check (period_type in ('annual', 'quarter')),
  period_end    date not null,
  reported_on   date,                 -- result announcement date; null until the exchange feed fills it
  value         numeric,
  unit          text not null check (unit in ('cr', 'inr', 'count', 'count_cr', 'pct', 'ratio')),
  source_id     text not null references public.sources (source_id),
  version       integer not null default 1 check (version >= 1),
  raw_hash      text not null,        -- sha256 of the source file this value came from
  run_id        text references public.runs (run_id),
  ingested_at   timestamptz not null default now(),
  primary key (isin, metric_id, period_type, period_end, source_id, version)
);
create index fundamentals_lookup on public.fundamentals (isin, metric_id, period_end);
create trigger fundamentals_append_only before update or delete on public.fundamentals
  for each row execute function public.reject_mutation();

-- Parquet price files (ADR-004): one row per file written, so a run can name the exact bytes.
create table public.price_files (
  isin          text not null references public.securities (isin),
  year          integer not null check (year between 1990 and 2100),
  storage_path  text not null,
  sha256        text not null,
  rows          integer not null check (rows >= 0),
  first_date    date,
  last_date     date,
  source_id     text not null references public.sources (source_id),
  adjusted      boolean not null,     -- back-adjusted for splits and bonuses
  run_id        text references public.runs (run_id),
  written_at    timestamptz not null default now(),
  primary key (storage_path, sha256)
);
create index price_files_isin_year on public.price_files (isin, year, written_at desc);

create table public.documents (
  doc_id        text primary key,
  isin          text not null references public.securities (isin),
  kind          text not null check (kind in ('concall', 'annual_report', 'presentation', 'filing')),
  period        text,
  source_url    text not null,
  sha256        text not null,
  storage_path  text,
  source_id     text not null references public.sources (source_id),
  fetched_at    timestamptz not null default now()
);

-- Data-quality results per run (plan 10 §13; AC-F02.x)
create table public.dq_results (
  run_id    text not null references public.runs (run_id),
  isin      text not null default '*',   -- '*' = a run-level check
  check_id  text not null check (check_id ~ '^DQ\.[a-z_]+\.[a-z0-9_]+$'),
  status    text not null check (status in ('pass', 'warn', 'fail')),
  detail    jsonb not null default '{}',
  ts_utc    timestamptz not null default now(),
  primary key (run_id, check_id, isin)
);

-- ---------------------------------------------------------------------------------------------
-- Holdings (plan 05 §2; plan 13 D8, P6). Restricted: no role but the service role reads them.
-- Only ISIN, quantity, cost and an account reference (a keyed hash, never a DP/client ID).
-- ---------------------------------------------------------------------------------------------
create table public.cas_statements (
  statement_id   text primary key,
  file_sha256    text not null unique,  -- de-duplicates re-imports; the PDF itself is never stored
  file_type      text not null check (file_type in ('NSDL', 'CDSL')),
  period_from    date not null,
  period_to      date not null,
  imported_at    timestamptz not null default now(),
  run_id         text references public.runs (run_id),
  check (period_to >= period_from)
);

create table public.cas_positions (
  statement_id  text not null references public.cas_statements (statement_id),
  account_ref   text not null check (account_ref ~ '^acct_[0-9a-f]{12}$'),
  isin          text not null check (isin ~ '^[A-Z]{2}[A-Z0-9]{9}[0-9]$'),
  kind          text not null check (kind in ('equity', 'mutual_fund')),
  qty           numeric not null check (qty > 0),
  primary key (statement_id, account_ref, isin)
);
create trigger cas_positions_append_only before update or delete on public.cas_positions
  for each row execute function public.reject_mutation();

create table public.holdings_lots (
  lot_id        text primary key check (lot_id ~ '^[0-9A-HJKMNP-TV-Z]{26}$'),
  account_ref   text not null check (account_ref ~ '^acct_[0-9a-f]{12}$'),
  isin          text not null check (isin ~ '^[A-Z]{2}[A-Z0-9]{9}[0-9]$'),
  qty           numeric not null check (qty >= 0),
  trade_date    date not null,
  settle_date   date not null check (settle_date >= trade_date),
  price_inr     numeric check (price_inr > 0),     -- null = cost pending (AC-F03.6)
  source        text not null check (source in ('broker_pnl', 'cli', 'cas_prompt')),
  status        text not null default 'open' check (status in ('open', 'closed')),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index holdings_lots_isin on public.holdings_lots (account_ref, isin, trade_date);

-- Every change to a lot is a transaction row; lots are the current state, this is the history.
create table public.transactions (
  txn_id        text primary key check (txn_id ~ '^[0-9A-HJKMNP-TV-Z]{26}$'),
  lot_id        text not null references public.holdings_lots (lot_id),
  account_ref   text not null check (account_ref ~ '^acct_[0-9a-f]{12}$'),
  isin          text not null,
  side          text not null check (side in ('buy', 'sell', 'cost_completed')),
  qty           numeric not null check (qty > 0),
  price_inr     numeric check (price_inr > 0),
  trade_date    date not null,
  source        text not null,
  created_at    timestamptz not null default now()
);
create trigger transactions_append_only before update or delete on public.transactions
  for each row execute function public.reject_mutation();

-- ---------------------------------------------------------------------------------------------
-- Row-level security: on everywhere, as in Phase 0
-- ---------------------------------------------------------------------------------------------
alter table public.sources             enable row level security;
alter table public.isin_history        enable row level security;
alter table public.corporate_actions   enable row level security;
alter table public.cap_classification  enable row level security;
alter table public.index_membership    enable row level security;
alter table public.fundamentals        enable row level security;
alter table public.price_files         enable row level security;
alter table public.documents           enable row level security;
alter table public.dq_results          enable row level security;
alter table public.cas_statements      enable row level security;
alter table public.cas_positions       enable row level security;
alter table public.holdings_lots       enable row level security;
alter table public.transactions        enable row level security;

revoke all on all tables in schema public from anon, authenticated;

-- parakh_mcp reads market and reference data only (plan 15 AG-07). Holdings reach agents only
-- through masked portfolio.* tools that run with the service role (Phase 4), never directly.
grant select on public.sources, public.isin_history, public.corporate_actions,
  public.cap_classification, public.index_membership, public.fundamentals, public.price_files,
  public.documents, public.dq_results to parakh_mcp;
create policy mcp_read on public.sources            for select to parakh_mcp using (true);
create policy mcp_read on public.isin_history       for select to parakh_mcp using (true);
create policy mcp_read on public.corporate_actions  for select to parakh_mcp using (true);
create policy mcp_read on public.cap_classification for select to parakh_mcp using (true);
create policy mcp_read on public.index_membership   for select to parakh_mcp using (true);
create policy mcp_read on public.fundamentals       for select to parakh_mcp using (true);
create policy mcp_read on public.price_files        for select to parakh_mcp using (true);
create policy mcp_read on public.documents          for select to parakh_mcp using (true);
create policy mcp_read on public.dq_results         for select to parakh_mcp using (true);

-- The staging role reads reference data to run shadow jobs (plan 13 D17), never holdings.
grant select on public.sources, public.isin_history, public.corporate_actions,
  public.cap_classification, public.index_membership, public.fundamentals,
  public.price_files to parakh_staging;
create policy staging_read on public.sources            for select to parakh_staging using (true);
create policy staging_read on public.isin_history       for select to parakh_staging using (true);
create policy staging_read on public.corporate_actions  for select to parakh_staging using (true);
create policy staging_read on public.cap_classification for select to parakh_staging using (true);
create policy staging_read on public.index_membership   for select to parakh_staging using (true);
create policy staging_read on public.fundamentals       for select to parakh_staging using (true);
create policy staging_read on public.price_files        for select to parakh_staging using (true);

-- Phase 4: the watchlist (plan 06 §7), review marks and UI/bot actions (plan 03 §4.3, plan 12 §5.1).
-- Entries and suggestions are updatable (a decision changes a row); events are append-only like the audit tables.

create table public.watchlist_entries (
  entry_id                 text primary key,
  isin                     text not null references public.securities (isin),
  symbol                   text not null,
  cap                      text not null check (cap in ('large', 'mid', 'small')),
  list_kind                text not null check (list_kind in ('my', 'system')),
  status                   text not null default 'active' check (status in ('active', 'owned', 'archived')),
  added_on                 date not null,
  added_period             text not null check (added_period ~ '^\d{4}-(0[1-9]|1[0-2])$'),
  added_by                 text not null,
  sources                  jsonb not null default '[]',
  reason                   text not null default '',
  target_entry_inr         numeric,
  review_on                date,
  last_period              text,
  fade_runs                int not null default 0,
  top_runs                 int not null default 0,
  weak_runs                int not null default 0,
  promote_rejections       int not null default 0,
  promote_rejected_sources jsonb not null default '[]',
  flags                    jsonb not null default '[]',
  thesis_pending           boolean not null default false,
  removed_on               date,
  removal_rule             text,
  removal_reason           text,
  close_at_add             numeric
);
-- a stock sits on at most one open list at a time (plan 06 §2)
create unique index watchlist_one_open_entry on public.watchlist_entries (isin) where status <> 'archived';

create table public.watchlist_suggestions (
  sugg_id        text primary key,
  isin           text not null references public.securities (isin),
  symbol         text not null,
  cap            text not null check (cap in ('large', 'mid', 'small')),
  action         text not null check (action in ('add_my', 'remove_my', 'promote')),
  sources        jsonb not null default '[]',
  origin         text not null default 'rule',
  reason         text not null,
  evidence       jsonb not null default '{}',
  run_id         text,
  status         text not null default 'pending'
                 check (status in ('pending', 'approved', 'rejected', 'snoozed', 'expired')),
  created_on     date not null,
  expires_on     date not null,
  snoozed_until  date,
  decided_on     date,
  decided_by     text,
  decision_note  text,
  channel        text check (channel in ('streamlit', 'telegram', 'cli', 'mcp', 'system')),
  flag           text
);
create index watchlist_suggestions_open on public.watchlist_suggestions (status, isin);

create table public.watchlist_events (
  event_id  text primary key,
  entry_id  text,
  isin      text not null,
  type      text not null
            check (type in ('added', 'removed', 'flagged', 'promoted', 'urgent_add', 'missed', 'suggested', 'expired')),
  rule_id   text,
  run_id    text,
  at        timestamptz not null,
  detail    jsonb not null default '{}'
);
create index watchlist_events_isin on public.watchlist_events (isin, at);

create trigger watchlist_events_append_only before update or delete on public.watchlist_events
  for each row execute function public.reject_mutation();

-- "Mark all reviewed" on the Home inbox (AC-F15.8); one row per press, so the review time is measurable
create table public.review_marks (
  mark_id      text primary key,
  marked_at    timestamptz not null default now(),
  items        int not null,
  first_opened timestamptz,
  seconds      numeric
);

-- Taps and commands from Telegram, written by the webhook and applied by the services (plan 03 §4.3)
create table public.ui_actions (
  action_id   text primary key,
  received_at timestamptz not null default now(),
  channel     text not null check (channel in ('telegram', 'streamlit')),
  kind        text not null check (kind in ('button', 'command')),
  payload     text not null,        -- the signed button token, or the command text
  update_id   bigint,               -- Telegram update id, so a retried webhook is applied once
  status      text not null default 'queued' check (status in ('queued', 'applied', 'rejected', 'failed')),
  result      text,
  applied_at  timestamptz
);
create unique index ui_actions_update on public.ui_actions (update_id) where update_id is not null;

alter table public.watchlist_entries     enable row level security;
alter table public.watchlist_suggestions enable row level security;
alter table public.watchlist_events      enable row level security;
alter table public.review_marks          enable row level security;
alter table public.ui_actions            enable row level security;
revoke all on public.watchlist_entries, public.watchlist_suggestions, public.watchlist_events,
  public.review_marks, public.ui_actions from anon, authenticated;

-- parakh_mcp: read the watchlist, propose through `proposals` only (AG-03, AC-F24.5)
grant select on public.watchlist_entries, public.watchlist_suggestions, public.watchlist_events
  to parakh_mcp;
create policy mcp_read on public.watchlist_entries     for select to parakh_mcp using (true);
create policy mcp_read on public.watchlist_suggestions for select to parakh_mcp using (true);
create policy mcp_read on public.watchlist_events      for select to parakh_mcp using (true);

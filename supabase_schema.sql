-- Run once in the Supabase SQL Editor. Do not publish service-role credentials.
create table if not exists public.paper_bets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  fixture_date date not null,
  league text not null,
  home text not null,
  away text not null,
  probability double precision not null check (probability >= 0 and probability <= 1),
  odds numeric(9,3) not null check (odds >= 1.01 and odds <= 100),
  stake numeric(12,2) not null check (stake > 0 and stake <= 100),
  commission_pct numeric(5,2) not null check (commission_pct >= 0 and commission_pct <= 10),
  status text not null default 'Open' check (status in ('Open', 'Settled')),
  home_goals integer check (home_goals between 0 and 30),
  away_goals integer check (away_goals between 0 and 30),
  profit numeric(12,2),
  constraint settlement_consistency check (
    (status = 'Open' and home_goals is null and away_goals is null and profit is null)
    or (status = 'Settled' and home_goals is not null and away_goals is not null and profit is not null)
  ),
  unique(user_id, fixture_date, league, home, away)
);
alter table public.paper_bets enable row level security;
revoke all on public.paper_bets from anon;
grant select, insert, update on public.paper_bets to authenticated;
create policy "Owner reads own bets" on public.paper_bets for select to authenticated using ((select auth.uid()) = user_id);
create policy "Owner inserts own bets" on public.paper_bets for insert to authenticated with check ((select auth.uid()) = user_id and status = 'Open');
create policy "Owner updates own bets" on public.paper_bets for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create index if not exists paper_bets_owner_created on public.paper_bets(user_id, created_at desc);

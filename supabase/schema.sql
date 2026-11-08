-- NBA Projection Model: tables in Supabase (same project as the MLB / NHL models, tables prefixed nba_).
-- Paste into the Supabase SQL Editor once. Safe to re-run (IF NOT EXISTS).
--
-- Security: row-level security is ON with no policies, so the public (anon) key used by the MLB
-- website can't read or write these tables. Only the service key (GitHub secret SUPABASE_KEY) can.

-- one row per player per game, from nba.com leaguegamelog (2003-04 on; src/nbacom.py)
create table if not exists nba_player_games (
  game_id      text not null,
  player_id    int  not null,
  season       text not null,          -- '2008-09'
  season_type  text not null,          -- Regular Season / PlayIn / Playoffs
  game_date    date not null,
  player_name  text,
  team_id      int, team text, opp text,
  home         boolean,
  wl           text,
  min real, fgm int, fga int, fg3m int, fg3a int, ftm int, fta int,
  oreb int, dreb int, reb int, ast int, stl int, blk int, tov int, pf int, pts int, plus_minus int,
  primary key (game_id, player_id)
);
create index if not exists nba_player_games_player on nba_player_games (player_id, game_date);
create index if not exists nba_player_games_date on nba_player_games (game_date);

-- one row per team per game
create table if not exists nba_team_games (
  game_id      text not null,
  team_id      int  not null,
  season       text not null,
  season_type  text not null,
  game_date    date not null,
  team text, opp text,
  home         boolean,
  wl           text,
  min real, fgm int, fga int, fg3m int, fg3a int, ftm int, fta int,
  oreb int, dreb int, reb int, ast int, stl int, blk int, tov int, pf int, pts int, plus_minus int,
  primary key (game_id, team_id)
);
create index if not exists nba_team_games_date on nba_team_games (game_date);

alter table nba_player_games enable row level security;
alter table nba_team_games enable row level security;
revoke all on nba_player_games, nba_team_games from anon, authenticated;

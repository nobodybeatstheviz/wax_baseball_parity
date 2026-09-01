-- Metric view: attended team games (Keeping Score parity contract, metric #5-7)
--   team_wins_attended    = SUM(CASE WHEN team_won THEN 1 ELSE 0 END)   over fct_attended_team_games (component)
--   team_games_decided    = SUM(CASE WHEN is_decided THEN 1 ELSE 0 END) over fct_attended_team_games (component)
--   attended_win_rate     = team_wins_attended / team_games_decided, ratio measure, team_id as a DIMENSION
--     NYA spot-check: 90 / 143 = 0.629
-- Source: wax_baseball.parity.fct_attended_team_games (one row per team-perspective on an attended game)
CREATE OR REPLACE VIEW wax_baseball.semantics.mv_attended_team_games
  WITH METRICS
  LANGUAGE YAML
  AS $$
version: 1.0
source: wax_baseball.parity.fct_attended_team_games
dimensions:
  - name: game_date
    expr: game_date
  - name: team_id
    expr: team_id
  - name: opponent_team_id
    expr: opponent_team_id
  - name: is_home
    expr: is_home
measures:
  - name: team_wins_attended
    expr: SUM(CASE WHEN team_won THEN 1 ELSE 0 END)
  - name: team_games_decided
    expr: SUM(CASE WHEN is_decided THEN 1 ELSE 0 END)
  - name: attended_win_rate
    expr: SUM(CASE WHEN team_won THEN 1 ELSE 0 END) / SUM(CASE WHEN is_decided THEN 1 ELSE 0 END)
$$;

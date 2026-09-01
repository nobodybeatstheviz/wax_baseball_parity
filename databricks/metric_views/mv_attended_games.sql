-- Metric view: attended games (Keeping Score parity contract, metric #1-2)
--   games_attended   = COUNT(*)                    over fct_attended_games -> 178
--   unique_stadiums  = COUNT(DISTINCT venue_wax)    over fct_attended_games -> 22
-- Source: wax_baseball.parity.fct_attended_games (one row per attended game)
CREATE OR REPLACE VIEW wax_baseball.semantics.mv_attended_games
  WITH METRICS
  LANGUAGE YAML
  AS $$
version: 1.0
source: wax_baseball.parity.fct_attended_games
dimensions:
  - name: game_date
    expr: game_date
  - name: venue_wax
    expr: venue_wax
  - name: is_yankees_game
    expr: is_yankees_game
measures:
  - name: games_attended
    expr: COUNT(*)
  - name: unique_stadiums
    expr: COUNT(DISTINCT venue_wax)
$$;

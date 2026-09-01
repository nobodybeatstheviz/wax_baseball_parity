-- Metric view: plays witnessed (Keeping Score parity contract, metric #3-4)
--   home_runs_witnessed = SUM(CASE WHEN event_code = 23 THEN 1 ELSE 0 END) over fct_plays -> 400
--   runs_witnessed       = SUM(runs_on_play)                                over fct_plays -> 1706
-- Source: wax_baseball.parity.fct_plays (one row per play, attended games only)
CREATE OR REPLACE VIEW wax_baseball.semantics.mv_plays
  WITH METRICS
  LANGUAGE YAML
  AS $$
version: 1.0
source: wax_baseball.parity.fct_plays
dimensions:
  - name: game_date
    expr: game_date
  - name: event_code
    expr: event_code
  - name: is_yankees_game
    expr: is_yankees_game
measures:
  - name: home_runs_witnessed
    expr: SUM(CASE WHEN event_code = 23 THEN 1 ELSE 0 END)
  - name: runs_witnessed
    expr: SUM(runs_on_play)
$$;

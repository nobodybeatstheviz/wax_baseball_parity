-- Metric view: game attendees (Keeping Score parity contract, metric #8)
--   games_per_attendee = COUNT(*) over fct_game_attendee, attendee_name as dimension
--     top-5: Melissa 57, Bergan 27, Al 26, solo 16, Poppa 14
-- Source: wax_baseball.parity.fct_game_attendee (one row per attendee per attended game)
CREATE OR REPLACE VIEW wax_baseball.semantics.mv_game_attendee
  WITH METRICS
  LANGUAGE YAML
  AS $$
version: 1.0
source: wax_baseball.parity.fct_game_attendee
dimensions:
  - name: game_date
    expr: game_date
  - name: attendee_name
    expr: attendee_name
  - name: attendee_type
    expr: attendee_type
  - name: is_yankees_game
    expr: is_yankees_game
measures:
  - name: games_per_attendee
    expr: COUNT(*)
$$;

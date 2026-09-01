-- Metric view: Hall of Fame sightings (Keeping Score parity contract, metric #9)
--   hall_of_famers_seen = COUNT(DISTINCT player_id) over fct_hof_sightings -> 44
-- Source: wax_baseball.parity.fct_hof_sightings (one row per Hall of Famer seen)
CREATE OR REPLACE VIEW wax_baseball.semantics.mv_hof_sightings
  WITH METRICS
  LANGUAGE YAML
  AS $$
version: 1.0
source: wax_baseball.parity.fct_hof_sightings
dimensions:
  - name: player_name
    expr: player_name
  - name: induction_year
    expr: induction_year
measures:
  - name: hall_of_famers_seen
    expr: COUNT(DISTINCT player_id)
$$;

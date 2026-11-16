-- Futtatandó Supabase SQL Editorban a projekt adatbázis-adminisztrátoraként.
BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'geoterroir_submit') THEN
        CREATE ROLE geoterroir_submit LOGIN NOINHERIT;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'geoterroir_admin') THEN
        CREATE ROLE geoterroir_admin LOGIN NOINHERIT;
    END IF;
END
$$;

CREATE SCHEMA IF NOT EXISTS geoterroir;
REVOKE ALL ON SCHEMA geoterroir FROM PUBLIC;
GRANT USAGE ON SCHEMA geoterroir TO geoterroir_submit, geoterroir_admin;

CREATE TABLE IF NOT EXISTS geoterroir.evaluations (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    lot smallint NOT NULL,
    wine_type text NOT NULL,
    aromas jsonb NOT NULL CHECK (jsonb_typeof(aromas) = 'array' AND aromas <> '[]'::jsonb),
    technique text NOT NULL CHECK (technique IN ('Reduktív', 'Oxidatív')),
    fragrance text,
    variety_group text,
    grape text NOT NULL,
    region text NOT NULL,
    balance text NOT NULL CHECK (balance IN ('Egyensúlyos', 'Nem egyensúlyos')),
    score smallint NOT NULL CHECK (score BETWEEN 1 AND 10),
    chart_active boolean NOT NULL DEFAULT TRUE,
    CHECK (
        (lot BETWEEN 1 AND 3 AND wine_type = 'Fehérbor'
         AND fragrance IS NOT NULL AND fragrance IN ('Illatos', 'Nem illatos')
         AND variety_group IS NULL)
        OR
        (lot BETWEEN 4 AND 5 AND wine_type = 'Vörösbor'
         AND variety_group IS NOT NULL AND variety_group IN ('Világfajta', 'Kárpát-medencei')
         AND fragrance IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS evaluations_created_idx
    ON geoterroir.evaluations (created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS evaluations_lot_created_idx
    ON geoterroir.evaluations (lot, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS evaluations_active_idx
    ON geoterroir.evaluations (lot, created_at DESC) WHERE chart_active;

REVOKE ALL ON geoterroir.evaluations FROM PUBLIC, geoterroir_submit, geoterroir_admin;
GRANT INSERT (id, lot, wine_type, aromas, technique, fragrance, variety_group,
              grape, region, balance, score)
    ON geoterroir.evaluations TO geoterroir_submit;
GRANT SELECT, UPDATE (chart_active) ON geoterroir.evaluations TO geoterroir_admin;

COMMIT;

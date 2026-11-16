CREATE TABLE IF NOT EXISTS evaluations (
    id TEXT PRIMARY KEY NOT NULL,
    created_at TEXT NOT NULL DEFAULT (geoterroir_utc_now()),
    lot INTEGER NOT NULL CHECK (lot BETWEEN 1 AND 20),
    wine_type TEXT NOT NULL CHECK (wine_type IN ('Fehérbor', 'Vörösbor')),
    aromas TEXT NOT NULL CHECK (json_valid(aromas) AND json_array_length(aromas) > 0),
    technique TEXT NOT NULL,
    fragrance TEXT,
    variety_group TEXT,
    grape TEXT NOT NULL,
    region TEXT NOT NULL,
    balance TEXT NOT NULL,
    score INTEGER NOT NULL CHECK (score BETWEEN 1 AND 10),
    chart_active INTEGER NOT NULL DEFAULT 1 CHECK (chart_active IN (0, 1)),
    CHECK (
        (wine_type = 'Fehérbor' AND fragrance IS NOT NULL AND variety_group IS NULL)
        OR (wine_type = 'Vörösbor' AND fragrance IS NULL AND variety_group IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS evaluations_lot_created_idx ON evaluations (lot, created_at DESC, id DESC);

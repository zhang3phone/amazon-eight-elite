-- Applied only to the explicit dedicated local database, after --confirm-db.
CREATE SCHEMA aee;
COMMENT ON SCHEMA aee IS 'amazon-eight-elite:v1';
CREATE TABLE aee.schema_version(version integer PRIMARY KEY CHECK(version=1));
INSERT INTO aee.schema_version VALUES(1);
CREATE TABLE aee.batches(
 batch_id text PRIMARY KEY CHECK(batch_id ~ '^[0-9a-f]{64}$'),
 input_hash text NOT NULL,scope jsonb NOT NULL,collection jsonb NOT NULL,
 config jsonb NOT NULL,engine_version text NOT NULL,imported_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE aee.raw_files(
 batch_id text NOT NULL REFERENCES aee.batches,report_type text NOT NULL CHECK(report_type IN ('campaign','search_term')),
 sha256 text NOT NULL,original_name text NOT NULL,content bytea NOT NULL,metadata jsonb NOT NULL,
 PRIMARY KEY(batch_id,report_type)
);
CREATE TABLE aee.raw_rows(
 batch_id text NOT NULL REFERENCES aee.batches,report_type text NOT NULL,source_row integer NOT NULL CHECK(source_row>0),
 payload jsonb NOT NULL,PRIMARY KEY(batch_id,report_type,source_row)
);
CREATE TABLE aee.ad_groups(
 batch_id text NOT NULL REFERENCES aee.batches,grain text NOT NULL CHECK(grain IN ('campaigns','search_terms')),
 ordinal integer NOT NULL,payload jsonb NOT NULL,PRIMARY KEY(batch_id,grain,ordinal)
);
CREATE TABLE aee.analysis_runs(
 batch_id text PRIMARY KEY REFERENCES aee.batches,result jsonb NOT NULL,html text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX batches_scope ON aee.batches((scope->>'account_alias'),(scope->>'marketplace'));
CREATE INDEX groups_identity ON aee.ad_groups USING gin((payload->'identity'));

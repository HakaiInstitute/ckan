-- The base image's own 10_postgis.sh already loads PostGIS into both
-- template_postgis and $POSTGRES_DB, so a bare CREATE EXTENSION here aborts
-- initdb with `extension "postgis" already exists`. The entrypoint runs .sql
-- files with ON_ERROR_STOP=1, so that killed the container outright and no
-- fresh database could ever be created.
CREATE EXTENSION IF NOT EXISTS postgis;

ALTER VIEW geometry_columns OWNER TO ckan;
ALTER TABLE spatial_ref_sys OWNER TO ckan;

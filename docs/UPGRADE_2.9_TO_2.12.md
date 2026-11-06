# Upgrading CKAN 2.9 → 2.12

This is a large upgrade: three minor versions, a change of base OS, a change of
Python, a new Solr major version, and the removal of several APIs that this
deployment relied on. Read the whole document before starting.

## What changed

| | 2.9 | 2.12 |
|---|---|---|
| Base image | `ckan/ckan-base:2.9` (Alpine) | `ckan/ckan-base:2.12` (Debian bookworm) |
| Python | 3.9 | 3.14 |
| site-packages | `/usr/lib/python3.9/site-packages` | `/usr/local/lib/python3.14/site-packages` |
| `ckan` binary | `/usr/bin/ckan` | `/usr/local/bin/ckan` |
| Container user | uid/gid `92:92` | `ckan:ckan-sys` (503:502) |
| cron | busybox `crond` | Debian `cron` |
| Solr | 10 | 9 |
| Auth | repoze.who + `who.ini` | flask-login |
| Sessions | `beaker.session.*` | `SECRET_KEY` |

Removed APIs that this deployment used:

- **`who.ini` / `who.*` settings** — repoze.who was replaced by flask-login in
  2.10. CKAN 2.12 contains no reference to them.
- **`SECRET_KEY` is mandatory** — CKAN aborts at startup without it.
- **`recline_view`** — no longer an entry point. Replaced by `datatables_view`.
- **`IRoutes`** — removed in 2.11. The interface no longer exists.
- **Old `IPackageController` hook names** — `before_index`, `before_search`,
  `after_search`, `after_show`, `before_view` were renamed to
  `before_dataset_index`, `before_dataset_search`, `after_dataset_search`,
  `after_dataset_show`, `before_dataset_view`. These are **not** deprecated
  aliases: the old names are absent from the 2.12 interface, so a plugin still
  using them is silently never called.
- **`{% resource %}` Jinja tag** — removed in 2.10, replaced by `{% asset %}`.
- **`unicode` validator** — removed in 2.10, replaced by `unicode_safe`.
- **`PackageExtra` model** — dropped in 2.12 (core migration
  `106_12d64978ab44_faster_extras`).
- **Activity streams** — moved out of core into `ckanext-activity` in 2.10.
  It ships with CKAN but must be listed in `ckan.plugins` to be active, and it
  has its own database migrations.

## Order of operations

The steps below are in dependency order and assume the `db` and `ckan`
containers are currently running. The order matters in three places:

- The PostgreSQL dump (step 4) has to happen while the database is **still on
  PostgreSQL 11** and after writers are stopped, so it comes before anything
  that touches the CKAN image.
- `ckan db upgrade` (step 7) has to run on the **already-migrated PostgreSQL
  16** database with the **2.12 image** in place, so it comes after both.
- `search-index rebuild` (step 9) reads from the database, so it comes after
  `db upgrade` - and it is what populates `spatial_geom`, without which
  spatial search returns nothing.

| | Step | Downtime |
|---|---|---|
| 1 | Back up | no |
| 2 | Config changes | no |
| 3 | Stop ckan + harvesters, leave `db` up | **starts here** |
| 4 | PostgreSQL 11 → 16 (dump, replace volume, restore) | yes |
| 5 | Re-own the storage volumes to 503:502 | yes |
| 6 | Replace `ckan_home`, pull the 2.12 image, start CKAN | yes |
| 7 | `ckan db upgrade` | yes |
| 8 | Fit stored extents onto the globe | yes |
| 9 | Solr 8 → 9 + `search-index rebuild` | yes |
| 10 | `ckan asset build` | yes |
| 11 | Verify | yes |
| 12 | Restart harvesters | **ends here** |

Steps 1 and 2 are preparation and can be done ahead of the window.

## 1. Back up first

```bash
cd ~/ckan/contrib/docker/postgresql
sudo bash ./pg_backup_rotated.sh
```

Also snapshot the storage volume — 
```bash
cd ~/ckan/contrib/docker
bash ./backup_ckan_volumes.sh
```
covers `docker_ckan_storage`.

This upgrade is **not reversible** by downgrading the image: `ckan db upgrade`
applies schema and data migrations (notably the `package_extra` change) that
`ckan db downgrade` does not fully reverse. Restoring means restoring the dump.

## 2. Config changes

The authoritative config is the one the running container is using, at
`/srv/app/ckan.ini` inside the `docker_ckan_home` volume. It is not in git —
it holds generated secrets — so it does not arrive via `git pull` and has to
be refreshed on every machine that builds the image.

The Dockerfile copies `contrib/docker/ckan.ini` to `/srv/app/ckan.ini` at
build time, so export the live file into place before editing it:

```bash
cd ~/ckan/contrib/docker
docker cp ckan:/srv/app/ckan.ini ckan.ini
cp ckan.ini ckan.ini.2.9.bak   # keep the 2.9 original
```

`migrate_ckan_ini.py` applies the edits listed below. It works line by line so
comments survive, backs up to `ckan.ini.bak`, and is idempotent — a second run
reports nothing to do:

```bash
cd ~/ckan/contrib/docker
python3 migrate_ckan_ini.py --dry-run ckan.ini   # preview
python3 migrate_ckan_ini.py ckan.ini
```

Read its output. It reduces `ckan.plugins` to `envvars` (see the note
below), warns if `ckan.views.default_views` contained a view
outside the standard set, since that view is dropped and has to be re-added by
hand, and it leaves a non-empty `SECRET_KEY` alone rather than silently
invalidating existing sessions.

Step 6 rebuilds the image and replaces the `docker_ckan_home` volume
wholesale, which is what puts the edited file back into the container —
editing the copy inside the running container instead would be thrown away by
that step.

The edits it makes, for reference:

Removed:

```ini
who.config_file = %(here)s/who.ini
who.log_level = warning
who.log_file = %(cache_dir)s/who_log.ini
beaker.session.key = ckan
beaker.session.secret = ...
```

Added:

```ini
# Left blank: the base image's start_ckan.sh generates SECRET_KEY,
# WTF_CSRF_SECRET_KEY and the api_token.jwt secrets on first boot when it
# finds this key present but empty.
SECRET_KEY =
```

Changed:

```ini
ckan.views.default_views = image_view text_view datatables_view geo_view geojson_view wmts_view
```

`contrib/docker/production.ini` is no longer read by anything — the Dockerfile
now copies `ckan.ini` — so any local copy is a leftover and can be deleted.
The same goes for `contrib/docker/who.ini`; `who_root_url.ini` and
`who_non_root_url.ini` were tracked and have already been deleted.

> **Developer note, not an upgrade step.** Nothing here needs doing during a
> normal upgrade — it only matters if you are changing how the image is built.
>
> `contrib/docker/ckan.ini.template` is the tracked template `ckan.ini`
> is based on. The image-build workflows have no access to the
> gitignored `ckan.ini`, so they materialise one from it:
>
> ```yaml
> - run: cp ./contrib/docker/ckan.ini.template ./contrib/docker/ckan.ini
> ```
>
> So a CI-built image carries the template, not this deployment's config, and
> relies on the `CKAN__*` environment variables in the site env file for
> anything deployment-specific. If you add a setting above that an image must
> carry even without env vars, add it to the template too, or CI-built images
> will drift from locally-built ones.

### Plugin list

The active plugin list comes from the `CKAN__PLUGINS` environment variable
(via `ckanext-envvars`), not from the ini file. Before upgrading:

> **`ckan.plugins` in the ini is a floor the env var cannot lower.** CKAN
> reads `ckan.plugins` from the ini and calls `load_all()` *before* any plugin
> runs. `ckanext-envvars` only executes later, as an `IConfigurer`, and its
> loop just loads names from `CKAN__PLUGINS` that are not already loaded — it
> never unloads anything. So anything listed in the ini stays loaded no matter
> what the env file says.
>
> An ini exported from a 2.9 container has the full resolved list in it, which
> is why `recline_view` keeps coming back and startup fails with
> `PluginNotFoundException`. `ckan.plugins` must be reduced to just:
>
> ```ini
> ckan.plugins = envvars
> ```
>
> `migrate_ckan_ini.py` does this, and refuses to if `envvars` is not already
> in the list — that would mean the deployment is not env-driven at all.
>
> The same trap applies to `scheming.*`. Those keys are read by scheming
> inside its own `update_config`, and `update_config()` calls every
> `IConfigurer` in turn, so whether `envvars` has already run comes down to
> iteration order. A stale `ckanext.scheming:group.json` left in the ini wins
> often enough to abort startup with `SchemingException: Could not load`.
> The script rewrites those paths to `ckanext.hakai:` too.
>
> General rule: treat the env file as the place to *set* things, not as a
> reliable way to *override* a value still present in the ini.

- Replace `recline_view` with `datatables_view`.
- `activity` is already listed in the env templates. Keep it there: activity
  streams left core in 2.10, so without it the Activity tab and the
  `/dashboard` feed disappear. It must be enabled **before** `db upgrade` in
  step 7, because `db upgrade` only applies migrations for plugins that are
  currently enabled.
- `datatables_view` needs `datastore` to be useful.

## 3. Stop the writers

Everything from here changes state. Stop the processes that write to the
database first, but **leave the `db` container running** - the PostgreSQL
migration in the next step dumps from it while it is still on 11.

```bash
cd ~/ckan/contrib/docker
ENVFILE=./.hakaienv     # or .mappenv / .iysenv

sudo docker compose --env-file $ENVFILE stop \
  ckan ckan_gather_harvester ckan_fetch_harvester ckan_run_harvester

sudo docker compose --env-file $ENVFILE ps   # db should still be Up
```

## 4. PostgreSQL 11 → 16

The database image moves from `postgis/postgis:11-3.3` to
`postgis/postgis:16-3.6`. This was previously blocked: the deployment was
pinned to an old PostGIS because ckanext-spatial needed it. Nothing uses
PostGIS now, so the pin is gone.

**PostgreSQL will not start on a data directory written by an older major
version.** Pointing the new image at the existing `pg_data` volume fails with:

```
FATAL:  database files are incompatible with server
DETAIL: The data directory was initialized by PostgreSQL version 11,
        which is not compatible with this version 16.15
```

So this is a dump and restore, not an image swap.

> **Mind `DB_IMAGE` in the interval before the window.** CI pushes both a
> dated tag and `latest`, and the env files use `latest`. From the moment a
> PostgreSQL 16 image is published, any routine `docker compose pull` on a
> site that has not done this step takes its database down. Pin `DB_IMAGE` to
> the last PostgreSQL 11 dated tag as soon as this branch merges, and move it
> back to `latest` here, at the start of this step.

```bash
cd contrib/docker
ENVFILE=./.hakaienv     # or .mappenv / .iysenv

# 1. Drop the dead PostGIS table first, so the dump carries no PostGIS
#    dependency at all and the 3.3 -> 3.6 jump becomes irrelevant.
#    ckanext-spatial no longer reads or writes it.
docker exec db psql -U ckan -d ckan -c "DROP TABLE IF EXISTS package_extent"

# 2. Dump, while still on PostgreSQL 11.
#    NO -t. A TTY rewrites every \n as \r\n on the way out, which silently
#    corrupts a -Fc dump and makes pg_restore fail with
#    "could not read from input file: end of file".
docker exec db pg_dump -U ckan -Fc ckan      > /tmp/ckan.dump
docker exec db pg_dump -U ckan -Fc datastore > /tmp/datastore.dump

# 3. VERIFY THE DUMPS BEFORE DESTROYING ANYTHING. --list parses the whole
#    archive without touching the database; if it prints a TOC the dump is
#    readable. Do not continue if either of these fails.
docker exec -i db pg_restore --list < /tmp/ckan.dump      | tail -5
docker exec -i db pg_restore --list < /tmp/datastore.dump | tail -5

# 4. Replace the volume. THIS DESTROYS THE OLD DATABASE - keep the dumps.
docker compose --env-file $ENVFILE rm -f -s db
docker volume rm docker_pg_data
docker compose --env-file $ENVFILE build db
docker compose --env-file $ENVFILE up -d db      # now PostgreSQL 16

# 5. Restore. The init scripts already recreate the `ckan` and `datastore_ro`
#    roles and an empty `ckan`/`datastore` pair, so restore with --no-owner
#    and --clean to avoid ownership and duplicate-object noise.
docker exec -i db pg_restore -U ckan -d ckan      --no-owner --clean --if-exists < /tmp/ckan.dump
docker exec -i db pg_restore -U ckan -d datastore --no-owner --clean --if-exists < /tmp/datastore.dump

# 6. Re-grant the datastore read-only permissions.
docker compose --env-file $ENVFILE up -d ckan
docker exec -it ckan ckan -c /srv/app/ckan.ini datastore set-permissions \
  | docker exec -i db psql -U ckan -d datastore
```

> **If `pg_restore` says "could not read from input file: end of file"**, the
> dump was taken with `docker exec -t` and the TTY mangled it. It is
> recoverable without re-dumping, because the mangling is exactly reversible —
> every `\n` became `\r\n`, so no bare `\n` survives:
>
> ```bash
> python3 -c "
> import sys
> d = open('/tmp/ckan.dump','rb').read()
> assert d.count(b'\n') == d.count(b'\r\n'), 'not TTY mangling - do not use this'
> open('/tmp/ckan.fixed.dump','wb').write(d.replace(b'\r\n', b'\n'))"
> docker exec -i db pg_restore --list < /tmp/ckan.fixed.dump | head -5
> ```
>
> The assert is the safety check: if any bare `\n` is present the file was
> corrupted some other way and this rewrite would damage it further.

The database now holds the 2.9 schema on PostgreSQL 16. Continue with
step 5; `db upgrade` in step 7 is what migrates the schema to 2.12.

Notes:

- `pg_dumpall --globals-only` is deliberately **not** used. The init scripts
  recreate `ckan` and `datastore_ro`; restoring globals on top only produces
  "role already exists" errors. Dump globals separately if this deployment has
  grown other roles.
- CKAN 2.12's CI matrix covers PostgreSQL 14 and 15, not 16. PostgreSQL 16 was
  tested here directly: `db upgrade` on a clean PostgreSQL 16 database
  succeeded and applied the core, `ckanext-activity` and `ckanext-harvest`
  alembic chains. If you would rather stay inside CKAN's tested range, use
  `postgis/postgis:15-3.6` — same PostGIS, one less major version.
- PostgreSQL 14 switched the default password hash from `md5` to
  `scram-sha-256`. The restored roles keep whatever hash they had; new or
  changed passwords get SCRAM. psycopg2 handles both, so no connection
  string changes are needed.

## 5. Re-own the persistent volumes

The container user changed. The 2.9 Alpine image ran as uid/gid `92:92`; the
2.12 Debian image runs as `ckan:ckan-sys`, **503:502**. Named volumes keep
their original ownership, so CKAN cannot write to its own storage until they
are re-owned, and the first page render dies with:

```
PermissionError: [Errno 13] Permission denied:
  '/var/lib/ckan/webassets/.webassets-cache/...'
```

The API keeps working, which makes this easy to misread as a template bug.

```bash
for v in docker_ckan_storage docker_ckan_config; do
  docker run --rm -v "$v":/data alpine chown -R 503:502 /data
done
```

Check it took:

```bash
docker run --rm -v docker_ckan_storage:/data alpine \
  sh -c 'stat -c "%u:%g" /data/*'     # expect 503:502
```

`docker_ckan_home` does not need this: step 6 deletes and reseeds it from the
image, which already has the right ownership.

## 6. Rebuild and replace the ckan_home volume

The compose files mount `ckan_home:/srv/app`. A named volume is only seeded
from the image when it is **empty**, so an existing `docker_ckan_home` volume
will shadow the new image's `/srv/app` entirely — including `ckan.ini`,
`start_ckan.sh`, `wsgi.py` and every installed extension under `src/`. Pulling
a new image without clearing that volume silently keeps running 2.9 code.

`clean_reload_ckan.sh` already does the right thing. It also stops ckan and
the harvesters, which step 3 has already done - that is harmless, it just
makes the script safe to run on its own.

```bash
cd ~/ckan/contrib/docker

sudo docker compose build ckan
or
sudo docker compose pull ckan

./clean_reload_ckan.sh          # removes docker_ckan_home
sudo docker compose --env-file ./.hakaienv --compatibility up -d ckan
```

This is the point at which the 2.12 image starts running, against the
PostgreSQL 16 database restored in step 4 but with the 2.9 schema still in
place. CKAN will not be fully usable until `db upgrade` in step 7.

## 7. Database migration

```bash
sudo docker exec -it ckan ckan -c /srv/app/ckan.ini db upgrade
```

`db upgrade` applies core migrations **and** the migrations of every enabled
plugin, so this one command also covers `ckanext-harvest` (which gained an
alembic chain upstream, including the `a1c0f3d27b41` revision added here to
recreate two indexes this fork used to declare on its table definitions) and
`ckanext-activity`.

> **Allow time for the activity migration.** `ckanext-activity`'s
> `fab3bfdcf830` revision runs a single bulk
> `UPDATE activity SET permission_labels = '{"public"}'` over every
> dataset-related row. On a catalogue with years of harvester history that
> table is large, so this can take a while and generates a lot of WAL. Run it
> inside the maintenance window rather than being surprised by it.
>
> It is safe on an upgraded database: core migration
> `048_4a7011172b3f_add_activity_streams_tables` still creates the `activity`
> tables, and the plugin's own migrations only add and populate the new
> `permission_labels` column.

Verify nothing was missed:

```bash
sudo docker exec -it ckan ckan -c /srv/app/ckan.ini db pending-migrations
```

## 8. Fit stored extents onto the globe

15 datasets have longitudes outside -180..180, either because they use the
0..360 convention common in oceanography (-165.4 written as 194.6) or because
the extent straddles the antimeridian. See
[the reference section](#reference-fitting-extents-onto-the-globe) for what is
actually going on.

ckanext-spatial repairs these at index time, so **search works either way**.
What this step fixes is the *stored* value, which is what the map widget, the
DCAT and schema.org output and the /geo endpoints read.

Report first, then write:

```bash
docker exec -it ckan ckan -c /srv/app/ckan.ini spatial fit-to-globe
docker exec -it ckan ckan -c /srv/app/ckan.ini spatial fit-to-globe --commit
```

Do it before step 9 so the rebuild there picks the corrected extents up in one
pass. Running it afterwards also works - `package_update` reindexes each
record it touches - it is just a second pass over the same data.

Newly harvested records do not need this; ckanext-cioos_harvest normalises
extents on the way in.

## 9. Solr 8 → 9

`contrib/docker/solr/Dockerfile` is now `FROM solr:9`, and the schema at
`ckan/config/solr/schema.xml` has been rebased onto CKAN 2.12's schema with
the CIOOS additions re-applied. It is a strict superset of CKAN's schema -
nothing removed - adding 51 fields, 4 field types, 2 dynamic fields and 45
copy fields. Two filters the old schema used — `WordDelimiterFilterFactory`
and `SynonymFilterFactory` — were removed in Solr 9 and are replaced by their
`...GraphFilterFactory` equivalents.

The schema also gains a `spatial_geom` field of a new `location_rpt` type, and
the image now downloads the JTS jar (`jts-core` 1.19.0). Solr's
`SpatialRecursivePrefixTreeFieldType` only understands points, rectangles and
circles without JTS on the classpath; JTS is what makes arbitrary-polygon
searches work. CKAN's own `ckan/ckan-solr:2.12-solr9-spatial` image does not
ship it, so do not expect to be able to swap that image in instead.

> **Do this before any `search-index rebuild`.** If the old `solr_data`
> volume is still mounted, the rebuild happily writes into the 2.9 core: the
> schema has no `spatial_geom`, so spatial search stays empty, and
> `data_dict` behaves differently enough to fail with "DocValuesField
> data_dict is too large". Confirm which schema is live first:
>
> ```bash
> docker exec solr curl -sG 'http://localhost:8983/solr/ckan/schema' \
>   | python3 -c 'import sys,json;s=json.load(sys.stdin)["schema"];print(s["name"],s["version"])'
> ```
>
> It must say `ckan-2.12`. If it says `ckan 2.9` the volume was not replaced.

Solr 9 will not read the Solr 8 data directory, and the schema changed, so the
index must be rebuilt from scratch:

```bash
sudo docker compose rm -f -s solr
sudo docker volume rm docker_solr_data
sudo docker compose build solr
sudo docker compose up -d solr
sudo docker exec -it ckan ckan -c /srv/app/ckan.ini search-index rebuild
```

A full rebuild on a large catalogue takes a while; `search-index rebuild-fast`
parallelises it if the machine has spare cores.

## 10. Rebuild assets

```bash
sudo docker exec -it ckan ckan -c /srv/app/ckan.ini asset build
```

## 11. Verify

```bash
# every configured plugin loads
sudo docker exec -it ckan ckan -c /srv/app/ckan.ini plugin-info

# no migrations outstanding
sudo docker exec -it ckan ckan -c /srv/app/ckan.ini db pending-migrations

# search works and the index is populated
sudo docker exec -it ckan ckan -c /srv/app/ckan.ini search-index check

curl -fsS http://localhost:5000/api/3/action/status_show | jq .result.ckan_version
```

Then check by hand: log in (auth moved to flask-login), load a dataset page
with a map, run a spatial search, open the metadata entry form, and confirm
the harvesters are running (`docker logs ckan_gather_harvester`).

## 12. Harvesting

Unlike the 2.8 → 2.9 upgrade, there is no need to clear and re-run the
harvesters: the dataset schema has not changed shape. The Solr index is
rebuilt from the database in step 9, which is enough.

`contrib/docker/crontab` now calls `/usr/local/bin/ckan` instead of
`/usr/bin/ckan`, and the compose services run Debian's `cron -f` instead of
busybox `crond -f`.

`ckan notify send_emails` exists in 2.12, so the email-notification cron entry
that has been commented out since 2.9 can be enabled if wanted — it is still
commented out because turning email on is a deployment decision, not an
upgrade requirement.

## Reference: spatial search moves off PostGIS

This is the biggest behavioural change in the upgrade, and it is why the
database can finally move past postgis-2.1.

Upstream ckanext-spatial deleted the `package_extent` table, the geoalchemy
layer and the whole `model/` package, replacing them with Solr search
backends. Nothing writes to PostGIS any more.

`CKANEXT__SPATIAL__SEARCH_BACKEND` changes from `solr` to
**`solr-spatial-field`** in all three site env files. The old `solr` value
still works (upstream renamed it `solr-bbox` and keeps an alias) but it only
indexes a bounding envelope. `solr-spatial-field` indexes the real geometry
into `spatial_geom`, which is what makes polygon search exact — previously
`ext_poly` queries bypassed Solr entirely and went to PostGIS.

The index carries no `spatial_geom` values until a reindex, so **spatial
search returns nothing until step 9's `search-index rebuild` has run.** Step 9
already rebuilds from scratch, so no extra step is needed — just do not skip
it.

After the rebuild, confirm geometry actually landed in the index:

```bash
sudo docker exec -it solr curl -sG 'http://localhost:8983/solr/ckan/select' \
  --data-urlencode 'q=spatial_geom:*' --data-urlencode 'rows=0' \
  --data-urlencode 'wt=json'
```

A `numFound` of 0 means no dataset has an indexed extent — check that
`spatial_metadata` and `spatial_query` are both in `CKAN__PLUGINS`.

The `package_extent` table and the postgis extension can be dropped once the
upgrade is confirmed good, but leaving them costs nothing and keeps a
rollback possible.

## Reference: fitting extents onto the globe

15 datasets had longitudes outside -180..180 and were being dropped from the
spatial index with "Geometries outside the -180, -90, 180, 90 boundaries are
not supported". Two different causes, despite the single error message:

- 12 used the 0..360 convention common in oceanography, where -165.4 is
  written as 194.6. Those just shift by 360.
- 3 genuinely straddle the antimeridian and have to be split into one polygon
  per side.

This is handled in two places, deliberately:

- `ckanext-spatial` fits the geometry at index time
  (`SpatialSearchBackend.fit_to_globe`, via the `antimeridian` package). Only
  runs when the geometry is out of range. Disable with
  `ckanext.spatial.fit_antimeridian = false`.
- `ckanext-cioos_harvest` normalises the extent as it is harvested, so the
  stored value is right for the map widget, the DCAT and schema.org output and
  the /geo endpoints - not just for search.

For records already in the database the index-time fix is ephemeral, so the
stored extras need repairing once. That is step 8.

## Known gaps

- **20 datasets have self-intersecting polygons**, all meeting at the same
  vertex (`-129.0038 48.4236`), which suggests one bad source geometry copied
  across records. ckanext-spatial rejects them with "Wrong geometry, not
  indexing", so they are searchable by text but not by location. `make_valid`
  would repair them mechanically, but it alters the authored shape, so it is
  left as a decision rather than applied silently.

  After the antimeridian work below, 67 of the 87 datasets with a `spatial`
  extra carry geometry; these 20 are the entire remainder.


- **`contrib/docker/migrations/mapp_ckan_1.5.0.sql`** operates on
  `package_extra`, which CKAN 2.12 dropped, so it cannot be run as-is against
  a 2.12 database. It is a one-off 2.9-era data migration still sitting on the
  parent repo's `MaPP_master` branch.
- **`docker-compose.local.yml`** is still 2.9-era (`/usr/lib/ckan` paths,
  `cioos/ckan` image). It is the build-from-source variant and needs its own
  pass.
- **`ECV.json`** in `cioos-siooc-schema` has a trailing comma and is not valid
  JSON. This predates the upgrade and the file is not copied into the image,
  so it is inert, but it should be fixed or deleted.
- **`cioos_harvest/plugin.py:65`** has `return ''` inside a `finally:` block,
  which swallows exceptions and raises a `SyntaxWarning` on Python 3.12+.
  Left alone because changing it alters exception-handling behaviour.
- **`simple_subfields`** is kept. CIOOS's own `feat/upgrade-2-11` branch
  converts these to `repeating_subfields`, which changes the stored shape from
  a dict to a list and needs a data migration for existing datasets. That is a
  product decision, not an upgrade requirement.

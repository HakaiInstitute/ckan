# Upgrading CKAN 2.9 → 2.12

This is a large upgrade: three minor versions, a change of base OS, a change of
Python, a new Solr major version, and the removal of several APIs that this
deployment relied on. Read the whole document before starting.

> **Status:** `ckanext-spatial` has **not** been ported yet. Until it is, the
> image will not build — `pip install -r ckanext-spatial/requirements.txt`
> fails because the pinned `pyproj==3.6.1` has no Python 3.14 wheel. See
> [Known gaps](#known-gaps).

## What changed

| | 2.9 | 2.12 |
|---|---|---|
| Base image | `ckan/ckan-base:2.9` (Alpine) | `ckan/ckan-base:2.12` (Debian bookworm) |
| Python | 3.9 | 3.14 |
| site-packages | `/usr/lib/python3.9/site-packages` | `/usr/local/lib/python3.14/site-packages` |
| `ckan` binary | `/usr/bin/ckan` | `/usr/local/bin/ckan` |
| Container user | uid/gid `92:92` | `ckan:ckan-sys` (503:502) |
| cron | busybox `crond` | Debian `cron` |
| Solr | 8 | 9 |
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

## 1. Back up first

```bash
cd ~/ckan/contrib/docker/postgresql
sudo bash ./pg_backup_rotated.sh
```

Also snapshot the storage volume — `contrib/docker/backup_ckan_volumes.sh`
covers `docker_ckan_storage`.

This upgrade is **not reversible** by downgrading the image: `ckan db upgrade`
applies schema and data migrations (notably the `package_extra` change) that
`ckan db downgrade` does not fully reverse. Restoring means restoring the dump.

## 2. Config changes

Only `contrib/docker/production_root_url.ini` is tracked in git;
`contrib/docker/production.ini` and `contrib/docker/ckan.ini` are gitignored
deployment-local files (the Dockerfile copies `production.ini` in at build
time). All three have been updated on this machine, but **the two gitignored
ones must be updated by hand on every other machine that builds the image** —
the changes below will not arrive via `git pull`.

The running deployment also keeps its live config in the `docker_ckan_home`
volume at `/srv/app/ckan.ini`; step 3 replaces that volume wholesale.

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

`contrib/docker/who.ini`, `who_root_url.ini` and `who_non_root_url.ini` are no
longer used and the two tracked ones have been deleted.

### Plugin list

The active plugin list comes from the `CKAN__PLUGINS` environment variable
(via `ckanext-envvars`), not from the ini file. Before upgrading:

- Replace `recline_view` with `datatables_view`.
- Add `activity` if you want activity streams. **Add it before running
  `ckan db upgrade`**, because `db upgrade` only applies migrations for
  plugins that are currently enabled.
- `datatables_view` needs `datastore` to be useful.

## 3. Rebuild and replace the ckan_home volume

The compose files mount `ckan_home:/srv/app`. A named volume is only seeded
from the image when it is **empty**, so an existing `docker_ckan_home` volume
will shadow the new image's `/srv/app` entirely — including `ckan.ini`,
`start_ckan.sh`, `wsgi.py` and every installed extension under `src/`. Pulling
a new image without clearing that volume silently keeps running 2.9 code.

`clean_reload_ckan.sh` already does the right thing:

```bash
cd ~/ckan/contrib/docker
sudo docker compose pull ckan
./clean_reload_ckan.sh          # stops ckan + harvesters, removes docker_ckan_home
sudo docker compose --env-file ./.hakaienv --compatibility up -d
```

## 4. Database migration

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

## 5. Solr 8 → 9

`contrib/docker/solr/Dockerfile` is now `FROM solr:9`, and the schema at
`ckan/config/solr/schema.xml` has been rebased onto CKAN 2.12's schema with
the CIOOS additions re-applied (3 field types, 46 fields, 2 dynamic fields,
33 copy fields). Two filters the old schema used — `WordDelimiterFilterFactory`
and `SynonymFilterFactory` — were removed in Solr 9 and are replaced by their
`...GraphFilterFactory` equivalents.

The schema also gains a `spatial_geom` field of a new `location_rpt` type, and
the image now downloads the JTS jar (`jts-core` 1.19.0). Solr's
`SpatialRecursivePrefixTreeFieldType` only understands points, rectangles and
circles without JTS on the classpath; JTS is what makes arbitrary-polygon
searches work. CKAN's own `ckan/ckan-solr:2.12-solr9-spatial` image does not
ship it, so do not expect to be able to swap that image in instead.

Solr 9 will not read the Solr 8 data directory, and the schema changed, so the
index must be rebuilt from scratch:

```bash
sudo docker compose rm -f -s solr
sudo docker volume rm docker_solr_data
sudo docker compose up -d solr
sudo docker exec -it ckan ckan -c /srv/app/ckan.ini search-index rebuild
```

A full rebuild on a large catalogue takes a while; `search-index rebuild-fast`
parallelises it if the machine has spare cores.

## 6. Rebuild assets

```bash
sudo docker exec -it ckan ckan -c /srv/app/ckan.ini asset build
```

## 7. Verify

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

## 8. Harvesting

Unlike the 2.8 → 2.9 upgrade, there is no need to clear and re-run the
harvesters: the dataset schema has not changed shape. The Solr index is
rebuilt from the database in step 5, which is enough.

`contrib/docker/crontab` now calls `/usr/local/bin/ckan` instead of
`/usr/bin/ckan`, and the compose services run Debian's `cron -f` instead of
busybox `crond -f`.

`ckan notify send_emails` exists in 2.12, so the email-notification cron entry
that has been commented out since 2.9 can be enabled if wanted — it is still
commented out because turning email on is a deployment decision, not an
upgrade requirement.

## 9. Spatial search moves off PostGIS

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
search returns nothing until step 5's `search-index rebuild` has run.** Step 5
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

## Known gaps

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

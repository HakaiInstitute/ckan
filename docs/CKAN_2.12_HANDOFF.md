# CKAN 2.12 upgrade — working notes and handoff

Engineering state for the 2.9 → 2.12 upgrade. The deployment runbook is a
separate document: [UPGRADE_2.9_TO_2.12.md](UPGRADE_2.9_TO_2.12.md).

**Branch:** `ckan-2.12-upgrade` (off `hakai_master`), nothing pushed.

```
639dbe960  Collapse the per-site compose files into one, driven by per-site env files
7dde3e9e9  Phase 2: fold the iys_master branch into ckanext-iys
f25a7d575  Phase 2: fold the three mapp_master branches into ckanext-mapp
371ef543f  Phase 2: move the CIOOS-only harvest pieces into the cioos extensions
adcd02f13  Phase 2: add ckanext-hakai and move the scheming/fluent patches into it
81ce924ab  Upgrade CKAN 2.9 -> 2.12 (all but ckanext-spatial)
```

## Status

| Piece | State |
|---|---|
| Dockerfile (Debian / py3.14) | done, builds |
| Solr 8 → 9 + schema | done, verified by booting Solr and querying |
| Config (who.ini, SECRET_KEY, recline_view) | done |
| Debian cron fixes | done |
| dcat, geoview, pdfview | pinned upstream tags, no local delta |
| fluent, scheming, harvest | merged with 2.12-tested upstreams |
| cioos_theme, cioos_harvest, cioos-siooc-schema | ported |
| ckanext-mapp | new — the three `mapp_master` branches folded into one extension |
| ckanext-iys | new — the `iys_master` branch of cioos_theme folded in; the schema branch held nothing |
| ckanext-spatial | merged with `upstream/master` (2.3.2) and ported |
| Solr spatial_geom + JTS | done, verified by polygon round-trip |
| Deployment | one `docker-compose.yml` + one env file per site |
| Phase 2 (de-forking) | four slices done, more possible |

The `pyproj==3.6.1` pin that used to break the build is gone: upstream's
requirements use `pyproj~=3.6`, which resolves to a cp314 wheel.

## Facts established empirically — do not re-derive

These cost real time to pin down. All were checked against the actual 2.12
image or source, not from memory.

**Versions and images**
- CKAN 2.12.1 is current. `ckan/ckan-base:2.12` is Debian bookworm + **Python 3.14**,
  no virtualenv: packages in `/usr/local/lib/python3.14/site-packages`, CKAN
  editable at `/srv/app/src/ckan`, `ckan` binary at `/usr/local/bin/ckan`,
  user `ckan:ckan-sys` (503:502). There is no py3.10 variant of 2.12.

**Dependencies on py3.14**
- `pyproj`, `shapely`, `lxml` all ship cp314 wheels. **GDAL does not** — it is
  sdist-only on PyPI. Debian bookworm's `libgdal-dev` (3.6.2) builds fine
  against py3.14 and `ogr.CreateGeometryFromGML` works; this was tested. The
  recipe is `setuptools<81` + `numpy` preinstalled, then
  `pip install --no-build-isolation "gdal==$(gdal-config --version)"`.
- The from-source PROJ build the 2.9 image needed is gone: pyproj wheels bundle PROJ.
- Dead on py3.14: `past.utils.old_div`, `importlib_metadata` backport,
  `urllib3.contrib.pyopenssl` (urllib3 2.x dropped it). `six` still works —
  see the spatial notes below — but is only present transitively.

**Removed CKAN APIs that bit us**
- `IRoutes` — gone in 2.11.
- Old `IPackageController` hook names (`before_index`, `before_search`,
  `after_search`, `after_show`, `before_view`) are **absent** from the 2.12
  interface, not deprecated aliases. A plugin using them is silently never called.
- `{% resource %}` Jinja tag — gone; only `{% asset %}` exists.
- `unicode` validator — gone; `unicode_safe` replaces it.
- `PackageExtra` model — dropped in 2.12 (core migration `106_12d64978ab44_faster_extras`).
- `recline_view` is not an entry point; `datatables_view` replaces it.
- `SECRET_KEY` is **mandatory** — CKAN aborts at startup without it.
- `toolkit.c` and `ckantoolkit`'s `c` still exist, so Pylons-style `c.user` works.
- repoze.who/`who.*` are referenced nowhere in 2.12.
- Solr: `SUPPORTED_SCHEMA_VERSIONS = ['2.8','2.9','2.10','2.11','2.12']`, and the
  version is read from the schema's `name="ckan-X.Y"` attribute, falling back to
  `version` for pre-2.10 schemas.

**Extension points (checked in source)**
- `_add_served_directory` **prepends** each plugin's template dir, and
  `update_config` runs in `ckan.plugins` order ⇒ **later plugins win** for
  template overrides.
- scheming's `scheming.presets` is a list; it `reversed()`es it and builds a
  dict ⇒ **first entry wins**.
- scheming's `_load_schema_module_path` accepts `module:sub/dir/file.json`,
  so schemas can live in any package (this is how the ckanext-scheming
  package-dir hack was removed).
- `Interface.implemented_by` resolves `_implements` through the MRO, so a
  subclass of a plugin that declares `IHarvester` is found **without**
  re-declaring it. CIOOS's `colton-ckan11upgrade` branch added redundant
  `implements(IHarvester)` calls and a bogus `info()` returning `None`; neither
  is needed.
- ckanext-spatial's search backend is **NOT pluggable** — `_get_search_backend`
  validates against a hardcoded `ALLOWED_SEARCH_BACKENDS` and raises `ValueError`.
- ckanext-spatial hardcodes `ISODocument(harvest_object.content)` in
  `harvesters/base.py`, so the ISO parser cannot be swapped. `ISpatialHarvester`
  offers only `get_package_dict`, `get_validators`, `transform_to_iso`.

**Spatial / Solr (learned during the spatial merge)**
- `six` is **not** dead on py3.14 — 1.17.0 imports fine in the 2.12 image,
  `six.moves` included. An earlier note here said otherwise. It is still worth
  removing, because it only arrives as a transitive dependency.
- Upstream's `str(self.xml_str)` (replacing `six.ensure_str`) is wrong for
  bytes input — it yields `"b'<?xml...'"`. The merge uses an explicit decode.
- `html_parser.unescape` has not existed since Python 3.9. The fork's WAF
  harvester called it; it is now `html.unescape`.
- Solr's `SpatialRecursivePrefixTreeFieldType` handles **only points,
  rectangles and circles** unless the JTS jar is on the classpath. CKAN's own
  `ckan/ckan-solr:2.12-solr9-spatial` image does **not** ship JTS and its
  `location_rpt` type has no `spatialContextFactory`, so that image cannot do
  polygon search either. Ours downloads `jts-core` 1.19.0.
- `get_common_map_config()` strips the `ckanext.spatial.common_map.` prefix and
  keeps the rest of the key verbatim, so `CKANEXT__SPATIAL__COMMON_MAP__STADIA__API_KEY`
  reaches JavaScript as `mapConfig['stadia.api_key']`.
- `stamen` is no longer a leaflet-providers name (Stamen shut down), so
  upstream's `{type: 'stamen'}` default made its own no-provider branch
  unreachable.

**Upstream state**
- Neither `cioos-siooc/ckan` nor `HakaiInstitute/ckan` has started this upgrade:
  all 931 refs still use `ckan/ckan-base:2.9`.
- CIOOS has a thin 2.11 spike in the extension repos (`colton-ckan11upgrade`,
  `feat/upgrade-2-11`, `feat/cioos-siooc-dev-2.11`). Only the scheming one is
  substantial and it was used. The others are ~1 commit each and self-labelled
  "Temporary fix".
- All seven third-party extensions support 2.12 on their canonical `ckan/*`
  masters (verified via CI matrices, not READMEs).

## Traps

- **The `ckan_home` volume shadows the image.** A named volume only seeds from
  the image when empty, so an existing `docker_ckan_home` keeps `ckan.ini`,
  `start_ckan.sh`, `wsgi.py` *and every extension under `src/`* at 2.9. Pulling
  a new image without clearing it silently keeps running old code.
  `clean_reload_ckan.sh` removes it.
- **`production.ini` and `ckan.ini` are gitignored.** Only
  `ckan.ini.template` is tracked. Config changes do not travel via
  `git pull`; they must be applied by hand wherever the image is built.
  The Dockerfile copies the gitignored `production.ini` at build time.
- **The site env files are gitignored too.** `.hakaienv`, `.mappenv` and
  `.iysenv` hold passwords and API keys; only the `.*env.template` files are
  tracked. Every compose command needs `--env-file`, or it silently falls back
  to `./.env` and interpolates the wrong site.
- `contrib/docker/who.ini` is gitignored and now unused.
- `ECV.json` in cioos-siooc-schema has a trailing comma and is invalid JSON.
  Pre-existing, not copied into the image, so inert.
- `cioos_harvest/plugin.py:65` has `return ''` inside `finally:` — swallows
  exceptions, raises SyntaxWarning on 3.12+. Left alone because fixing it
  changes exception semantics.

## Done: ckanext-spatial

Merged with `upstream/master` (v2.3.2 + 3 commits) as a real merge commit, so
the next upstream pull is an ordinary 3-way diff rather than another full
re-derivation. There is no upstream "2.12 branch" — master is the 2.12 line,
and its CI matrix tests `ckan/ckan-dev:2.12-py3.14`.

**Upstream had already absorbed most of what this fork carried.** The `bf`
boost function is character-for-character the same, and the easting
adjustment, geometry→envelope coercion, the `resource_locator` protocols map
and `extras['lineage']` are all upstream now. Do not assume an old fork delta
still needs porting — diff it first.

The big structural change: upstream **deleted** the PostGIS `package_extent`
table, `geoalchemy_common.py` and the whole `model/` package. That removal is
what unblocks the postgis-2.1 pin from commit `10343191f`.

What actually had to be carried over:
- `spatial` **or** `extras_spatial` on index (upstream only checks the latter)
- a degenerate-bbox fix: a Point indexes to a zero-area envelope, which the
  `{!frange incl=false l=0}` filter always excludes
- the three extra helpers, `update_config_schema`, the two `IActions`
- CIOOS WAF additions, the ISO19115 validators, the ISO19139 parser
- the `Session.refresh` workaround for ckanext-harvest #151/#262

**Polygon search was the one piece with no upstream equivalent.** `ext_poly`
always went through PostGIS `polygon_query()` regardless of the configured
backend, so it was the last thing keeping the PostGIS table live. It is now a
Solr `Intersects` against `spatial_geom` on the `solr-spatial-field` backend,
degrading to the polygon's envelope with a warning on `solr-bbox`. The sites
moved from `solr` to `solr-spatial-field` to get exact results; this requires
the full reindex that step 5 of the runbook already performs.

`model/__init__.py` was a namespace package re-exporting both ISO parsers;
`ckanext-cioos_theme/helpers.py:387` imported it as `spatial_model` and now
points at `ckanext.spatial.harvested_metadata`.

## Superseded: the old ckanext-spatial plan

The step-by-step asset and Python port recipe that used to live here has
been carried out; see the two commits in the submodule for what was
actually done. It is removed rather than kept, because several of its
premises turned out to be wrong (notably that the `bf` function and the
easting adjustment still needed porting, and that `six` was dead).

## Next: Phase 2 remainder

Done so far: `ckanext-hakai` created (schemas + fluent presets + fluent_text
template); CIOOS harvester → `ckanext-cioos_harvest`; harvest templates →
`ckanext-cioos_theme`; `ckanext-mapp` created, retiring the three `mapp_master`
branches (cioos_theme, spatial, cioos-siooc-schema); `ckanext-iys` created,
retiring `ckanext-cioos_theme@iys_master`.

Guiding rule learned: **check whether a customisation exists on
`upstream/cioos-siooc` but not `ckan/master`.** If so it is CIOOS-level and
belongs in the shared cioos extensions (where it can be offered back to CIOOS),
not in Hakai-only `ckanext-hakai`.

Second rule, from the MaPP slice: **diff a site branch against its merge-base
with the shared line, not against `hakai_master`.** Most of what
`git log hakai_master..mapp_master` lists is CIOOS work that reached
`hakai_master` by another route; the real site-specific delta in cioos_theme was
12 files, and in spatial 4.

Third rule, from the IYS slice: **check whether a site branch still differs at
all.** `cioos-siooc-schema@iys_master` has 19 commits on it and its tip content
is identical to its merge-base with `hakai_master` — every IYS schema change
was merged into the shared line long ago and the branch has only fallen behind
since. It can be deleted without extracting anything.

### One compose file, one env file per site

There were five near-identical compose files: `docker-compose.yml`,
`docker-compose.hakai.yml`, `docker-compose.cpu_limited.yml`, and a
`docker-compose.iys.yml` / `docker-compose.mapp.yml` on the parent repo's
`iys_master` and `MaPP_master` branches. They differed in the image tag,
whether CPU limits were declared, and whether the services joined Hakai's
external proxy network. One image now carries every site's extensions and
`CKAN__PLUGINS` picks the site, so all of that is environment:

```bash
docker compose --env-file ./.hakaienv up -d
docker compose --env-file ./.mappenv  up -d
docker compose --env-file ./.iysenv   up -d
```

`.env.template` and the hakai/cpu_limited compose files are gone, replaced by
`contrib/docker/.{hakai,mapp,iys}env.template`. `--env-file` supplies the
values interpolated into the compose file; `CKAN_ENV_FILE`, set inside each
template to its own path, is what injects them into the containers — keep the
two in step. The helper scripts (`clean_reload_ckan.sh`, `update_solr.sh`,
`ckan_utils.sh`) read `CKAN_ENV_FILE` and default to `./.env`.

Three things parameterise what used to be separate files:
`LIMIT_CPU_*` (0 = unlimited, the old `docker-compose.yml` behaviour),
`PROXY_NETWORK_EXTERNAL`/`PROXY_NETWORK_NAME` (Hakai's Turnstile proxy network
is external; elsewhere Compose creates `ckan_proxynet`), and
`CKAN_IMAGE`/`DB_IMAGE`/`SOLR_IMAGE`.

`docker-compose.local.yml` was **left alone**. It is the build-from-source
variant and is separately 2.9-era (`/usr/lib/ckan` paths, `cioos/ckan` image);
it needs its own pass.

### Still on the parent repo's site branches

- **`MaPP_master`** — `contrib/docker/migrations/mapp_ckan_1.5.0.sql`, a
  one-off 2.9-era data migration. It rewrites `contact-info_online-resource`
  from a bare URL into the JSON blob form and strips `position-name`, and is
  what the contact normalisation in `ckanext-mapp` exists to paper over for
  records that predate it. It operates on `package_extra`, **which CKAN 2.12
  dropped**, so it cannot be run as-is against a 2.12 database.
  Note its merge-base with `hakai_master` is ancient (695 commits, and it still
  carries an `old/` copy of CKAN), so diff it file by file, not wholesale.
- **`iys_master`** — nothing but a `push:` trigger on
  `.github/workflows/iys-ckan-docker-image.yml`.

That workflow is still here and still builds a separate
`hakaiinstitute/ckan:iys_*` image, which one-image-many-plugins makes
redundant. It was left in place rather than deleted in case a deployment still
pulls that tag. Its `.env.template` and `who_root_url.ini` copy steps were
removed from all three image workflows — nothing in the build read them, and
`who_root_url.ini` has not existed for some time, so those steps were failing.

Remaining:
- **ckanext-harvest, 296 lines left.** `ckanharvester.py` (120) — the
  `_get_content(url, params)` signature change, `modify_remote_organization`
  hook, field filtering, delete support; CIOOS subclasses depend on these.
  `harvest_source_clear` (30) could use `chained_action`. `helpers.py` (28)
  could become ITemplateHelpers in cioos_theme. Will not reach a pinned tag
  without upstreaming.
- **fluent upstream PR.** `fluent_text`/`fluent_tags` parse the language with
  `name.split('-', 1)[1]`, which breaks field names containing dashes. The fork
  uses `split('-')[-1]`, which breaks multi-part BCP-47 tags (`field-zh-Hant`
  → `Hant`). The correct fix is `name[len(prefix):]`. Not extracted because it
  sits inside closures from two factories totalling 307 of the module's 390 lines.
- **After spatial is ported**, extract its validators
  (`ISpatialHarvester.get_validators`), the ISO19115-3 XSLT (`transform_to_iso`),
  assets and templates, and the SpatialQuery index/search customisations.
- Not movable without upstreaming or a data migration: spatial's ISO parser, and
  scheming's `simple_subfields` (CIOOS's own branch converts these to
  `repeating_subfields`, which changes stored shape dict → list).

## Verification recipes

Build without spatial (until it is ported) — strip its two layers into a
throwaway `Dockerfile.noSpatial`, build, then:

```bash
docker run --rm <image> python3 -c "
from importlib.metadata import entry_points
eps={e.name:e for e in entry_points(group='ckan.plugins')}
for w in ['dcat','harvest','ckan_harvester','ckan_schema_harvester','scheming_datasets',
          'fluent','cioos_theme','hakai','geo_view','datatables_view']:
    try: eps[w].load(); print(w,'OK')
    except Exception as e: print(w,'FAILED',e)"
```

`cioos_theme` failing on `shapely` in a spatial-free build is expected — it
loads once shapely is installed.

Solr: build `contrib/docker/solr/Dockerfile`, run it, wait for
`/solr/ckan/admin/ping`, then check `initFailures` is empty and round-trip a
document. Query from **inside** the container; host-port curl was flaky.

Inspect 2.12 internals without a database:

```bash
docker run --rm ckan/ckan-base:2.12 python3 -c "<import and introspect>"
```

The `ckan` CLI needs a live DB even for `--help`, so introspect in Python instead.

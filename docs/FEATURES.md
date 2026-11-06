This document lists what this deployment does that a stock `ckan/ckan` image
does not. For how to perform the 2.9 → 2.12 upgrade itself, see
[UPGRADE_2.9_TO_2.12.md](UPGRADE_2.9_TO_2.12.md).

# One image, many sites

A single image carries every site's extensions. Which site you get is decided
entirely by the plugin list in the `CKAN__PLUGINS` environment variable, read
via `ckanext-envvars` — there is no per-site image and no per-site branch.

| Site | Site extension in `CKAN__PLUGINS` |
|---|---|
| Hakai / CIOOS Pacific | `hakai` |
| MaPP | `mapp`, `mapp_harvest` |
| IYS | `iys` |

Each site extension is a plain directory under `contrib/docker/src/`, not a
submodule:

- **`ckanext-hakai`** — the Hakai schemas, fluent presets and the
  `fluent_text` form snippet. The presets and snippet used to be patches
  applied inside vendored forks of `ckanext-scheming` and `ckanext-fluent`,
  which meant those two could never track an upstream tag. The schemas used to
  be copied in at image build time from the `cioos-siooc-schema` submodule's
  `hakai_master` branch, which hid the fact that the branch had diverged from
  that repository's `master` - including a `topic-category` field no other
  CIOOS site has. That submodule now tracks `master` and is kept only for its
  `.wkt` region polygons.
- **`ckanext-mapp`** — the MaPP schema, templates, map layers and harvester
  customisations. These used to live on a `mapp_master` branch in *three*
  separate checkouts (`ckanext-cioos_theme`, `ckanext-spatial`,
  `cioos-siooc-schema`), so every upstream merge had to be done three times.
- **`ckanext-iys`** — the IYS header, footer, menu and CSS overrides,
  previously an `iys_master` branch of `ckanext-cioos_theme`.

Site extensions must appear **after** the extensions they customise in
`CKAN__PLUGINS`. CKAN resolves template directories and helper registrations
in plugin order, with later plugins winning — so `mapp` and `iys` go after
`cioos_theme`, and `hakai` goes after `fluent`.

Deployment is one `docker-compose.yml` plus one env file per site. Every
compose command needs `--env-file`, or Compose silently falls back to `./.env`
and interpolates the wrong site:

```bash
docker compose --env-file ./.hakaienv up -d
docker compose --env-file ./.mappenv  up -d
docker compose --env-file ./.iysenv   up -d
```

# Search Engines

- sitemap (/sitemap/sitemap.xml)
- robots.txt

## Generating a sitemap

Generating a sitemap can enable searching and harvesting of a CIOOS catalogue by some external organizations like the [Ocean Data and Information System (ODIS)](https://catalogue.odis.org/).

```bash
 sudo docker exec -it ckan ckan --config=/etc/ckan/production.ini sitemap create
```

The sitemap needs to be regenerated whenever a new dataset is added or removed to accurately reflect the contents of the catalogue. Scheduling this task to occur daily is perhaps the easiest way to ensure the sitemap is reasonably up-to-date.

# Harvesting

adding an extra of `harvest_source_quality_level` to a harvester config with a value in ('unknown','external') will add a `external data source` warning message to the dataset page of any dataset from this harvester 

## CKAN Harvester Type

Config settings:

- api_key: api token of a registered user on the ckan being harvested from.
  allows harvesting private datasets
- organizations_filter_include: list (['strings']) - list organizations to include in the harvest
- organizations_filter_exclude: list (['strings']) - list organizations to exclude from the harvest
- groups_filter_include: list (['strings']) - list groups to include in the harvest
- groups_filter_exclude: list (['strings']) - list groups to exclude from the harvest
- field_filter_include: list ([{field:"", value:""}]) - list of fields and values to filter datasets by for including in harvest
- field_filter_exclude: list ([{field:"", value:""}]) - list of fields and values to filter datasets by for excluding from harvest

- clean_tags: munge tags to remove special characters
- force_all: boolean (true|false) - force harvester to gather all datasets even if the dataset was not updated since the last time the harvester was run. Only datasets whose content have changed will be updated.
  force_package_type

- default_tags: list - Set default tags if needed eg: ['waf', 'test']
- remote_groups: string ('only_local'|'create') - populate group if exists,
  create remote groups, or nothing
- remote_orgs: string ('only_local'|'create') - same as above but for
  organizations. If organization can not be determined from dataset it falls
  back to the organization that owns the harvester.
- default_groups: list
- default_extras: dictionary
- override_extras: (default: False)

## CIOOS CKAN Harvester Type

all config settings listed above, plus:

- source_title, and source_description - used to populate included_in_data_catalogue if the source catalogue does not populate this field.

## CKAN Spatial Harvester Type

This is a custom harvester that allows harvesting datasets from a remote ckan
instance who's spatial geometry intersects with a given polygon, multipolygon,
or bbox.

when using ckan spatial harvester the following harvester config settings are available, these are in addition to the ckan harvester config settings:

- spatial_filter_file: Path, relative to the src folder, to a file containing well known text formatted polygons eg "./pacific_RA.wkt"
- spatial_filter: same as above but a literal text string in well know text format.
- spatial_crs: define the crs of the spatial coordinates (default: 4326)

note that when using the ckan spatial harvester, the catalogue you are harvesting
from must have implemented our modified /api/2/search/dataset/geo endpoint to
allow searching by polygon. The default endpoint only allows searching using
bounding box.

## WAF Harvester

ckanext-cioos_harvest extends the waf harvester by adding a `data_catalogue_source` config setting. This setting is used to manually populate the `included_in_data_catalogue` dataset field. An example of the harvest source config is:
```
"data_catalogue_source": [{
  "name": "DataStream",
  "description": "DataStream is an open access platform for water quality data",
  "url": "https://datastream.org"
}]
```

Add the `harvest_source_quality_level` extra to harvester configs. this field can be set to 'unknown' or 'external'. if set it will trigger the display of the metadata quality statment box on dataset pages. This can should be set by adding the key to the 'default_extras' field in the harvester config.

The WAF harvester also accepts a `group_mapping` dictionary, in the same
format as the CKAN harvester's, and `harvest_iso_categories` to map ISO
TopicCategory values onto CKAN groups.

Its directory scraper understands Apache, nginx and IIS listings, tolerates
`<a class="..." href="...">` rather than only `<a href=`, handles the
`<td class="R">` column some servers emit, and un-escapes HTML entities in
hrefs.

## Harvester types added beyond upstream

| Entry point | What it harvests |
|---|---|
| `geonetwork_harvester` | GeoNetwork instances via CSW, pulling GeoNetwork groups into CKAN |
| `datastream_harvester` | a sitemap listing dataset URLs with ISO19115-2 XML |
| `ckan_cioos_harvester` | remote CKANs implementing the CIOOS metadata profile |
| `ckan_spatial_harvester` | remote CKANs, filtered by polygon (see above) |
| `ckan_schema_harvester` | remote CKANs, mapping into a scheming schema |

Both ISO19115-3 and ISO19139 are supported. The `parser` harvester config
option chooses between them (`iso19115` is the default); there is also an
ISO19139 → ISO19115-3 XSLT for sources that only publish the older standard.

# Menu

it is now possible to sync the menu items from a compatible wordpress site, into ckan. The wordpress instance must implement the following endpoints

```text
/wp-json/ra/menu/en
/wp-json/ra/menu/fr
```

To use, first set the 'Custome Header Filename' config option to the appropriate value, for example `/menu/pacific_menu_list.html`. If you are using an existing file then you could stop there. CKAN will pull the menu items from the appropriate template in the /menu/ folder.

To sync menu items from a wordpress site we run the `menu create` CLI command.

## CLI Command Usage

```bash
ckan  menu create --url [path to wordpress api endpoint] --output [output menu list file (default: /menu/menu_list.html)]
```

## Example

```bash
sudo docker exec -u root -it ckan  ckan --config /etc/ckan/production.ini menu create --url https://cioospacific.ca/wp-json/ra/menu/ --output /menu/pacific_menu_list.html
```

# organization_list api end point

added a fq paramiter to organization_list so that results can be filtered on fields other then name, description, and title.
not queries are supported by adding a negative sign in front of the field name.

example query `/api/3/action/organization_list?q=hakai&all_fields=true&include_extras=true&fq=-organization-uri:code"_ "",&fq=organization-uri:__`

# Spatial search

Stock CKAN has no spatial search at all; `ckanext-spatial` adds it, and this
deployment extends it further.

## Exact polygon search

Upstream `ckanext-spatial` can only filter by a bounding box (`ext_bbox`).
This deployment adds polygon and multipolygon filtering (`ext_poly`), exposed
through two endpoints:

```text
/api/2/search/<register>/geo
/api/3/search/<register>/geo_package_search
```

Both accept `bbox`, or `poly` in well-known text, plus an optional `crs`:

- `POLYGON((x1 y1, x2 y2, ...))`
- `MULTIPOLYGON(((x1 y1, ...)), ((x1 y1, ...)))` — external rings only
- `BOX(minx, miny, maxx, maxy)`

`geo` returns `{"count": n, "results": [id, ...]}`. `geo_package_search` takes
the same arguments plus any normal `package_search` argument and returns a
full `package_search` response, so it can be used as a drop-in replacement.

The same two are registered as actions, `spatial_query_geo` and
`spatial_query_geo_package_search`.

These results are **exact**, not the polygon's bounding box. That requires
both of the following, which are configured by default here:

```ini
ckanext.spatial.search_backend = solr-spatial-field
```

and a Solr image carrying the JTS library. Solr's
`SpatialRecursivePrefixTreeFieldType` only understands points, rectangles and
circles unless JTS is on the classpath — CKAN's own
`ckan/ckan-solr:*-spatial` images do **not** ship it, so they cannot do this.
`contrib/docker/solr/Dockerfile` downloads `jts-core` and the schema declares
`spatial_geom` with `spatialContextFactory="JTS"`.

On the `solr-bbox` backend the same query still works but degrades to the
polygon's bounding envelope, and logs a warning.

> Dataset geometry is only written to the index during indexing, so spatial
> search returns nothing until `ckan search-index rebuild` has run.

## Other spatial config

```ini
# starting map extent, either Leaflet bounds [[south, west], [north, east]]...
ckanext.spatial.default_extent = [[46.0, -140.0], [60.0, -125.0]]

# ...or a GeoJSON Polygon, which the widget converts to bounds
# ckanext.spatial.default_extent = {"type": "Polygon", "coordinates": [[...]]}

# expand the map widget when a spatial search runs
ckan.spatial.spatial_widget_expands = false
```

## No PostGIS

Spatial extents are stored in Solr, not in a PostGIS `package_extent` table.
Nothing in the stack requires the postgis extension any more, which is what
allowed the database image to move off postgis-2.1.

# map background tiles

Any [leaflet-providers](https://github.com/leaflet-extras/leaflet-providers)
name can be used as the base map:

```
ckanext.spatial.common_map.type = OpenStreetMap.Mapnik
```

If no `type` is set, the map falls back to Stadia Maps' Stamen Terrain tiles,
which need a free API key — register at
https://stadiamaps.com/stamen/onboarding/ and add it to your production.ini:

```
ckanext.spatial.common_map.stadia.API_key = YOURKEYHERE
```

(Config keys are lower-cased when loaded, so `API_key` and `api_key` are
equivalent here.)

With neither a `type` nor a Stadia key, the map renders a "no map provider
set" notice rather than failing silently.

`mapbox`, `custom` and `wms` remain available as `type` values.

# map RA polygons layer
To add a polygon layer of Regional Associations to the map, add the following key to the production.ini file. This should be the path to the json file on disk, not a url.
example:
```
ckan.cioos.ra_json_file = ./ckanext-cioos_theme/ckanext/cioos_theme/public/base/layers/RA.json
```
once added a Regional Associations layer will be avilable in the layer button in the spatial search map on the dataset page

# Solr schema

The Solr image is built from `ckan/config/solr/schema.xml`. It is a strict
superset of CKAN 2.12's own schema — nothing is removed — adding 51 fields,
4 field types, 2 dynamic fields and 45 copy fields. These are what make the
CIOOS metadata facetable and searchable: `eov`, `datacentre`,
`included_in_data_catalogue`,
`metadata-point-of-contact`, `cited-responsible-party`, `distributor`,
`lineage`, `dataset-reference-date`, the bbox fields, and the French-analysed
(`text_fr`) variants used for bilingual search.

It also carries `spatial_geom` (type `location_rpt`) for the spatial search
described above, and the image installs the JTS library that field needs.

Rebuild the image and reindex after changing the schema:

```bash
docker build -t hakaiinstitute/solr:latest --file ./contrib/docker/solr/Dockerfile .
docker exec -it ckan ckan -c /srv/app/ckan.ini search-index rebuild
```
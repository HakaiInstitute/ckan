# ckanext-hakai

Hakai/CIOOS customisations that used to live as patches inside vendored
`ckanext-*` forks. Everything here is expressed through published CKAN
extension points, so the checkouts it replaces can go back to being pinned
upstream tags.

## Plugin ordering

`hakai` must appear **after** the extensions it customises in `ckan.plugins`
(in particular after `fluent`). CKAN resolves template directories and
`ITemplateHelpers`/`IValidators` registrations in plugin order, with later
plugins winning.

The live plugin list comes from the `CKAN__PLUGINS` environment variable via
`ckanext-envvars`, not from the ini file.

## What it holds

### `schemas/`

The CIOOS schemas, copied in at image build time from the `cioos-siooc-schema`
submodule, which stays the source of truth.

They used to be copied into **ckanext-scheming's own package directory** and
referenced as `ckanext.scheming:cioos_siooc_schema.json`, which meant scheming
could never be a plain pinned dependency — the schemas masqueraded as part of
upstream. They are now referenced as `ckanext.hakai:schemas/<file>`:

```ini
scheming.dataset_schemas      = ckanext.hakai:schemas/cioos_siooc_schema.json
scheming.organization_schemas = ckanext.hakai:schemas/organization.json
scheming.group_schemas        = ckanext.hakai:schemas/group.json
licenses_group_url            = file:///srv/app/src/ckanext-hakai/ckanext/hakai/schemas/ckan_license.json
```

### `presets/hakai_presets.json`

Overrides the `fluent_tags` preset to add the tag autocomplete `form_attrs`.

Must be listed **first** in `scheming.presets`. Scheming reverses the list and
builds a dict, so the first entry takes precedence:

```ini
scheming.presets = ckanext.hakai:presets/hakai_presets.json
                   ckanext.scheming:presets.json
                   ckanext.fluent:presets.json
```

### `templates/`

`scheming/form_snippets/fluent_text.html` — suppresses a field's custom
`form_attrs` for languages not in `slug_lang`, while keeping the base styling
upstream applies to every fluent input.

## Still forked, and why

**`ckanext-fluent/ckanext/fluent/validators.py`** — two lines. `fluent_text`
and `fluent_tags` parse the language out of a flattened key with
`name.split('-', 1)[1]`, which breaks for field names containing dashes
(`temporal-extent-begin-en` yields `extent-begin-en` as the language). The fork
uses `name.split('-')[-1]`.

This is not extracted because the fix sits inside closures returned by two
validator factories totalling 307 of the module's 390 lines — copying them here
to change two lines would be worse than the patch.

Note the fork's version is also not quite right: `split('-')[-1]` breaks
multi-part BCP-47 tags (`field-zh-Hant` yields `Hant`). `name[len(prefix):]`
handles both cases and is the fix worth sending upstream.

## Not in scope here

Two customisations have no extension point at all and cannot move:

- **ckanext-spatial's ISO parser.** `harvesters/base.py` hardcodes
  `ISODocument(harvest_object.content)`. `ISpatialHarvester` offers
  `get_package_dict`, `get_validators` and `transform_to_iso`, which covers the
  vendored validation schemas and the ISO19115-3 XSLT, but not the parser.
- **ckanext-scheming's `simple_subfields`.** Implemented inside
  `SchemingDatasetsPlugin` methods. The alternative is to migrate the schema to
  `repeating_subfields`, which changes the stored shape from a dict to a list
  and needs a data migration.

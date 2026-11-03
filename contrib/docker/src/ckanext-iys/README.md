# ckanext-iys

The IYS (International Year of the Salmon) site's customisations, in one
extension.

They used to live on an `iys_master` branch of `ckanext-cioos_theme`, so IYS
could only be deployed by checking out a different branch of that submodule.
Everything here is a template or asset override instead, so the branch can be
retired and the checkout can track the shared CIOOS/Hakai line.

Same move `ckanext-hakai` made for the Hakai-only patches and `ckanext-mapp`
for MaPP; see their READMEs.

## Enabling it

```ini
ckan.plugins = ...
               cioos_theme
               iys
```

`iys` must come **after** `cioos_theme`: CKAN resolves template directories in
plugin order with later plugins winning, and `header.html` / `footer.html`
here override cioos_theme's. The live plugin list comes from the
`CKAN__PLUGINS` environment variable via `ckanext-envvars`, not from the ini
file.

### Config

```ini
# the IYS palette; it @imports cioos_theme.css ahead of its own rules
ckan.cioos.ra_css_path = /iys.css

# IYS's own Cloudflare Turnstile site key
ckan.cioos.turnstile_site_key = 0x4AAAAAAEJdBg9eZfMxtr4b

# IYS is English-only
ckan.show_language_picker_in_top_bar = false
ckan.show_language_picker_in_menu    = false
```

`ckan.header_file_name` and `ckan.footer_file_name` are **not** needed: this
extension's header and footer reference the IYS menu by path.

`scheming.*` is unchanged from the Hakai deployment — see below.

## There is no IYS schema

`cioos-siooc-schema@iys_master` carries nothing. Its tip content is
byte-for-byte (modulo JSON indentation) the same as its merge-base with
`hakai_master`: the IYS schema commits — "remove french language", "add
biological eov's", "set preset for spatial field", "update display settings
for contacts" — were all merged into the shared line years ago, and the branch
has only fallen behind since.

So IYS uses `ckanext.hakai:schemas/cioos_siooc_schema.json` like everyone
else, and that branch can be deleted without extracting anything.

One caveat worth a decision before IYS is redeployed: `hakai_master` later
added `"alternate_languages": {"fr": ["en"]}` to the shared schema (commit
"update schema to match existing hakai schema"), which turns on the French
side of every fluent field. IYS was English-only. The branch cannot tell us
whether IYS wants that off, because it predates the change. If it does, IYS
needs its own schema copy with that key removed — the same vendored-copy
approach `ckanext-mapp` takes.

## What it holds

### `templates/header.html`

The CIOOS "mega menu" header, which ckanext-cioos_theme carried until
`hakai_master` reverted its copy to the plain CKAN navbar.

Two differences from the version it came from:

- **No social list.** `iys_master` got this by emptying cioos_theme's shared
  `menu/social_list.html` — a file that still holds CIOOS's own
  LinkedIn/Twitter/Facebook links and is used by the other sites. Dropping the
  two snippet calls here renders the same thing and leaves the shared file
  alone.
- **The menu is snippeted by path**, not through `ckan.header_file_name`.
  `iys_master` additionally overwrote the shared `menu/menu_list.html` with the
  IYS menu; that copy is gone.

Both language pickers are kept and stay config-gated.

### `templates/footer.html`

The IYS footer — contact link and a link back to yearofthesalmon.org — plus
the account masthead reproduced from cioos_theme unchanged. A full copy rather
than a `ckan_extends` override, because the `<footer class="site-footer">`
wrapper it replaces is not inside a Jinja block.

### `templates/menu/iys_menu_list.html`

The IYS main menu. On `iys_master` this file existed twice — once under its own
name and once as `menu/menu_list.html`, byte-identical — and its contents were
wrapped in an `{%- if h.lang() == 'en' -%}` / `{% else %}` whose two branches
were also byte-identical. Both the duplicate and the dead conditional are gone.

### `public/iys.css`

The IYS palette and the "Additional Info" table styling.

cioos_theme's `base.html` loads exactly **one** extra stylesheet, named by
`ckan.cioos.ra_css_path`. `iys_master` got two by uncommenting the
`cioos_theme.css` `<link>` in `base.html`. This file opens with
`@import url("/cioos_theme.css")` instead, which loads the same two
stylesheets in the same order without forking `base.html`.

## Changed in ckanext-cioos_theme

One shared change, rather than duplicating a file to alter a single string:

**The Cloudflare Turnstile site key is now config.** Turnstile issues keys per
domain, so `js/turnstyle.js` hardcoding the Hakai catalogue's key meant IYS had
to fork a 60-line JS file over one literal. `base.html` now emits
`window.CIOOS_TURNSTILE_SITEKEY` from `ckan.cioos.turnstile_site_key`, and
`turnstyle.js` falls back to the old literal when it is unset — so every
existing deployment behaves exactly as before.

## Not carried over

- **IYS's `menu/menu_list.html`.** It clobbered the shared CIOOS menu for every
  site. The IYS menu lives under its own name here and the shared one is
  untouched.
- **The empty `menu/social_list.html`.** See `header.html` above.
- **`base.html`.** The only IYS change to it was uncommenting the
  `cioos_theme.css` link, which `iys.css`'s `@import` now covers.

## Still on `iys_master`, and why

Nothing in `ckanext-cioos_theme`, and nothing at all in `cioos-siooc-schema`.

The **parent repository** also has an `iys_master` branch.

Its `contrib/docker/docker-compose.iys.yml` is gone: it differed from the
shared `docker-compose.yml` only in the image tag
(`hakaiinstitute/ckan:iys_${CKAN_TAG}`), some CPU limits and whitespace, and
under one-image-many-plugins there is no IYS image to tag. IYS now runs the
shared compose file:

```bash
docker compose --env-file ./.iysenv up -d
```

with `.iysenv` copied from the tracked `contrib/docker/.iysenv.template`, which
carries the settings listed above.

What is left on that branch is a `push:` trigger on
`.github/workflows/iys-ckan-docker-image.yml`. That workflow still builds and
pushes a separate `hakaiinstitute/ckan:iys_*` image, which one-image-many-plugins
makes redundant. It has been left alone rather than deleted, in case a
deployment still pulls that tag.

# encoding: utf-8
"""MaPP site customisations.

This is everything that used to live on the `mapp_master` branches of
ckanext-cioos_theme, ckanext-spatial and cioos-siooc-schema, re-expressed
through published CKAN extension points so those branches can be retired and
their checkouts can track the shared CIOOS/Hakai line again.

Plugin ordering matters: in `ckan.plugins`, `mapp` must come *after*
`cioos_theme`. CKAN resolves template directories, ITemplateHelpers and
IFacets in plugin order, with later plugins winning, and the facet and
contact work here runs on what cioos_theme has already produced.
"""
import json
import logging

from ckan import plugins
from ckan.lib.plugins import DefaultTranslation
from ckan.plugins import toolkit

log = logging.getLogger(__name__)


#: Facets added to the dataset search sidebar, in display order. They are
#: inserted after cioos_theme's `ecv` facet.
MAPP_FACETS = [
    ('mapp-theme', 'Theme'),
    ('mapp-sub-theme', 'Sub Theme'),
    ('mapp-sub-region', 'Region'),
    ('mapp-project', 'Project'),
]

#: cioos_theme's facet that MaPP replaces with `mapp-project`.
REPLACED_FACET = 'projects'

#: Fields stored as a JSON list that Solr has to see as a real list.
JSON_LIST_FIELDS = ['mapp-sub-region', 'mapp-project']

#: Keys of a grouped contact dict that MaPP rewrites.
CONTACT_FIELDS = ['cited-responsible-party', 'metadata-point-of-contact']


def load_json(value):
    """Parse a JSON string, passing anything that is not JSON straight through.

    A local copy of ckanext-cioos_theme's helper of the same name. Importing
    its `helpers` module would pull in shapely and the rest of the theme's
    dependency tree for five lines.
    """
    try:
        return json.loads(value)
    except Exception:
        return value


def _collapse(values):
    """Dedupe a list, drop empties, and unwrap a single remaining value.

    Mirrors the tail of ckanext-cioos_theme's `group_by_ind_or_org`, which is
    what produced the dicts this module rewrites.
    """
    values = list(dict.fromkeys(values))
    if len(values) == 1:
        return values[0]
    values = [v for v in values if v]
    if len(values) == 1:
        return values[0]
    return values


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


class MappPlugin(plugins.SingletonPlugin, DefaultTranslation):
    plugins.implements(plugins.ITranslation)
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IFacets)
    plugins.implements(plugins.IPackageController, inherit=True)

    # IConfigurer

    def update_config(self, config_):
        # Templates here override the same-named templates from extensions
        # listed earlier in ckan.plugins, which is why `mapp` must follow
        # `cioos_theme`.
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')

    # ITemplateHelpers

    def get_helpers(self):
        return {
            # Adds the MaPP homepage to the layout dropdown in /ckan-admin/config
            # alongside the CIOOS one that cioos_theme registers.
            'cioos_append_to_homepages': self.append_to_homepages,
        }

    def append_to_homepages(self, homepages):
        homepages.append({'value': '4', 'text': 'CIOOS'})
        homepages.append({'value': '5', 'text': 'MaPP'})
        return homepages

    # IFacets

    def dataset_facets(self, facets_dict, package_type):
        return self._update_facets(facets_dict)

    def group_facets(self, facets_dict, group_type, package_type):
        return self._update_facets(facets_dict)

    def organization_facets(self, facets_dict, organization_type, package_type):
        return self._update_facets(facets_dict)

    def _update_facets(self, facets_dict):
        """Insert the MaPP facets after `ecv` and drop the one they replace.

        cioos_theme has already rebuilt and ordered `facets_dict` by the time
        this runs, so the dict is unpacked and refilled rather than appended
        to: a plain assignment would put the MaPP facets at the bottom.
        """
        facets_dict.pop(REPLACED_FACET, None)
        if MAPP_FACETS[0][0] in facets_dict:
            return facets_dict

        existing = list(facets_dict.items())
        facets_dict.clear()
        for key, value in existing:
            facets_dict[key] = value
            if key == 'ecv':
                self._add_mapp_facets(facets_dict)
        if MAPP_FACETS[0][0] not in facets_dict:
            # cioos_theme is not loaded, or stopped emitting `ecv`.
            self._add_mapp_facets(facets_dict)
        return facets_dict

    @staticmethod
    def _add_mapp_facets(facets_dict):
        for key, label in MAPP_FACETS:
            facets_dict[key] = toolkit._(label)

    # IPackageController

    def before_dataset_index(self, data_dict):
        """Turn the stored JSON lists into real lists so Solr indexes them.

        cioos_theme does the same for its own multi-valued fields; the MaPP
        ones are not in its list.
        """
        if data_dict.get('type') != 'dataset':
            return data_dict
        for field in JSON_LIST_FIELDS:
            if data_dict.get(field):
                data_dict[field] = load_json(data_dict[field])
        return data_dict

    def after_dataset_show(self, context, package_dict):
        self._normalise_contacts(package_dict)
        return package_dict

    def after_dataset_search(self, search_results, search_params):
        for package_dict in search_results.get('results', []):
            self._normalise_contacts(package_dict)
        return search_results

    def _normalise_contacts(self, package_dict):
        """Tidy the contacts cioos_theme has already grouped.

        Two things MaPP wants that the shared grouping does not do:

        - `contact-info_online-resource` arrives as a JSON blob per contact
          (`{"url": ..., "name": ..., ...}`). Only the URL is of any use on
          the page, so the blob is reduced to it. Entries that are not JSON,
          or that carry no url, are dropped.
        - a contact listed under several roles accumulates one copy of its
          address per role. They are deduped and joined into a single string.
        """
        for field in CONTACT_FIELDS:
            contacts = package_dict.get(field)
            if not isinstance(contacts, list):
                continue
            for contact in contacts:
                if not isinstance(contact, dict):
                    continue
                self._normalise_online_resource(contact)
                self._normalise_email(contact)

    @staticmethod
    def _normalise_online_resource(contact):
        if 'contact-info_online-resource' not in contact:
            return
        urls = []
        for item in _as_list(contact['contact-info_online-resource']):
            try:
                url = load_json(item)['url']
            except (TypeError, KeyError, ValueError, AttributeError):
                continue
            if url:
                urls.append(url)
        contact['contact-info_online-resource'] = _collapse(urls)

    @staticmethod
    def _normalise_email(contact):
        emails = contact.get('contact-info_email')
        if not isinstance(emails, list):
            return
        emails = [e for e in dict.fromkeys(emails) if e]
        contact['contact-info_email'] = ', '.join(emails)

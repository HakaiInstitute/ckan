# encoding: utf-8
"""Pull the MaPP vocabularies out of harvested ISO 19115-3 documents.

MaPP tags its records with four controlled vocabularies, each carried as an
`MD_Keywords` block whose thesaurus title names the vocabulary:

    MaPP Theme, MaPP Sub-Theme, MaPP Sub-Region, MaPP Project

On `mapp_master` these were four extra `ISOElement`s patched into
ckanext-spatial's `ISODocument`. That patch cannot be expressed as an
extension: `ckanext/spatial/harvesters/base.py` hardcodes
`ISODocument(harvest_object.content)`, so the parser is not swappable.

`ISpatialHarvester.get_package_dict` is, though, and it is handed the parsed
`xml_tree`, so the same xpaths run here instead. ckanext-cioos_harvest copies
every `iso_values` key whose name matches a scheming field into the package
dict; this plugin does that last step itself, for these four fields only.

Ordering: `mapp_harvest` must come *after* `cioos_harvest` in `ckan.plugins`,
because it writes straight into the package dict that cioos_harvest builds.
"""
import logging

from ckan import plugins

from ckanext.spatial.interfaces import ISpatialHarvester

log = logging.getLogger(__name__)

NAMESPACES = {
    'mdb': 'http://standards.iso.org/iso/19115/-3/mdb/2.0',
    'mri': 'http://standards.iso.org/iso/19115/-3/mri/1.0',
    'srv': 'http://standards.iso.org/iso/19115/-3/srv/2.0',
    'cit': 'http://standards.iso.org/iso/19115/-3/cit/2.0',
    'gco': 'http://standards.iso.org/iso/19115/-3/gco/1.0',
}

_IDENTIFICATION = (
    'mdb:identificationInfo/mri:MD_DataIdentification',
    'mdb:identificationInfo/srv:SV_ServiceIdentification',
)

_KEYWORDS = (
    'mri:descriptiveKeywords/mri:MD_Keywords'
    '[mri:thesaurusName/cit:CI_Citation/cit:title/gco:CharacterString/text() = "{thesaurus}"]'
    '/mri:keyword/gco:CharacterString/text()'
)

#: scheming field name -> (thesaurus title, keep the value as a list?)
#:
#: `mapp-theme` and `mapp-sub-theme` are `select` fields and `mapp-project` is
#: `tag_string_autocomplete`; all three take a comma-separated string.
#: `mapp-sub-region` is `multiple_select`, which takes a list.
MAPP_VOCABULARIES = {
    'mapp-theme': ('MaPP Theme', False),
    'mapp-sub-theme': ('MaPP Sub-Theme', False),
    'mapp-sub-region': ('MaPP Sub-Region', True),
    'mapp-project': ('MaPP Project', False),
}


def extract_keywords(xml_tree, thesaurus):
    """Return the keywords of one MaPP thesaurus, in document order, deduped.

    The identification paths are tried in order and the first one that matches
    wins, rather than both being merged. That is what ckanext-spatial's
    `ISOElement.read_value` does with a list of `search_paths`, and these
    xpaths came from there.
    """
    for identification in _IDENTIFICATION:
        xpath = '{0}/{1}'.format(
            identification, _KEYWORDS.format(thesaurus=thesaurus))
        found = []
        for value in xml_tree.xpath(xpath, namespaces=NAMESPACES):
            value = str(value).strip()
            if value and value not in found:
                found.append(value)
        if found:
            return found
    return []


class MappHarvestPlugin(plugins.SingletonPlugin):
    plugins.implements(ISpatialHarvester, inherit=True)

    # ISpatialHarvester

    def get_package_dict(self, context, data_dict):
        package_dict = data_dict['package_dict']
        xml_tree = data_dict.get('xml_tree')
        if xml_tree is None:
            return package_dict

        for field, (thesaurus, as_list) in MAPP_VOCABULARIES.items():
            try:
                keywords = extract_keywords(xml_tree, thesaurus)
            except Exception:
                log.exception('Failed to read "%s" keywords for %s',
                              thesaurus, package_dict.get('name'))
                continue
            if not keywords:
                continue
            package_dict[field] = keywords if as_list else ', '.join(keywords)

        return package_dict

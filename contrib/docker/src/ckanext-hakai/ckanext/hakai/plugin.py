# encoding: utf-8
"""Hakai/CIOOS customisations that used to be patches inside vendored forks.

Everything here is expressed through published CKAN extension points so the
ckanext-* checkouts it replaces can go back to being pinned upstream tags.

Plugin ordering matters. In ckan.plugins, `hakai` must come *after* the
extensions it customises (notably `fluent`), because CKAN resolves template
directories and ITemplateHelpers/IValidators registrations in plugin order,
with later plugins winning.
"""
from ckan import plugins
from ckan.plugins import toolkit


class HakaiPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)

    # IConfigurer

    def update_config(self, config_):
        # Templates here override same-named templates from extensions listed
        # earlier in ckan.plugins. Currently used for the fluent text form
        # snippet.
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'assets')
        toolkit.add_resource('assets', 'ckanext-hakai')

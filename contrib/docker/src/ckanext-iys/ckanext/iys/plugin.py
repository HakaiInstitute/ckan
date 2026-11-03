# encoding: utf-8
"""IYS site customisations.

Everything that used to live on the `iys_master` branch of
ckanext-cioos_theme, re-expressed as template and asset overrides so that
branch can be retired and the checkout can track the shared CIOOS/Hakai line
again.

Unlike ckanext-mapp this is presentation only: IYS has no schema of its own
(see the README), no extra facets and no harvest-time fields, so IConfigurer
is the only interface it needs.

Plugin ordering matters: in `ckan.plugins`, `iys` must come *after*
`cioos_theme`, because CKAN resolves template directories in plugin order with
later plugins winning.
"""
from ckan import plugins
from ckan.plugins import toolkit


class IysPlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)

    # IConfigurer

    def update_config(self, config_):
        # header.html and footer.html override the same-named templates from
        # ckanext-cioos_theme, which is why `iys` must follow `cioos_theme`.
        toolkit.add_template_directory(config_, 'templates')
        # Serves /iys.css, named by `ckan.cioos.ra_css_path`.
        toolkit.add_public_directory(config_, 'public')

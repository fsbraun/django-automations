# coding=utf-8
from cms.app_base import CMSApp
from cms.apphook_pool import apphook_pool
from django.utils.translation import gettext as _


class AutomationsApphook (CMSApp):
    name = _("Django Automations")
    app_name = 'automations'

    def get_urls(self, page=None, langague=None, **kwargs):
        return ["automations.urls"]


apphook_pool.register(AutomationsApphook)

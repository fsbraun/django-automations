# coding=utf-8
from cms.app_base import CMSApp
from django.utils.translation import gettext as _

class FundApphook (CMSApp):
    name = _("Django Automations")
    app_name = 'autmations'

    def get_urls(self, page=None, langague=None, **kwargs):
        return ["automations.urls"]


# -*- coding: utf-8 -*-
from django import template
from .. import models

register = template.Library()



# @register.simple_tag(takes_context=True)
# def task_info(context, automation_class, info, debug=False):
#     get_data = context.get("request", dict()).GET
#     task_id, atm_id = get_int(get_data, "task_id"), get_int(get_data, "atm_id")
#     if automation is not None and automation.automation_class == automation_class:
#         cls = automation.get_automation_class()
#         if hasattr(cls, "public_data") and info in cls.public_data:
#             return automation.data.get(info, "")
#     return "-- Task info --" if debug else ""

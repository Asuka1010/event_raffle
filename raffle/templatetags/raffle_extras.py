from django import template


register = template.Library()


@register.filter
def get_item(obj, key):
    try:
        return obj.get(key)
    except Exception:
        return ""



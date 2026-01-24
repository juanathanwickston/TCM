"""
Custom template tags for TCM Django.
"""

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Template filter to access dictionary items by key.
    Usage: {{ mydict|get_item:key }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key, key)


@register.filter
def intcomma(value):
    """
    Format integer with commas.
    Usage: {{ number|intcomma }}
    """
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return value

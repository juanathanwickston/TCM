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


@register.filter
def split_hash(value):
    """
    Strip hash fragment from path for display.
    Usage: {{ path|split_hash }}
    
    Example:
        Input:  "HR/_General/01_Onboarding/links.txt#96eaa05d"
        Output: "HR/_General/01_Onboarding/links.txt"
    
    This is display-only. Does not affect stored data.
    """
    if value is None:
        return ''
    return str(value).split('#')[0]

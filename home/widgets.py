"""
Custom widgets for Wagtail admin.
"""

from django import forms


class InPostSearchWidget(forms.TextInput):
    """
    Custom widget for InPost paczkomat search with autocomplete.

    Usage:
        FieldPanel('point', widget=InPostSearchWidget())
    """
    template_name = 'wagtailadmin/panels/inpost_search.html'

    class Media:
        css = {
            'all': [],
        }
        js = []

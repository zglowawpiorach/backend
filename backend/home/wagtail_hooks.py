from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet
from wagtail import hooks

from .models import Product, Event


class ProductViewSet(SnippetViewSet):
    model = Product
    icon = "tag"
    menu_label = "Products"
    menu_order = 200
    add_to_admin_menu = True
    list_display = ["name", "price", "active", "created_at"]
    list_filter = ["active", "created_at"]
    search_fields = ["name", "description"]


class EventViewSet(SnippetViewSet):
    model = Event
    icon = "date"
    menu_label = "Events"
    menu_order = 201
    add_to_admin_menu = True
    list_display = ["title", "location", "start_date", "end_date", "active"]
    list_filter = ["active", "start_date"]
    search_fields = ["title", "location", "description"]


register_snippet(ProductViewSet)
register_snippet(EventViewSet)


@hooks.register('construct_main_menu')
def hide_menu_items(request, menu_items):
    menu_items[:] = [item for item in menu_items if item.name not in ['explorer', 'documents', 'snippets']]

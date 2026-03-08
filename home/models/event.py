"""Event models for artist appearances."""

from django.db import models
from wagtail.admin.panels import FieldPanel, MultiFieldPanel, InlinePanel
from wagtail.models import Orderable
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel


class EventImage(Orderable):
    """Event image with ordering support"""
    event = ParentalKey('Event', on_delete=models.CASCADE, related_name='images')
    image = models.ForeignKey(
        'wagtailimages.Image',
        on_delete=models.CASCADE,
        related_name='+'
    )

    panels = [
        FieldPanel('image'),
    ]

    def __str__(self):
        return f"{self.event.title} - Image {self.sort_order}"

    class Meta:
        verbose_name = "Zdjęcie eventu"
        verbose_name_plural = "Zdjęcia eventu"


class Event(ClusterableModel):
    """Event model for artist's local shop appearances"""
    title = models.CharField(max_length=255, verbose_name="Tytuł")
    description = models.TextField(blank=True, verbose_name="Opis")
    location = models.CharField(max_length=500, verbose_name="Lokalizacja")
    start_date = models.DateTimeField(verbose_name="Data rozpoczęcia")
    end_date = models.DateTimeField(verbose_name="Data zakończenia")
    external_url = models.URLField(blank=True, verbose_name="Link do zewnętrznej strony wydarzenia")

    active = models.BooleanField(default=True, db_index=True, verbose_name="Aktywny")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    panels = [
        FieldPanel('title'),
        FieldPanel('description'),
        FieldPanel('location'),
        FieldPanel('start_date'),
        FieldPanel('end_date'),
        FieldPanel('external_url'),
        FieldPanel('active'),
        InlinePanel('images', label="Zdjęcia", min_num=0),
    ]

    @property
    def primary_image(self):
        """Returns the first image (main event image)"""
        first_image = self.images.first()
        return first_image.image if first_image else None

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-start_date']
        verbose_name = "Event"
        verbose_name_plural = "Eventy"
        indexes = [
            models.Index(fields=['-start_date']),
            models.Index(fields=['active', '-start_date']),
        ]

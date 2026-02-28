from django.contrib import admin
from .models import Podcast, PodcastInputFile, PodcastInputURL, PodcastProcessingResult

# Register your models here.
admin.site.register(Podcast)
admin.site.register(PodcastInputFile)
admin.site.register(PodcastInputURL)
admin.site.register(PodcastProcessingResult)
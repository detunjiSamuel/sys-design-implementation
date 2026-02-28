from django.shortcuts import render
from django.http import HttpResponse
from .sample_tasks import add_job_to_queue

from .models import Podcast, PodcastInputFile, PodcastInputURL, PodcastProcessingResult
from django.db import transaction


def test_view(request):
    if request.method == "POST":
        files = request.FILES.getlist('files')
        urls = [
            request.POST.get(f'url_{i}') for i in range(1, 5) if request.POST.get(f'url_{i}')
        ]
        content = request.POST.get("content", "")

        with transaction.atomic():

            new_pod = Podcast.objects.create(
                text_content=content
            )
            for f in files:
                PodcastInputFile.objects.create(
                    podcast=new_pod,
                    file=f
                )
            for u in urls:
                PodcastInputURL.objects.create(
                    podcast=new_pod,
                    url=u
                )
        task = add_job_to_queue.delay(new_pod.id)
        new_pod.task_id = task.id
        new_pod.save()
    podcasts = Podcast.objects.all().order_by('-id')
    return render(request,  'podtasks/index.html' , {'podcasts': podcasts})

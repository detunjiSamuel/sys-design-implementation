from django.db import models


class Podcast(models.Model):
    text_content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    task_id = models.CharField(max_length=255, null=True, blank=True)
    
class PodcastInputFile(models.Model):
    podcast = models.ForeignKey(Podcast, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='podcast_input_files/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

class PodcastInputURL(models.Model):
    podcast = models.ForeignKey(Podcast, on_delete=models.CASCADE, related_name='urls')
    url = models.URLField()
    added_at = models.DateTimeField(auto_now_add=True)


class PodcastProcessingResult(models.Model):
    podcast = models.ForeignKey(Podcast, on_delete=models.CASCADE, related_name='results')
    result_text = models.TextField()
    result_file = models.FileField(upload_to='podcast_results/', null=True, blank=True)
    failure_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
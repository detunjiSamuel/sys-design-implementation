from celery import shared_task
from  podbro.podbro.main import PodcastGenerator, TTSModel
from .models import Podcast, PodcastInputFile, PodcastInputURL, PodcastProcessingResult

default_tts_mode = TTSModel.EDGE


@shared_task
def add_job_to_queue(podcast_id):
    print(f"Processing podcast with ID: {podcast_id}")

    text_content = Podcast.objects.get(id=podcast_id).text_content
    input_files = PodcastInputFile.objects.filter(podcast_id=podcast_id)
    input_urls = PodcastInputURL.objects.filter(podcast_id=podcast_id)

    # get urls from input_urls
    urls = [u.url for u in input_urls]
    # get file paths from input_files
    file_paths = [f.file.path for f in input_files]

    try:
        generator = PodcastGenerator(tts_mode=default_tts_mode)
        result_file_path = generator.create_podcast(
            urls=urls,
            files=file_paths,
            text=text_content,
            tts_model=default_tts_mode
        )

        result = PodcastProcessingResult.objects.create(
            podcast_id=podcast_id,
            result_text="Podcast generated successfully",
            result_file=result_file_path
        )
    except Exception as e:
        result = PodcastProcessingResult.objects.create(
            podcast_id=podcast_id,
            result_text="Podcast generation failed",
            failure_message=str(e)
        )
    return result.id

import nltk
import pytest


@pytest.fixture(scope="session", autouse=True)
def download_nltk_data() -> None:
    nltk.download("vader_lexicon", quiet=True)

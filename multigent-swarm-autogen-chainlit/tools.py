import requests
from bs4 import BeautifulSoup
import json
from config import EnvConfig
from functools import cache
from crawl4ai import *


@cache
def search_with_serper_api(query: str) -> str:
    """Searches Google using serper API and returns the results as a string."""

    base_url = "https://google.serper.dev/search"

    payload = json.dumps({
        "q": query,
        "gl": "in"
    })

    headers = {
        'X-API-KEY': EnvConfig.SERPER_API_KEY,
        'Content-Type': 'application/json'
    }

    response = requests.post(base_url, headers=headers, data=payload)
    # no need to convert to json here
    if response.status_code == 200:
        return response.text
    return "Error: Unable to fetch search results." + f" Status code: {response.status_code}" + response.text


async def scrape_website(url: str) -> str:
    """Scrapes the content of a website given its URL."""
    prune_filter = PruningContentFilter(
        threshold_type="dynamic",
        threshold=0.45,
        min_word_threshold=5
    )
    md_generator = DefaultMarkdownGenerator(
        content_filter=prune_filter,
        options={
            "ignore_links": True,
            "escape_html": False,
            "skip_internal_links": True,
        }
    )
    browser_config = BrowserConfig()
    run_config = CrawlerRunConfig(
        exclude_external_links=True,
        remove_overlay_elements=True,
        markdown_generator=md_generator
    )
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=run_config
        )

        return result.fit_markdown  # type: ignore
    return "Error: Unable to scrape website."


def search_with_google(query: str) -> str:

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }
    response = requests.get(
        f"https://www.google.com/search?q={query}", headers=headers)

    if response.status_code != 200:
        return "Error: Unable to fetch search results." + f" Status code: {response.status_code}"
    return response.text  # parsing is a pain and unreliable

    soup = BeautifulSoup(response.text, 'html.parser')

    results = []

    for g in soup.find_all('div', class_='tF2Cxc'):
        title = g.find('h3').text if g.find('h3') else 'No title'
        link = g.find('a')['href'] if g.find('a') else 'No link'
        snippet = g.find('span', class_='aCOpRe').text if g.find(
            'span', class_='aCOpRe') else 'No snippet'
        results.append(f"Title: {title}\nLink: {link}\nSnippet: {snippet}\n")

    return "\n".join(results)

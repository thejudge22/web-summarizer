# ABOUTME: Handles web page content fetching and extraction.
# ABOUTME: Used for extracting text content from web pages.

import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from requests.exceptions import RequestException

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def is_valid_url(url_string: str) -> bool:
    """Basic URL validation focusing on scheme and network location."""
    if not url_string:
        return False
    try:
        parsed = urlparse(url_string)
        is_valid = all([parsed.scheme in ['http', 'https'], parsed.netloc])
        # Basic SSRF mitigation placeholder - enhance if needed
        # e.g., check against private IP ranges
        return is_valid
    except ValueError:
        return False

def fetch_page_content(url: str) -> str | None:
    """Fetches URL content and extracts text using BeautifulSoup."""
    logging.info(f"Attempting to fetch content from: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 SummarizerBot/1.0'
    }
    try:
        logging.info(f"Sending HTTP request to {url}")
        # Increased timeout from 20s to 45s for larger pages
        response = requests.get(url, headers=headers, timeout=45, allow_redirects=True)
        response.raise_for_status()
        logging.info(f"Received response from {url} ({len(response.text)} bytes)")

        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' not in content_type:
            logging.warning(f"Non-HTML content type received: {content_type} for URL: {url}")
            return None

        logging.info(f"Parsing HTML content with BeautifulSoup")
        soup = BeautifulSoup(response.text, 'lxml')
        logging.info(f"Removing script and style tags")
        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()

        body = soup.find('body')
        if body:
            logging.info(f"Extracting text from body tag")
            text = body.get_text(separator=' ', strip=True)
            text = ' '.join(text.split())

            # Limit content size to prevent timeouts
            MAX_CHARS = 100000  # Limit to 100K characters
            if len(text) > MAX_CHARS:
                logging.warning(f"Content too large ({len(text)} chars). Truncating to {MAX_CHARS} characters.")
                text = text[:MAX_CHARS] + "... [Content truncated due to size]"

            logging.info(f"Successfully extracted {len(text)} characters from {url}")
            return text
        else:
            logging.warning(f"Could not find body tag in content from {url}")
            return None

    except requests.exceptions.Timeout:
        logging.error(f"Request timed out for URL {url} (took longer than 45 seconds)")
        return None
    except requests.exceptions.ConnectionError:
        logging.error(f"Connection error for URL {url} - site may be down or blocking requests")
        return None
    except RequestException as e:
        logging.error(f"Request failed for URL {url}: {e}")
        return None
    except Exception as e:
        logging.error(f"Error parsing content for URL {url}: {e}")
        return None
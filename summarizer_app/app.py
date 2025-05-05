import os
import requests
import logging
import functools
import re # For regex matching (YouTube video ID)
import json # For parsing JSON responses, especially errors
import markdown # Import the markdown library
import uuid # For generating unique summary IDs
from tempfile import gettempdir # For temporary storage
from bs4 import BeautifulSoup
import google.generativeai as genai
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound # YouTube transcript fetching
from flask import Flask, request, render_template, abort, flash, get_flashed_messages, session, redirect, url_for, jsonify # Added jsonify
from dotenv import load_dotenv
from urllib.parse import urlparse
from requests.exceptions import RequestException
from werkzeug.security import generate_password_hash, check_password_hash

# --- Configuration ---
load_dotenv() # Load environment variables from .env

app = Flask(__name__)

# --- Secret Key Configuration (CRITICAL for session persistence) ---
flask_secret_key = os.environ.get("FLASK_SECRET_KEY")
if flask_secret_key:
    app.secret_key = flask_secret_key
    logging.info("Flask secret key loaded from FLASK_SECRET_KEY environment variable.")
else:
    # Fallback to urandom ONLY if the environment variable is not set
    app.secret_key = os.urandom(24)
    logging.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    logging.warning("!!! FLASK_SECRET_KEY environment variable not set.        !!!")
    logging.warning("!!! Falling back to a temporary, random secret key.       !!!")
    logging.warning("!!! User sessions (login state) WILL NOT PERSIST          !!!")
    logging.warning("!!! across application restarts or worker reloads.        !!!")
    logging.warning("!!! Set FLASK_SECRET_KEY in your .env file for proper     !!!")
    logging.warning("!!! session handling.                                     !!!")
    logging.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Credentials ---
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD_PLAIN = os.getenv("ADMIN_PASSWORD")
ADMIN_PASSWORD_HASH = None

if not ADMIN_USERNAME or not ADMIN_PASSWORD_PLAIN:
    app.logger.error("FATAL: ADMIN_USERNAME or ADMIN_PASSWORD not found in environment variables.")
    # In a real app, you might exit or raise an exception
else:
    # Hash the password on startup for comparison
    ADMIN_PASSWORD_HASH = generate_password_hash(ADMIN_PASSWORD_PLAIN)
    app.logger.info(f"Admin user '{ADMIN_USERNAME}' loaded.")


# Configure Gemini API
gemini_api_key = os.getenv("GEMINI_API_KEY")
# Get model name from environment variable, default to 'gemini-2.0-flash'
gemini_model_name = os.getenv("GEMINI_MODEL_NAME", 'gemini-2.0-flash')

if not gemini_api_key:
    app.logger.error("FATAL: GEMINI_API_KEY not found in environment variables.")
    # Allow app to run but log error, LLM checks will fail later
    llm = None
else:
    try:
        genai.configure(api_key=gemini_api_key)
        llm = genai.GenerativeModel(gemini_model_name)
        app.logger.info(f"Gemini API configured successfully with model: {gemini_model_name}.")
    except Exception as e:
        app.logger.error(f"Failed to configure Gemini API with model '{gemini_model_name}': {e}")
        llm = None # Ensure llm is None if configuration fails

# --- Karakeep / Hoarder Configuration ---
KARAKEEP_API_URL = os.getenv("KARAKEEP_API_URL")
KARAKEEP_API_KEY = os.getenv("KARAKEEP_API_KEY")
KARAKEEP_LIST_NAME = os.getenv("KARAKEEP_LIST_NAME")

if not all([KARAKEEP_API_URL, KARAKEEP_API_KEY, KARAKEEP_LIST_NAME]):
    app.logger.warning("Karakeep integration details (API URL, Key, or List Name) missing in environment variables. Sending to Karakeep will be disabled.")
    KARAKEEP_ENABLED = False
else:
    # Basic URL format check (remove trailing slash)
    KARAKEEP_API_URL = KARAKEEP_API_URL.rstrip('/')
    if not KARAKEEP_API_URL.endswith('/api/v1'):
         app.logger.warning(f"KARAKEEP_API_URL ('{KARAKEEP_API_URL}') does not end with '/api/v1'. Ensure this is the correct base path.")
    KARAKEEP_ENABLED = True
    app.logger.info(f"Karakeep integration enabled. Target List: '{KARAKEEP_LIST_NAME}', API URL: '{KARAKEEP_API_URL}'")

# --- Authentication Decorator ---

def login_required(view):
    """View decorator that redirects anonymous users to the login page."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'logged_in' not in session:
            flash("Please log in to access this page.", "info")
            # Store the requested URL in the session to redirect after login
            next_url = request.url
            return redirect(url_for('login', next=next_url))
        return view(**kwargs)
    return wrapped_view

# --- Helper Functions ---

def get_temp_summary_path(summary_id):
    """Get the path to the temporary summary file."""
    return os.path.join(gettempdir(), f"web_summarizer_{summary_id}.json")

def store_summary_data(summary_data):
    """Store summary data in a temporary file and return a unique ID."""
    summary_id = str(uuid.uuid4())
    temp_path = get_temp_summary_path(summary_id)
    
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(summary_data, f, ensure_ascii=False)
    
    return summary_id

def retrieve_summary_data(summary_id):
    """Retrieve summary data from a temporary file and delete the file."""
    temp_path = get_temp_summary_path(summary_id)
    
    if not os.path.exists(temp_path):
        return None
    
    try:
        with open(temp_path, 'r', encoding='utf-8') as f:
            summary_data = json.load(f)
        
        # Clean up the temp file
        os.remove(temp_path)
        return summary_data
    except Exception as e:
        app.logger.error(f"Error retrieving summary data: {e}")
        # If we can't read the file, try to clean it up anyway
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        return None

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

def is_youtube_url(url: str) -> str | None:
    """Checks if the URL is a YouTube video URL and returns the video ID if it is."""
    # Regex patterns to match various YouTube URL formats and extract video ID
    patterns = [
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})',        # Standard watch URL
        r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([a-zA-Z0-9_-]{11})',                  # Shortened youtu.be URL
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',       # Embed URL
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/v\/([a-zA-Z0-9_-]{11})',           # v/ URL
        # Add more patterns if needed for other formats like shorts, playlists with video context etc.
        # Example for shorts (adjust if needed): r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/shorts\/([a-zA-Z0-9_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1) # Return the video ID (first capture group)
    return None # Not a recognized YouTube video URL format

def fetch_youtube_transcript(video_id: str) -> str | None:
    """Fetches the transcript for a given YouTube video ID."""
    app.logger.info(f"Attempting to fetch transcript for YouTube video ID: {video_id}")
    try:
        # Add timeout handling using a simple timeout context manager
        import signal
        
        class TimeoutException(Exception):
            pass
            
        def timeout_handler(signum, frame):
            raise TimeoutException("Transcript fetching timed out")
            
        # Set a 60-second timeout for transcript operations
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(60)
        
        app.logger.info(f"Fetching available transcripts for {video_id}")
        # Fetch available transcripts
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            app.logger.info(f"Successfully retrieved transcript list for {video_id}")
        except Exception as e:
            app.logger.error(f"Failed to retrieve transcript list: {e}")
            signal.alarm(0)  # Cancel the alarm
            raise

        # Try to find a manually created transcript first, otherwise get a generated one
        # Prioritize English ('en') or common variants if available
        preferred_languages = ['en', 'en-US', 'en-GB']
        transcript = None
        try:
            # Check manually created transcripts first
            app.logger.info(f"Looking for manually created transcript in preferred languages")
            transcript = transcript_list.find_manually_created_transcript(preferred_languages)
            app.logger.info(f"Found manually created transcript for {video_id}.")
        except NoTranscriptFound:
            app.logger.info(f"No manual transcript found for {video_id}, checking generated.")
            try:
                # Check generated transcripts
                app.logger.info(f"Looking for auto-generated transcript in preferred languages")
                transcript = transcript_list.find_generated_transcript(preferred_languages)
                app.logger.info(f"Found auto-generated transcript for {video_id}.")
            except NoTranscriptFound:
                app.logger.warning(f"No suitable English transcript found for {video_id}. Checking any language.")
                # If no preferred language found, fetch the first available transcript regardless of language
                try:
                    app.logger.info(f"Attempting to use first available transcript in any language")
                    first_transcript = list(transcript_list)[0]  # Get the first Transcript object
                    transcript = first_transcript
                    app.logger.info(f"Found transcript in language: {transcript.language} for {video_id}.")
                except IndexError:
                    app.logger.error(f"Transcript list seems empty for video ID: {video_id}")
                    signal.alarm(0)  # Cancel the alarm
                    return None

        # Fetch the actual transcript data
        app.logger.info(f"Fetching actual transcript data for {video_id}")
        transcript_data = transcript.fetch()
        app.logger.info(f"Successfully fetched raw transcript data ({len(transcript_data)} segments)")

        # Format the transcript data into a single string (robustly)
        texts = []
        for item in transcript_data:
            if isinstance(item, dict):
                texts.append(item.get('text', ''))  # Use .get for safety if 'text' key is missing
            elif hasattr(item, 'text'):
                # If it's an object with a 'text' attribute
                texts.append(getattr(item, 'text', ''))
            else:
                # Log if the item structure is unexpected
                app.logger.warning(f"Unexpected item type in transcript data: {type(item)}")

        full_transcript = " ".join(texts)
        # Clean up potential multiple spaces resulting from joining
        full_transcript = ' '.join(full_transcript.split())

        # Limit transcript size to prevent timeouts in processing
        MAX_TRANSCRIPT_CHARS = 75000  # 75K characters for longer videos
        if len(full_transcript) > MAX_TRANSCRIPT_CHARS:
            app.logger.warning(f"Transcript too large ({len(full_transcript)} chars). Truncating to {MAX_TRANSCRIPT_CHARS}.")
            full_transcript = full_transcript[:MAX_TRANSCRIPT_CHARS] + "... [Transcript truncated due to size]"

        if not full_transcript:
            app.logger.warning(f"Formatted transcript is empty for video ID: {video_id}")
            signal.alarm(0)  # Cancel the alarm
            return None

        app.logger.info(f"Successfully processed transcript (length: {len(full_transcript)}) for {video_id}")
        
        # Cancel the timeout alarm
        signal.alarm(0)
        return full_transcript

    except TimeoutException:
        app.logger.error(f"Timed out while fetching transcript for YouTube video ID: {video_id}")
        return None
    except TranscriptsDisabled:
        app.logger.warning(f"Transcripts are disabled for YouTube video ID: {video_id}")
        return None
    except NoTranscriptFound:
        app.logger.warning(f"Could not find any transcript for YouTube video ID: {video_id}")
        return None
    except Exception as e:
        # Catch potential network errors or other API issues
        app.logger.error(f"Error fetching YouTube transcript for video ID {video_id}: {e}")
        return None


def fetch_page_content(url: str) -> str | None:
    """Fetches URL content and extracts text using BeautifulSoup."""
    app.logger.info(f"Attempting to fetch content from: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 SummarizerBot/1.0'
    }
    try:
        app.logger.info(f"Sending HTTP request to {url}")
        # Increased timeout from 20s to 45s for larger pages
        response = requests.get(url, headers=headers, timeout=45, allow_redirects=True)
        response.raise_for_status()
        app.logger.info(f"Received response from {url} ({len(response.text)} bytes)")

        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' not in content_type:
            app.logger.warning(f"Non-HTML content type received: {content_type} for URL: {url}")
            return None

        app.logger.info(f"Parsing HTML content with BeautifulSoup")
        soup = BeautifulSoup(response.text, 'lxml')
        app.logger.info(f"Removing script and style tags")
        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()

        body = soup.find('body')
        if body:
            app.logger.info(f"Extracting text from body tag")
            text = body.get_text(separator=' ', strip=True)
            text = ' '.join(text.split())
            
            # Limit content size to prevent timeouts
            MAX_CHARS = 100000  # Limit to 100K characters
            if len(text) > MAX_CHARS:
                app.logger.warning(f"Content too large ({len(text)} chars). Truncating to {MAX_CHARS} characters.")
                text = text[:MAX_CHARS] + "... [Content truncated due to size]"
            
            app.logger.info(f"Successfully extracted {len(text)} characters from {url}")
            return text
        else:
            app.logger.warning(f"Could not find body tag in content from {url}")
            return None

    except requests.exceptions.Timeout:
        app.logger.error(f"Request timed out for URL {url} (took longer than 45 seconds)")
        return None
    except requests.exceptions.ConnectionError:
        app.logger.error(f"Connection error for URL {url} - site may be down or blocking requests")
        return None
    except RequestException as e:
        app.logger.error(f"Request failed for URL {url}: {e}")
        return None
    except Exception as e:
        app.logger.error(f"Error parsing content for URL {url}: {e}")
        return None


def get_summary_from_llm(content: str, source_url: str, is_youtube: bool = False) -> str | None:
    """Sends content (web page or YT transcript) to Gemini API for summarization."""
    if not llm:
        app.logger.error("LLM client not initialized. Cannot generate summary.")
        return None
    if not content:
        app.logger.warning("No content provided to summarize.")
        return None

    # Track start time for operation timing
    import time
    start_time = time.time()
    
    # Ensure content isn't too large for API processing
    MAX_CONTENT_LENGTH = 80000  # 80K chars should be safe for most LLM APIs
    if len(content) > MAX_CONTENT_LENGTH:
        app.logger.warning(f"Content too large for LLM API ({len(content)} chars). Truncating to {MAX_CONTENT_LENGTH} chars.")
        content = content[:MAX_CONTENT_LENGTH] + "... [Content truncated due to size]"
    
    app.logger.info(f"Preparing to send content (length: {len(content)}, type: {'YouTube' if is_youtube else 'WebPage'}) to Gemini")

    if is_youtube:
        prompt = f"""You are a helpful AI assistant that connects to YouTube videos, downloads their transcripts, and provides detailed summaries. Your goal is to create comprehensive and easy-to-understand summaries, highlighting all key points discussed.
Here's how you should operate:
 Receive a YouTube Video URL {source_url}.
 Download the transcript. If a transcript is unavailable, inform the user and cease operation.
 Analyze the transcript to identify key themes and arguments.
 Summarize the video's content, ensuring a comprehensive overview.
 Structure the summary using bullet points where helpful, especially when listing arguments, steps, or different viewpoints.
Use bold or other formatting for bullet points or where it makes sense, for emphasis or to highlight important topics.  Make sure any sub headings are also bold formatted or made to stand out.
 Use clear and concise language.
 Present the information in a logical order.

Transcript:
---
{content}
---

Summary:"""
    else:
        prompt = f"""Take the URL that was passed over and summarize it.  {source_url}

Aim to cover the topic thoroughly by exploring various aspects and perspectives.

Response Structure:
Make sure the story is thoroughly expanded, include snippets from the article or page if appropriate.
Provide comprehensive coverage of the topic, including detailed information and multiple perspectives.
Use clear headings and bullet points.
Highlight key takeaways.


Content:
---
{content}
---

Summary:"""

    app.logger.info(f"Sending request to Gemini API (prompt length: {len(prompt)})")
    
    try:
        # Import necessary timeout handling
        import concurrent.futures
        from concurrent.futures import TimeoutError as FuturesTimeoutError
        import google.api_core.exceptions
        
        # Set proper generation config (without invalid timeout parameter)
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95
        }
        
        # Use ThreadPoolExecutor to implement timeout
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Create a future for the API call
            future = executor.submit(lambda: llm.generate_content(prompt, generation_config=generation_config))
            
            try:
                # Wait for the result with a timeout
                app.logger.info("Starting LLM API call with 90 second timeout")
                response = future.result(timeout=90)  # 90 second timeout
                
                elapsed_time = time.time() - start_time
                app.logger.info(f"Gemini API call completed in {elapsed_time:.2f} seconds")
                
                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    summary = response.candidates[0].content.parts[0].text
                    app.logger.info(f"Successfully generated summary from Gemini ({len(summary)} chars)")
                    return summary.strip()
                else:
                    try:
                        finish_reason = response.candidates[0].finish_reason if response.candidates else "Unknown"
                        safety_ratings = response.prompt_feedback.safety_ratings if response.prompt_feedback else "N/A"
                        app.logger.error(f"Gemini API returned unexpected or empty response. Finish Reason: {finish_reason}, Safety: {safety_ratings}")
                    except Exception:
                        app.logger.error(f"Gemini API returned unexpected or empty response. Could not parse details.")
                    return None
                    
            except FuturesTimeoutError:
                app.logger.error("Gemini API request timed out (exceeded 90 seconds)")
                # Cancel the future if possible
                future.cancel()
                return None
            except google.api_core.exceptions.DeadlineExceeded:
                app.logger.error("Gemini API request exceeded deadline")
                return None
                
    except Exception as e:
        elapsed_time = time.time() - start_time
        app.logger.error(f"Error calling Gemini API after {elapsed_time:.2f} seconds: {e}")
        return None

def get_short_title_from_llm(summary_text: str) -> str | None:
    """Generates a short title ( < 10 words) for the summary using the LLM."""
    if not llm:
        app.logger.error("LLM client not initialized. Cannot generate title.")
        return None
    if not summary_text:
        app.logger.warning("No summary text provided to generate title from.")
        return None

    app.logger.info("Requesting short title generation from LLM.")
    prompt = f"""Please summarize the following text into a concise title of less than 10 words. Output only the title itself, without any introductory phrases like "Title:".

Text to summarize into a title:
---
{summary_text[:2000]}
---

Concise Title (less than 10 words):""" # Limit input length just in case

    try:
        # Import necessary timeout handling
        import concurrent.futures
        from concurrent.futures import TimeoutError as FuturesTimeoutError
        
        # Set proper generation config
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95
        }
        
        # Use ThreadPoolExecutor to implement timeout
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Create a future for the API call
            future = executor.submit(lambda: llm.generate_content(prompt, generation_config=generation_config))
            
            try:
                # Wait for the result with a timeout
                app.logger.info("Starting LLM title generation with 30 second timeout")
                response = future.result(timeout=30)  # 30 second timeout for title generation
                
                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    title = response.candidates[0].content.parts[0].text.strip()
                    # Basic cleanup: remove potential quotes, ensure reasonable length
                    title = title.strip('"\'')
                    if len(title.split()) > 12: # Allow slightly more than 10 just in case
                        app.logger.warning(f"LLM generated title longer than expected: '{title}'. Truncating.")
                        title = " ".join(title.split()[:10]) + "..."
                    app.logger.info(f"Successfully generated short title: '{title}'")
                    return title
                else:
                    app.logger.error(f"LLM failed to generate a short title. Response: {response}")
                    return None
                    
            except FuturesTimeoutError:
                app.logger.error("Gemini API title generation timed out (exceeded 30 seconds)")
                # Cancel the future if possible
                future.cancel()
                return None
                
    except Exception as e:
        app.logger.error(f"Error calling Gemini API for title generation: {e}")
        return None

def get_karakeep_list_id(api_url: str, api_key: str, list_name: str) -> str | None:
    """Fetches the ID of a Karakeep list by its name."""
    if not KARAKEEP_ENABLED:
        app.logger.warning("Karakeep is disabled, cannot fetch list ID.")
        return None

    list_endpoint_url = f"{api_url}/lists" # Define the specific URL being called here
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json'
    }
    app.logger.info(f"Attempting to find Karakeep list ID for: '{list_name}' via GET {list_endpoint_url}")

    try: # <<< Add the missing try block here
        response = requests.get(list_endpoint_url, headers=headers, timeout=15)
        response.raise_for_status()
        response_data = response.json()

        actual_list_data = None

        if isinstance(response_data, list):
            # Case 1: API returns the list directly
            app.logger.info("Karakeep /lists endpoint returned a direct list.")
            actual_list_data = response_data
        elif isinstance(response_data, dict):
            # Case 2: API returns a dictionary, look for nested list
            app.logger.info("Karakeep /lists endpoint returned a dictionary. Checking common keys for list data...")
            possible_keys = ['data', 'results', 'items', 'lists'] # Common keys for list data
            for key in possible_keys:
                if key in response_data and isinstance(response_data[key], list):
                    app.logger.info(f"Found list data under the key '{key}'.")
                    actual_list_data = response_data[key]
                    break # Found it, stop looking
            if actual_list_data is None:
                 app.logger.error(f"Karakeep /lists response was a dictionary, but could not find list data under expected keys ({', '.join(possible_keys)}). Dictionary keys: {list(response_data.keys())}")
                 return None
        else:
            # Case 3: Unexpected format
            app.logger.error(f"Unexpected response format from Karakeep /lists endpoint. Expected a list or a dict containing a list, got: {type(response_data)}")
            return None

        # Now process the actual_list_data if found
        if actual_list_data is not None:
            for lst in actual_list_data:
                if isinstance(lst, dict) and lst.get('name') == list_name:
                    list_id = lst.get('id')
                    if list_id:
                        app.logger.info(f"Found Karakeep list '{list_name}' with ID: {list_id}")
                        return str(list_id)  # Ensure it's a string
                    else:
                        app.logger.error(f"List '{list_name}' found but has no 'id' field in response item: {lst}")
                        # Continue searching in case there are multiple lists with the same name (unlikely but possible)
            # If loop finishes without finding the list
            app.logger.warning(f"Karakeep list named '{list_name}' not found in the response data.")
            return None
        else:
             # This case should technically be caught above, but for safety:
             app.logger.error("Failed to extract actual list data from Karakeep response.")
             return None
    # End of the main processing logic inside the try block

    except RequestException as e:
        # This except block now correctly corresponds to the try above
        app.logger.error(f"Error requesting Karakeep lists from {list_endpoint_url}: {e}") # Use the correct URL variable
        return None
    except Exception as e:
        # This except block also corresponds to the try above
        app.logger.error(f"Error processing Karakeep lists response: {e}")
        return None

def send_summary_to_karakeep(api_url: str, api_key: str, list_id: str, title: str, markdown_summary: str, original_url: str) -> bool:
    """Sends the summary as a new item to a specific Karakeep list."""
    if not KARAKEEP_ENABLED:
        app.logger.warning("Karakeep is disabled, cannot send summary.")
        return False

    # Karakeep requires a 2-step process: POST to /bookmarks, then PUT to /lists/{id}/bookmarks/{id}
    create_bookmark_url = f"{api_url}/bookmarks"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }

    # Step 1: Create the global bookmark
    # Payload should NOT include list_id here.
    create_payload = {
        "title": title[:255], # Ensure title doesn't exceed potential DB limits
        "text": markdown_summary,
        "type": "text",
        "archived": False,
        "favourited": False,
        "url": original_url,
        "note": f"Summary generated from: {original_url}",
        # No list_id here
    }
    app.logger.info(f"Attempting Step 1: POST summary to Karakeep (Endpoint: {create_bookmark_url}), title '{title}'")

    try:
        response_create = requests.post(create_bookmark_url, headers=headers, json=create_payload, timeout=20)
        response_create.raise_for_status()
        created_bookmark_data = response_create.json()
        new_bookmark_id = created_bookmark_data.get('id')

        if not new_bookmark_id:
            app.logger.error(f"ERROR: Could not extract 'id' from POST /bookmarks response. Response: {str(created_bookmark_data)[:500]}...")
            return False

        new_bookmark_id = str(new_bookmark_id) # Ensure it's a string
        app.logger.info(f"Successfully Step 1: Created Bookmark ID {new_bookmark_id}")

        # Step 2: Link the new bookmark to the target list
        link_url = f"{api_url}/lists/{list_id}/bookmarks/{new_bookmark_id}"
        app.logger.info(f"Attempting Step 2: Link Bookmark ID {new_bookmark_id} to List ID {list_id} (PUT {link_url})")

        # Use PUT with an empty JSON body to link
        response_link = requests.put(link_url, headers=headers, json={}, timeout=15) # Empty JSON payload {}
        response_link.raise_for_status()

        app.logger.info(f"Successfully Step 2: Linked Bookmark ID {new_bookmark_id} to List ID {list_id}. Status: {response_link.status_code}")
        return True

    except RequestException as e:
        # Log specific details based on which step failed
        failed_url = e.request.url if e.request else "Unknown URL"
        failed_method = e.request.method if e.request else "Unknown Method"
        app.logger.error(f"Error during Karakeep interaction ({failed_method} {failed_url}): {e}")
        if hasattr(e, 'response') and e.response is not None:
            app.logger.error(f"Response Status: {e.response.status_code}")
            try:
                error_details = e.response.json()
                app.logger.error(f"Response JSON: {error_details}")
            except Exception as json_e: # Added missing except block
                app.logger.error(f"Could not parse error response as JSON: {json_e}")
                app.logger.error(f"Raw Response Text: {e.response.text[:500]}...") # Log raw text instead
        # The general error log below might be redundant now, but keep it for broader issues
        app.logger.error(f"Unexpected error during Karakeep summary sending (outside RequestException handling): {e}", exc_info=True) # Clarified log message
        return False
    except Exception as e: # Catch other potential errors in the function
        app.logger.error(f"Unexpected error during Karakeep summary sending: {e}", exc_info=True) # Include traceback
        return False


# --- Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    # If user is already logged in, redirect them away from login page
    if 'logged_in' in session:
        flash("You are already logged in.", "info")
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        next_url = request.form.get('next') # Get redirect target from hidden field

        # Validate credentials (ensure hash was created)
        if ADMIN_PASSWORD_HASH and username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['logged_in'] = True
            session['username'] = username
            app.logger.info(f"User '{username}' logged in successfully.")
            flash(f"Welcome back, {username}!", "success")

            # Redirect to the originally requested page or index
            # Basic validation for the next_url to prevent open redirect
            # A more robust check would parse the URL and ensure it has the same host/origin.
            if next_url and urlparse(next_url).netloc == urlparse(request.host_url).netloc:
                 app.logger.info(f"Redirecting logged in user to intended destination: {next_url}")
                 return redirect(next_url)
            else:
                 app.logger.info(f"Redirecting logged in user to index (no valid 'next' URL provided or external URL detected).")
                 return redirect(url_for('index'))
        else:
            app.logger.warning(f"Failed login attempt for username: {username}")
            flash("Invalid username or password.", "error")
            # No redirect here, fall through to render login template again

    # For GET request or failed POST, render login form
    # Pass the 'next' parameter to the template if it exists in the GET request args
    return render_template('login.html', next=request.args.get('next', ''))


@app.route('/logout')
def logout():
    """Logs the user out."""
    session.pop('logged_in', None)
    session.pop('username', None)
    app.logger.info("User logged out.")
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))


@app.route('/', methods=['GET']) # Only handle GET requests now
@login_required # Protect this route
def index():
    """Handles displaying the form and pre-filling from query params (e.g., bookmarklet)."""
    target_url = request.args.get('url') # Check for URL from query param
    if target_url:
        app.logger.info(f"Received URL via GET parameter: {target_url}")
        # Basic validation before pre-filling
        if not is_valid_url(target_url):
             app.logger.warning(f"Invalid URL format in GET parameter: {target_url}")
             flash("Invalid URL format provided in the link. Please check the URL.", "error")
             target_url = None # Don't pre-fill invalid URL

    # Render the main form page
    # Pass the potentially pre-filled URL and username
    return render_template('index.html', submitted_url=target_url, username=session.get('username'))


@app.route('/summarize_ajax', methods=['POST'])
@login_required
def summarize_ajax():
    """Handles AJAX request for summarization."""
    # Log request starting time for tracking long-running operations
    import time
    start_time = time.time()
    
    if not request.is_json:
        app.logger.warning("Received non-JSON request on /summarize_ajax endpoint.")
        return jsonify({'status': 'error', 'message': 'Invalid request format. Expected JSON.'}), 400

    data = request.get_json()
    target_url = data.get('url')
    app.logger.info(f"Received URL via AJAX POST: {target_url}")

    if not target_url:
        app.logger.warning("No URL provided in AJAX request.")
        return jsonify({'status': 'error', 'message': 'No URL provided.'}), 400

    # Validate the URL
    if not is_valid_url(target_url):
        app.logger.warning(f"Invalid URL format provided via AJAX: {target_url}")
        return jsonify({'status': 'error', 'message': 'Invalid URL format. Please include http:// or https://'}), 400

    content = None
    summary = None
    is_youtube = False
    video_id = is_youtube_url(target_url)

    try:
        if video_id:
            # It's a YouTube URL
            is_youtube = True
            app.logger.info(f"Detected YouTube URL with video ID: {video_id}")
            content = fetch_youtube_transcript(video_id)
            if content is None:
                app.logger.error(f"Failed to fetch transcript for YouTube URL: {target_url}")
                return jsonify({'status': 'error', 'message': 'Could not fetch transcript. Transcripts might be disabled or unavailable.'}), 400
            else:
                summary = get_summary_from_llm(content, target_url, is_youtube=True)
        else:
            # It's a regular web page URL
            app.logger.info(f"Processing as standard web page: {target_url}")
            content = fetch_page_content(target_url)
            if content is None:
                app.logger.error(f"Failed to fetch or process content for web URL: {target_url}")
                return jsonify({'status': 'error', 'message': 'Could not fetch or process content. Site might be inaccessible or blocking requests.'}), 400
            else:
                 summary = get_summary_from_llm(content, target_url, is_youtube=False)

        # Check if summary generation failed
        if summary is None:
            app.logger.error(f"Failed to get summary from LLM for URL: {target_url} (Type: {'YouTube' if is_youtube else 'WebPage'})")
            return jsonify({'status': 'error', 'message': 'Failed to generate summary. LLM might be unavailable or had an issue.'}), 500 # Internal server error likely

        # Success! Generate HTML and store results in temporary file
        app.logger.info(f"Successfully generated summary (Markdown) for: {target_url}")
        summary_html = markdown.markdown(summary) # Convert Markdown to HTML
        app.logger.info(f"Converted summary to HTML.")

        # Store the summary data in a temporary file and keep just the ID in the session
        summary_data = {
            'original_url': target_url,
            'summary_html': summary_html,
            'summary_markdown': summary # Store markdown for Karakeep if needed later
        }
        
        try:
            # Store data in temp file and get ID
            summary_id = store_summary_data(summary_data)
            # Store only the ID in session (very small)
            session['summary_id'] = summary_id
            app.logger.info(f"Stored summary with ID {summary_id} in temporary file")
            
            return jsonify({'status': 'success', 'redirect_url': url_for('show_summary')})
        except Exception as e:
            app.logger.error(f"Failed to store summary data: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': 'Server error: Failed to store summary data.'}), 500

    except Exception as e:
        # Catch any unexpected errors during the process
        app.logger.error(f"Unexpected error during summarization for {target_url}: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'An unexpected server error occurred.'}), 500


@app.route('/show_summary')
@login_required
def show_summary():
    """Displays the summary result retrieved from temporary storage."""
    # Get the summary ID from session
    summary_id = session.pop('summary_id', None)

    if not summary_id:
        app.logger.warning("Accessed /show_summary without summary ID in session.")
        flash("No summary data found. Please generate a summary first.", "info")
        return redirect(url_for('index'))

    # Retrieve the summary data using the ID
    summary_data = retrieve_summary_data(summary_id)

    if not summary_data:
        app.logger.warning(f"Could not retrieve summary data for ID: {summary_id}")
        flash("Summary data could not be retrieved. Please try again.", "error")
        return redirect(url_for('index'))

    app.logger.info(f"Successfully retrieved summary data for ID: {summary_id}")

    # Render the summary template with the retrieved data
    return render_template(
        'summary.html',
        original_url=summary_data.get('original_url'),
        summary_html=summary_data.get('summary_html'),
        summary_markdown=summary_data.get('summary_markdown'), # Pass markdown to template
        username=session.get('username') # Pass username for logout link
    )


# Optional: Add a simple health check endpoint (unprotected)
@app.route('/health')
def health_check():
    # Basic check - more elaborate checks could test LLM connectivity etc.
    return "OK", 200


@app.route('/send_to_karakeep', methods=['POST'])
@login_required # Protect this route
def send_to_karakeep():
    """Handles sending the current summary to Karakeep."""
    if not KARAKEEP_ENABLED:
        flash("Karakeep integration is not enabled.", "error")
        return redirect(url_for('index')) # Or redirect back to summary?

    original_url = request.form.get('original_url')
    if not original_url:
        flash("Missing original URL for Karakeep submission.", "error")
        # Redirect back to the summary page if possible, otherwise index
        # Since we don't have summary data here easily, redirect to index.
        return redirect(url_for('index'))

    # Retrieve the summary markdown directly from the submitted form
    summary_markdown = request.form.get('summary_markdown')

    if not summary_markdown:
        # This should ideally not happen if the form is correct, but handle it just in case
        app.logger.error("Missing summary_markdown in form submission to Karakeep.")
        flash("Could not find summary content to send to Karakeep.", "error")
        # Redirect back to index as we don't have the context to show the summary page again easily
        return redirect(url_for('index'))

    app.logger.info("Received summary markdown from form for Karakeep submission.")

    # Proceed with Karakeep submission using summary_markdown
    karakeep_title = get_short_title_from_llm(summary_markdown)

    if not karakeep_title:
        flash("Failed to generate title for Karakeep.", "error")
        return redirect(url_for('index')) # Or redirect back to summary?

    karakeep_list_id = get_karakeep_list_id(KARAKEEP_API_URL, KARAKEEP_API_KEY, KARAKEEP_LIST_NAME)

    if not karakeep_list_id:
        flash(f"Could not find Karakeep list '{KARAKEEP_LIST_NAME}'.", "error")
        return redirect(url_for('index')) # Or redirect back to summary?

    karakeep_sent_ok = send_summary_to_karakeep(
        KARAKEEP_API_URL, KARAKEEP_API_KEY, karakeep_list_id,
        karakeep_title, summary_markdown, original_url # Use summary_markdown here
    )

    if karakeep_sent_ok:
        flash(f"Summary successfully sent to Karakeep list '{KARAKEEP_LIST_NAME}'.", "success")
    else:
        flash(f"Failed to send summary to Karakeep list '{KARAKEEP_LIST_NAME}'. Check logs.", "error")

    # Redirect back to the summary page (or index)
    # To redirect back to the summary page, you'd need to pass the summary content
    # in the redirect, which isn't standard for GET redirects.
    # Redirecting to index is simpler for now.
    return redirect(url_for('index'))

if __name__ == '__main__':
    # This block is NOT used when running with Gunicorn/Docker CMD
    # It's only for direct execution like `python app.py`
    # Use a more secure secret key for development if needed
    # app.secret_key = 'dev_secret_key'
    app.run(host='0.0.0.0', port=5000, debug=True)
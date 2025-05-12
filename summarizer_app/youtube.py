# ABOUTME: Handles YouTube URL detection, transcript fetching, and related helpers.
# ABOUTME: Used for extracting transcripts from YouTube videos.

import re
import logging
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
    logging.info(f"Attempting to fetch transcript for YouTube video ID: {video_id}")
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

        logging.info(f"Fetching available transcripts for {video_id}")
        # Fetch available transcripts
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            logging.info(f"Successfully retrieved transcript list for {video_id}")
        except Exception as e:
            logging.error(f"Failed to retrieve transcript list: {e}")
            signal.alarm(0)  # Cancel the alarm
            raise

        # Try to find a manually created transcript first, otherwise get a generated one
        # Prioritize English ('en') or common variants if available
        preferred_languages = ['en', 'en-US', 'en-GB']
        transcript = None
        try:
            # Check manually created transcripts first
            logging.info(f"Looking for manually created transcript in preferred languages")
            transcript = transcript_list.find_manually_created_transcript(preferred_languages)
            logging.info(f"Found manually created transcript for {video_id}.")
        except NoTranscriptFound:
            logging.info(f"No manual transcript found for {video_id}, checking generated.")
            try:
                # Check generated transcripts
                logging.info(f"Looking for auto-generated transcript in preferred languages")
                transcript = transcript_list.find_generated_transcript(preferred_languages)
                logging.info(f"Found auto-generated transcript for {video_id}.")
            except NoTranscriptFound:
                logging.warning(f"No suitable English transcript found for {video_id}. Checking any language.")
                # If no preferred language found, fetch the first available transcript regardless of language
                try:
                    logging.info(f"Attempting to use first available transcript in any language")
                    first_transcript = list(transcript_list)[0]  # Get the first Transcript object
                    transcript = first_transcript
                    logging.info(f"Found transcript in language: {transcript.language} for {video_id}.")
                except IndexError:
                    logging.error(f"Transcript list seems empty for video ID: {video_id}")
                    signal.alarm(0)  # Cancel the alarm
                    return None

        # Fetch the actual transcript data
        logging.info(f"Fetching actual transcript data for {video_id}")
        transcript_data = transcript.fetch()
        logging.info(f"Successfully fetched raw transcript data ({len(transcript_data)} segments)")

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
                logging.warning(f"Unexpected item type in transcript data: {type(item)}")

        full_transcript = " ".join(texts)
        # Clean up potential multiple spaces resulting from joining
        full_transcript = ' '.join(full_transcript.split())

        # Limit transcript size to prevent timeouts in processing
        MAX_TRANSCRIPT_CHARS = 75000  # 75K characters for longer videos
        if len(full_transcript) > MAX_TRANSCRIPT_CHARS:
            logging.warning(f"Transcript too large ({len(full_transcript)} chars). Truncating to {MAX_TRANSCRIPT_CHARS}.")
            full_transcript = full_transcript[:MAX_TRANSCRIPT_CHARS] + "... [Transcript truncated due to size]"

        if not full_transcript:
            logging.warning(f"Formatted transcript is empty for video ID: {video_id}")
            signal.alarm(0)  # Cancel the alarm
            return None

        logging.info(f"Successfully processed transcript (length: {len(full_transcript)}) for {video_id}")

        # Cancel the timeout alarm
        signal.alarm(0)
        return full_transcript

    except TimeoutException:
        logging.error(f"Timed out while fetching transcript for YouTube video ID: {video_id}")
        return None
    except TranscriptsDisabled:
        logging.warning(f"Transcripts are disabled for YouTube video ID: {video_id}")
        return None
    except NoTranscriptFound:
        logging.warning(f"Could not find any transcript for YouTube video ID: {video_id}")
        return None
    except Exception as e:
        # Catch potential network errors or other API issues
        logging.error(f"Error fetching YouTube transcript for video ID {video_id}: {e}")
        return None
# ABOUTME: Manages Gemini API configuration and summary/title generation logic.
# ABOUTME: Used for generating summaries and titles from content using the LLM.

import logging
import concurrent.futures
from concurrent.futures import TimeoutError as FuturesTimeoutError
import google.generativeai as genai
from google.api_core.exceptions import DeadlineExceeded
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configure Gemini API
if Config.GEMINI_API_KEY:
    try:
        genai.configure(api_key=Config.GEMINI_API_KEY)
        llm = genai.GenerativeModel(Config.GEMINI_MODEL_NAME)
        logging.info(f"Gemini API configured successfully with model: {Config.GEMINI_MODEL_NAME}.")
    except Exception as e:
        logging.error(f"Failed to configure Gemini API with model '{Config.GEMINI_MODEL_NAME}': {e}")
        llm = None
else:
    logging.error("FATAL: GEMINI_API_KEY not found in environment variables.")
    llm = None

def get_summary_from_llm(content: str, source_url: str, is_youtube: bool = False) -> str | None:
    """Sends content (web page or YT transcript) to Gemini API for summarization."""
    if not llm:
        logging.error("LLM client not initialized. Cannot generate summary.")
        return None
    if not content:
        logging.warning("No content provided to summarize.")
        return None

    # Ensure content isn't too large for API processing
    MAX_CONTENT_LENGTH = 80000  # 80K chars should be safe for most LLM APIs
    if len(content) > MAX_CONTENT_LENGTH:
        logging.warning(f"Content too large for LLM API ({len(content)} chars). Truncating to {MAX_CONTENT_LENGTH} chars.")
        content = content[:MAX_CONTENT_LENGTH] + "... [Content truncated due to size]"

    logging.info(f"Preparing to send content (length: {len(content)}, type: {'YouTube' if is_youtube else 'WebPage'}) to Gemini")

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

    logging.info(f"Sending request to Gemini API (prompt length: {len(prompt)})")

    try:
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
                logging.info("Starting LLM API call with 90 second timeout")
                response = future.result(timeout=90)  # 90 second timeout

                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    summary = response.candidates[0].content.parts[0].text
                    logging.info(f"Successfully generated summary from Gemini ({len(summary)} chars)")
                    return summary.strip()
                else:
                    try:
                        finish_reason = response.candidates[0].finish_reason if response.candidates else "Unknown"
                        safety_ratings = response.prompt_feedback.safety_ratings if response.prompt_feedback else "N/A"
                        logging.error(f"Gemini API returned unexpected or empty response. Finish Reason: {finish_reason}, Safety: {safety_ratings}")
                    except Exception:
                        logging.error(f"Gemini API returned unexpected or empty response. Could not parse details.")
                    return None

            except FuturesTimeoutError:
                logging.error("Gemini API request timed out (exceeded 90 seconds)")
                # Cancel the future if possible
                future.cancel()
                return None
            except DeadlineExceeded:
                logging.error("Gemini API request exceeded deadline")
                return None

    except Exception as e:
        logging.error(f"Error calling Gemini API: {e}")
        return None

def get_short_title_from_llm(summary_text: str) -> str | None:
    """Generates a short title ( < 10 words) for the summary using the LLM."""
    if not llm:
        logging.error("LLM client not initialized. Cannot generate title.")
        return None
    if not summary_text:
        logging.warning("No summary text provided to generate title from.")
        return None

    logging.info("Requesting short title generation from LLM.")
    prompt = f"""Please summarize the following text into a concise title of less than 10 words. Output only the title itself, without any introductory phrases like "Title:".

Text to summarize into a title:
---
{summary_text[:2000]}
---

Concise Title (less than 10 words):""" # Limit input length just in case

    try:
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
                logging.info("Starting LLM title generation with 30 second timeout")
                response = future.result(timeout=30)  # 30 second timeout for title generation

                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    title = response.candidates[0].content.parts[0].text.strip()
                    # Basic cleanup: remove potential quotes, ensure reasonable length
                    title = title.strip('"\'')
                    if len(title.split()) > 12: # Allow slightly more than 10 just in case
                        logging.warning(f"LLM generated title longer than expected: '{title}'. Truncating.")
                        title = " ".join(title.split()[:10]) + "..."
                    logging.info(f"Successfully generated short title: '{title}'")
                    return title
                else:
                    logging.error(f"LLM failed to generate a short title. Response: {response}")
                    return None

            except FuturesTimeoutError:
                logging.error("Gemini API title generation timed out (exceeded 30 seconds)")
                # Cancel the future if possible
                future.cancel()
                return None

    except Exception as e:
        logging.error(f"Error calling Gemini API for title generation: {e}")
        return None
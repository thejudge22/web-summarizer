# ABOUTME: Manages LLM API configuration and summary/title generation logic.
# ABOUTME: Used for generating summaries and titles from content using the LLM.

import logging
import concurrent.futures
from concurrent.futures import TimeoutError as FuturesTimeoutError
import openai
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configure OpenAI API client
client = openai.OpenAI(api_key=Config.OPENAI_API_KEY) if Config.OPENAI_API_KEY else None
if client:
    logging.info(f"OpenAI API configured successfully with model: {Config.OPENAI_MODEL_NAME}.")
else:
    logging.warning("OPENAI_API_KEY not found in environment variables. OpenAI functionality will be disabled.")

def _call_openai(prompt: str, model: str) -> str | None:
    """Call the OpenAI API with the given prompt and model."""
    if not client:
        logging.error("OpenAI client not initialized. Check your API key configuration.")
        return None

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            top_p=0.95
        )
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        else:
            logging.error(f"OpenAI API returned unexpected or empty response.")
            return None
    except openai.OpenAIError as e:
        logging.error(f"Error calling OpenAI API: {e}")
        return None

def get_summary_from_llm(content: str, source_url: str, is_youtube: bool = False) -> str | None:
    """Sends content (web page or YT transcript) to the LLM API for summarization."""
    if not content:
        logging.warning("No content provided to summarize.")
        return None

    # Ensure content isn't too large for API processing
    MAX_CONTENT_LENGTH = 80000  # 80K chars should be safe for most LLM APIs
    if len(content) > MAX_CONTENT_LENGTH:
        logging.warning(f"Content too large for LLM API ({len(content)} chars). Truncating to {MAX_CONTENT_LENGTH} chars.")
        content = content[:MAX_CONTENT_LENGTH] + "... [Content truncated due to size]"

    logging.info(f"Preparing to send content (length: {len(content)}, type: {'YouTube' if is_youtube else 'WebPage'}) to LLM")

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
 Do not ask a follow up question.

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
Do not ask a follow up question.

Content:
---
{content}
---

Summary:"""

    logging.info(f"Sending request to LLM API (prompt length: {len(prompt)})")

    return _call_openai(prompt, Config.OPENAI_MODEL_NAME)

def get_short_title_from_llm(summary_text: str) -> str | None:
    """Generates a short title ( < 10 words) for the summary using the LLM."""
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

    return _call_openai(prompt, Config.OPENAI_MODEL_NAME)

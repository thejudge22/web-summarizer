# ABOUTME: Contains all Flask route handlers for the application.
# ABOUTME: Handles summarization and Karakeep integration.

import logging
import markdown
from flask import Flask, request, render_template, abort, flash, get_flashed_messages, session, redirect, url_for, jsonify
from config import Config
from llm import get_summary_from_llm, get_short_title_from_llm
from youtube import is_youtube_url, fetch_youtube_transcript
from web_content import is_valid_url, fetch_page_content
from karakeep import get_karakeep_list_id, send_summary_to_karakeep
from helpers import store_summary_data, retrieve_summary_data

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Flask app
app = Flask(__name__)

# Configure Flask app
app.secret_key = Config.FLASK_SECRET_KEY or os.urandom(24)

# Admin credentials

# Karakeep configuration
KARAKEEP_ENABLED = Config.KARAKEEP_ENABLED  # Use the value from Config class



@app.route('/', methods=['GET']) # Only handle GET requests now
def index():
    """Handles displaying the form and pre-filling from query params (e.g., bookmarklet)."""
    target_url = request.args.get('url') # Check for URL from query param
    if target_url:
        logging.info(f"Received URL via GET parameter: {target_url}")
        # Basic validation before pre-filling
        if not is_valid_url(target_url):
             logging.warning(f"Invalid URL format in GET parameter: {target_url}")
             flash("Invalid URL format provided in the link. Please check the URL.", "error")
             target_url = None # Don't pre-fill invalid URL

    # Render the main form page
    # Pass the potentially pre-filled URL
    return render_template('index.html', submitted_url=target_url)

@app.route('/summarize_ajax', methods=['POST'])
def summarize_ajax():
    """Handles AJAX request for summarization."""
    # Log request starting time for tracking long-running operations
    import time
    start_time = time.time()

    if not request.is_json:
        logging.warning("Received non-JSON request on /summarize_ajax endpoint.")
        return jsonify({'status': 'error', 'message': 'Invalid request format. Expected JSON.'}), 400

    data = request.get_json()
    target_url = data.get('url')
    logging.info(f"Received URL via AJAX POST: {target_url}")

    if not target_url:
        logging.warning("No URL provided in AJAX request.")
        return jsonify({'status': 'error', 'message': 'No URL provided.'}), 400

    # Validate the URL
    if not is_valid_url(target_url):
        logging.warning(f"Invalid URL format provided via AJAX: {target_url}")
        return jsonify({'status': 'error', 'message': 'Invalid URL format. Please include http:// or https://'}), 400

    content = None
    summary = None
    is_youtube = False
    video_id = is_youtube_url(target_url)

    try:
        if video_id:
            # It's a YouTube URL
            is_youtube = True
            logging.info(f"Detected YouTube URL with video ID: {video_id}")
            content = fetch_youtube_transcript(video_id)
            if content is None:
                logging.error(f"Failed to fetch transcript for YouTube URL: {target_url}")
                return jsonify({'status': 'error', 'message': 'Could not fetch transcript. Transcripts might be disabled or unavailable.'}), 400
            else:
                summary = get_summary_from_llm(content, target_url, is_youtube=True)
        else:
            # It's a regular web page URL
            logging.info(f"Processing as standard web page: {target_url}")
            content = fetch_page_content(target_url)
            if content is None:
                logging.error(f"Failed to fetch or process content for web URL: {target_url}")
                return jsonify({'status': 'error', 'message': 'Could not fetch or process content. Site might be inaccessible or blocking requests.'}), 400
            else:
                 summary = get_summary_from_llm(content, target_url, is_youtube=False)

        # Check if summary generation failed
        if summary is None:
            logging.error(f"Failed to get summary from LLM for URL: {target_url} (Type: {'YouTube' if is_youtube else 'WebPage'})")
            return jsonify({'status': 'error', 'message': 'Failed to generate summary. LLM might be unavailable or had an issue.'}), 500 # Internal server error likely

        # Success! Generate HTML and store results in temporary file
        logging.info(f"Successfully generated summary (Markdown) for: {target_url}")
        summary_html = markdown.markdown(summary) # Convert Markdown to HTML
        logging.info(f"Converted summary to HTML.")

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
            logging.info(f"Stored summary with ID {summary_id} in temporary file")

            return jsonify({'status': 'success', 'redirect_url': url_for('show_summary')})
        except Exception as e:
            logging.error(f"Failed to store summary data: {e}", exc_info=True)
            return jsonify({'status': 'error', 'message': 'Server error: Failed to store summary data.'}), 500

    except Exception as e:
        # Catch any unexpected errors during the process
        logging.error(f"Unexpected error during summarization for {target_url}: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': 'An unexpected server error occurred.'}), 500

@app.route('/show_summary')
def show_summary():
    """Displays the summary result retrieved from temporary storage."""
    # Get the summary ID from session
    summary_id = session.pop('summary_id', None)

    if not summary_id:
        logging.warning("Accessed /show_summary without summary ID in session.")
        flash("No summary data found. Please generate a summary first.", "info")
        return redirect(url_for('index'))

    # Retrieve the summary data using the ID
    summary_data = retrieve_summary_data(summary_id)

    if not summary_data:
        logging.warning(f"Could not retrieve summary data for ID: {summary_id}")
        flash("Summary data could not be retrieved. Please try again.", "error")
        return redirect(url_for('index'))

    logging.info(f"Successfully retrieved summary data for ID: {summary_id}")

    # Render the summary template with the retrieved data
    return render_template(
        'summary.html',
        original_url=summary_data.get('original_url'),
        summary_html=summary_data.get('summary_html'),
        summary_markdown=summary_data.get('summary_markdown') # Pass markdown to template
    )

# Optional: Add a simple health check endpoint (unprotected)
@app.route('/health')
def health_check():
    # Basic check - more elaborate checks could test LLM connectivity etc.
    return "OK", 200

@app.route('/send_to_karakeep', methods=['POST'])
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
        logging.error("Missing summary_markdown in form submission to Karakeep.")
        flash("Could not find summary content to send to Karakeep.", "error")
        # Redirect back to index as we don't have the context to show the summary page again easily
        return redirect(url_for('index'))

    logging.info("Received summary markdown from form for Karakeep submission.")

    # Proceed with Karakeep submission using summary_markdown
    karakeep_title = get_short_title_from_llm(summary_markdown)

    if not karakeep_title:
        flash("Failed to generate title for Karakeep.", "error")
        return redirect(url_for('index')) # Or redirect back to summary?

    karakeep_list_id = get_karakeep_list_id(Config.KARAKEEP_API_URL, Config.KARAKEEP_API_KEY, Config.KARAKEEP_LIST_NAME)

    if not karakeep_list_id:
        flash(f"Could not find Karakeep list '{Config.KARAKEEP_LIST_NAME}'.", "error")
        return redirect(url_for('index')) # Or redirect back to summary?

    karakeep_sent_ok = send_summary_to_karakeep(
        Config.KARAKEEP_API_URL, Config.KARAKEEP_API_KEY, karakeep_list_id,
        karakeep_title, summary_markdown, original_url # Use summary_markdown here
    )

    if karakeep_sent_ok:
        flash(f"Summary successfully sent to Karakeep list '{Config.KARAKEEP_LIST_NAME}'.", "success")
    else:
        flash(f"Failed to send summary to Karakeep list '{Config.KARAKEEP_LIST_NAME}'. Check logs.", "error")

    # Redirect back to the summary page (or index)
    # To redirect back to the summary page, you'd need to pass the summary content
    # in the redirect, which isn't standard for GET redirects.
    # Redirecting to index is simpler for now.
    return redirect(url_for('index'))
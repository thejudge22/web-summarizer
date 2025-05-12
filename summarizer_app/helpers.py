# ABOUTME: Provides general-purpose helpers, such as temp file storage and URL validation.
# ABOUTME: Used for various utility functions across the application.

import os
import json
import uuid
from tempfile import gettempdir

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
        logging.error(f"Error retrieving summary data: {e}")
        # If we can't read the file, try to clean it up anyway
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
        return None
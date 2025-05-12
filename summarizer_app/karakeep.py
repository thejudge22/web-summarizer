# ABOUTME: Integrates with the Karakeep API for list ID lookup and summary sending.
# ABOUTME: Used for managing Karakeep lists and sending summaries.

import logging
import requests
from requests.exceptions import RequestException
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_karakeep_list_id(api_url: str, api_key: str, list_name: str) -> str | None:
    """Fetches the ID of a Karakeep list by its name."""
    if not Config.is_karakeep_enabled():
        logging.warning("Karakeep is disabled, cannot fetch list ID.")
        return None

    list_endpoint_url = f"{api_url}/lists" # Define the specific URL being called here
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json'
    }
    logging.info(f"Attempting to find Karakeep list ID for: '{list_name}' via GET {list_endpoint_url}")

    try:
        response = requests.get(list_endpoint_url, headers=headers, timeout=15)
        response.raise_for_status()
        response_data = response.json()

        actual_list_data = None

        if isinstance(response_data, list):
            # Case 1: API returns the list directly
            logging.info("Karakeep /lists endpoint returned a direct list.")
            actual_list_data = response_data
        elif isinstance(response_data, dict):
            # Case 2: API returns a dictionary, look for nested list
            logging.info("Karakeep /lists endpoint returned a dictionary. Checking common keys for list data...")
            possible_keys = ['data', 'results', 'items', 'lists'] # Common keys for list data
            for key in possible_keys:
                if key in response_data and isinstance(response_data[key], list):
                    logging.info(f"Found list data under the key '{key}'.")
                    actual_list_data = response_data[key]
                    break # Found it, stop looking
            if actual_list_data is None:
                 logging.error(f"Karakeep /lists response was a dictionary, but could not find list data under expected keys ({', '.join(possible_keys)}). Dictionary keys: {list(response_data.keys())}")
                 return None
        else:
            # Case 3: Unexpected format
            logging.error(f"Unexpected response format from Karakeep /lists endpoint. Expected a list or a dict containing a list, got: {type(response_data)}")
            return None

        # Now process the actual_list_data if found
        if actual_list_data is not None:
            for lst in actual_list_data:
                if isinstance(lst, dict) and lst.get('name') == list_name:
                    list_id = lst.get('id')
                    if list_id:
                        logging.info(f"Found Karakeep list '{list_name}' with ID: {list_id}")
                        return str(list_id)  # Ensure it's a string
                    else:
                        logging.error(f"List '{list_name}' found but has no 'id' field in response item: {lst}")
                        # Continue searching in case there are multiple lists with the same name (unlikely but possible)
            # If loop finishes without finding the list
            logging.warning(f"Karakeep list named '{list_name}' not found in the response data.")
            return None
        else:
             # This case should technically be caught above, but for safety:
             logging.error("Failed to extract actual list data from Karakeep response.")
             return None
    # End of the main processing logic inside the try block

    except RequestException as e:
        # This except block now correctly corresponds to the try above
        logging.error(f"Error requesting Karakeep lists from {list_endpoint_url}: {e}") # Use the correct URL variable
        return None
    except Exception as e:
        # This except block also corresponds to the try above
        logging.error(f"Error processing Karakeep lists response: {e}")
        return None

def send_summary_to_karakeep(api_url: str, api_key: str, list_id: str, title: str, markdown_summary: str, original_url: str) -> bool:
    """Sends the summary as a new item to a specific Karakeep list."""
    if not Config.is_karakeep_enabled():
        logging.warning("Karakeep is disabled, cannot send summary.")
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
    logging.info(f"Attempting Step 1: POST summary to Karakeep (Endpoint: {create_bookmark_url}), title '{title}'")

    try:
        response_create = requests.post(create_bookmark_url, headers=headers, json=create_payload, timeout=20)
        response_create.raise_for_status()
        created_bookmark_data = response_create.json()
        new_bookmark_id = created_bookmark_data.get('id')

        if not new_bookmark_id:
            logging.error(f"ERROR: Could not extract 'id' from POST /bookmarks response. Response: {str(created_bookmark_data)[:500]}...")
            return False

        new_bookmark_id = str(new_bookmark_id) # Ensure it's a string
        logging.info(f"Successfully Step 1: Created Bookmark ID {new_bookmark_id}")

        # Step 2: Link the new bookmark to the target list
        link_url = f"{api_url}/lists/{list_id}/bookmarks/{new_bookmark_id}"
        logging.info(f"Attempting Step 2: Link Bookmark ID {new_bookmark_id} to List ID {list_id} (PUT {link_url})")

        # Use PUT with an empty JSON body to link
        response_link = requests.put(link_url, headers=headers, json={}, timeout=15) # Empty JSON payload {}
        response_link.raise_for_status()

        logging.info(f"Successfully Step 2: Linked Bookmark ID {new_bookmark_id} to List ID {list_id}. Status: {response_link.status_code}")
        return True

    except RequestException as e:
        # Log specific details based on which step failed
        failed_url = e.request.url if e.request else "Unknown URL"
        failed_method = e.request.method if e.request else "Unknown Method"
        logging.error(f"Error during Karakeep interaction ({failed_method} {failed_url}): {e}")
        if hasattr(e, 'response') and e.response is not None:
            logging.error(f"Response Status: {e.response.status_code}")
            try:
                error_details = e.response.json()
                logging.error(f"Response JSON: {error_details}")
            except Exception as json_e: # Added missing except block
                logging.error(f"Could not parse error response as JSON: {json_e}")
                logging.error(f"Raw Response Text: {e.response.text[:500]}...") # Log raw text instead
        # The general error log below might be redundant now, but keep it for broader issues
        logging.error(f"Unexpected error during Karakeep summary sending (outside RequestException handling): {e}", exc_info=True) # Clarified log message
        return False
    except Exception as e: # Catch other potential errors in the function
        logging.error(f"Unexpected error during Karakeep summary sending: {e}", exc_info=True) # Include traceback
        return False
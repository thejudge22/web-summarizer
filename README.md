# Web Summarizer

A simple web application that summarizes web pages and YouTube videos using the Google Gemini API. It includes basic authentication, a bookmarklet for quick summarizing, and optional integration with Karakeep

## Features

*   Summarize content from any publicly accessible URL.
*   Summarize YouTube videos by fetching and processing their transcripts.
*   Uses the Google Gemini API with a configurable model (defaulting to `gemini-2.0-flash`).
*   Simple web interface built with Flask.
*   Bookmarklet to quickly summarize the currently viewed page.
*   Basic username/password authentication to protect access.
*   Optional: Send generated summaries directly to a specified list in your Karakeep/Hoarder instance.
*   Containerized using Docker and Docker Compose for easy deployment.

## Technology Stack

*   **Backend:** Python, Flask
*   **LLM:** Google Gemini API (configurable via `GEMINI_MODEL_NAME` environment variable)
*   **Web Scraping:** BeautifulSoup4, requests
*   **YouTube Transcripts:** `youtube-transcript-api`
*   **Serving:** Gunicorn
*   **Containerization:** Docker, Docker Compose
*   **Authentication:** Werkzeug (for password hashing)
*   **Markdown Rendering:** Markdown

## Setup and Installation

### Prerequisites

*   [Docker](https://docs.docker.com/get-docker/)
*   [Docker Compose](https://docs.docker.com/compose/install/) (usually included with Docker Desktop)
*   [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) (for cloning)
*   A Google Gemini API Key (obtainable from [Google AI Studio](https://aistudio.google.com/))

### Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/web-summarizer.git # Replace with the actual repo URL
    cd web-summarizer
    ```

2.  **Configure Environment Variables:**
    *   Navigate to the `summarizer_app` directory:
        ```bash
        cd summarizer_app
        ```
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    *   Edit the `.env` file with your actual credentials and settings. See the [Configuration](#configuration-summarizer_appenv) section below for details. **Crucially, set `FLASK_SECRET_KEY` and change `ADMIN_PASSWORD`**.

3.  **Build and Run with Docker Compose:**
    *   Navigate back to the project root directory (where `docker-compose.yaml` is located):
        ```bash
        cd ..
        ```
    *   Run Docker Compose:
        ```bash
        docker-compose up -d --build
        ```
        *   `-d` runs the container in detached mode (in the background).
        *   `--build` forces a rebuild of the image if necessary (useful after code changes if not using volumes for development).

4.  **Access the Application:**
    *   Open your web browser and go to `http://localhost:25001` (or the host port you mapped in `docker-compose.yaml`).

## Configuration (`summarizer_app/.env`)

The `.env` file within the `summarizer_app` directory controls the application's configuration:

*   `GEMINI_API_KEY`: **Required.** Your API key for the Google Gemini service.
*   `FLASK_SECRET_KEY`: **Required.** A strong, random string used for session security (login persistence). Generate one using `python -c 'import os; print(os.urandom(24).hex())'`.
*   `ADMIN_USERNAME`: The username for logging into the application. Default is `admin`.
*   `ADMIN_PASSWORD`: **Required.** The password for the admin user. **Change this from the default!**
*   `KARAKEEP_API_URL`: **Optional.** The base URL for your Karakeep/Hoarder API (e.g., `http://your-hoarder.com/api/v1`). Leave blank to disable integration.
*   `KARAKEEP_API_KEY`: **Optional.** The API key generated within your Karakeep/Hoarder instance. Required if `KARAKEEP_API_URL` is set.
*   `KARAKEEP_LIST_NAME`: **Optional.** The exact name of the list within Karakeep/Hoarder where summaries should be sent. Required if `KARAKEEP_API_URL` is set.
*   `GEMINI_MODEL_NAME`: **Optional.** The name of the Gemini model to use for summarization (e.g., `gemini-1.5-flash`, `gemini-1.5-pro`). Defaults to `gemini-2.0-flash`.

**Note:** The application requires `FLASK_SECRET_KEY` to be set for login sessions to persist across restarts. If not set, a temporary key is generated, but logins will be lost on restart.

## Usage

1.  **Login:** Access the application URL (`http://localhost:25001` by default) and log in using the `ADMIN_USERNAME` and `ADMIN_PASSWORD` configured in your `.env` file.
2.  **Summarize:**
    *   Enter a valid URL (including `http://` or `https://`) into the input field and click "Summarize".
    *   The application will fetch the content (or YouTube transcript), send it to the Gemini API, and display the resulting summary.
3.  **Bookmarklet:**
    *   While logged in, drag the "Summarize Current Page" link from the main page to your browser's bookmarks bar.
    *   When viewing a page you want to summarize, click the bookmarklet. It will open the summarizer application in a new tab with the current page's URL pre-filled.
4.  **Karakeep/Hoarder Integration:**
    *   If configured in the `.env` file, check the "Send summary to Hoarder/Karakeep" checkbox before submitting a URL.
    *   If the summary is generated successfully, the application will attempt to:
        1.  Generate a short title for the summary using the LLM.
        2.  Find the ID of the specified `KARAKEEP_LIST_NAME`.
        3.  Create a new bookmark/item in Karakeep/Hoarder with the title, summary (as Markdown text), and original URL, linking it to the specified list.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

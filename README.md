<!--
ABOUTME: This file provides setup, configuration, and usage instructions for the Web Summarizer app.
ABOUTME: Focused on Docker-based deployment and environment configuration for GitHub users.
-->

# Web Summarizer

A simple web application that summarizes web pages and YouTube videos using the OpenAI API. Includes basic authentication, a bookmarklet for quick summarizing, and optional integration with [Karakeep/Hoarder](https://karakeep.app).

---

## Features

- Summarize content from any publicly accessible URL.
- Summarize YouTube videos by fetching and processing their transcripts.
- Uses the OpenAI API with a configurable model (default: `gpt-4.1-mini`).
- Simple web interface built with Flask.
- Bookmarklet for one-click summarization of the current page.
- Basic username/password authentication.
- Optional: Send generated summaries directly to a specified list in your Karakeep/Hoarder instance.
- Containerized using Docker and Docker Compose for easy deployment.

## Setup & Installation

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/) (usually included with Docker Desktop)
- [Git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
- An OpenAI API Key (get one from [OpenAI](https://openai.com/))

### Steps

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/web-summarizer.git # Replace with the actual repo URL
   cd web-summarizer
   ```

2. **Configure Environment Variables:**
   - Navigate to the `summarizer_app` directory:
     ```bash
     cd summarizer_app
     ```
   - Copy the example environment file:
     ```bash
     cp .env.example .env
     ```
   - Edit the `.env` file with your settings.  
     **Important:** Set a strong `FLASK_SECRET_KEY`
   - See the [Configuration](#configuration-summarizer_appenv) section below for details.

3. **Build and Run with Docker Compose:**
   - Navigate back to the project root directory (where `docker-compose.yaml` is located):
     ```bash
     cd ..
     ```
   - Run Docker Compose:
     ```bash
     docker-compose up -d --build
     ```
     - `-d` runs the container in detached mode (background).
     - `--build` forces a rebuild of the image if necessary.

4. **Access the Application:**
   - Open your browser and go to [http://localhost:25001](http://localhost:25001) (or the port you mapped in `docker-compose.yaml`).

## Configuration (`summarizer_app/.env`)

The `.env` file in the `summarizer_app` directory controls the application's configuration.  
Copy `.env.example` to `.env` and edit as needed.

### Required

- `OPENAI_API_KEY`: Your OpenAI API key.
- `FLASK_SECRET_KEY`: A strong, random string for session security. Generate one with:
  ```bash
  python -c 'import os; print(os.urandom(24).hex())'
  ```

### Optional

- `OPENAI_API_URL`: OpenAI API endpoint (default: `https://api.openai.com/v1/chat/completions`)
- `OPENAI_MODEL_NAME`: OpenAI model to use (default: `gpt-4.1-mini`)
- `KARAKEEP_API_URL`: Base URL for your Karakeep/Hoarder API (leave blank to disable)
- `KARAKEEP_API_KEY`: API key for Karakeep/Hoarder (required if using integration)
- `KARAKEEP_LIST_NAME`: Name of the list in Karakeep/Hoarder for summaries (required if using integration)

**Note:** If `FLASK_SECRET_KEY` is not set, a temporary key is generated and logins will be lost on restart.

## Usage

1. **Login:**  
   Go to [http://localhost:25001](http://localhost:25001)

2. **Summarize:**  
   Enter a valid URL (including `http://` or `https://`) and click "Summarize".  
   The app will fetch the content (or YouTube transcript), send it to OpenAI, and display the summary.

3. **Bookmarklet:**  
   While logged in, drag the "Summarize Current Page" link from the main page to your bookmarks bar.  
   When viewing a page you want to summarize, click the bookmarklet. It will open the summarizer with the current page's URL pre-filled.

4. **Karakeep/Hoarder Integration (Optional):**  
   If configured, a "Send Summary to Karakeep" button appears after generating a summary.  
   Clicking it will:
   - Generate a short title for the summary.
   - Find the ID of the specified `KARAKEEP_LIST_NAME`.
   - Create a new item in Karakeep/Hoarder with the title, summary, and original URL.

   Feedback messages will indicate success or failure.

## Troubleshooting

- **Port already in use:**  
  Make sure port `25001` is free or change the mapping in `docker-compose.yaml`.
- **OpenAI errors:**  
  Double-check your `OPENAI_API_KEY` and model name.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.


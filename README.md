# arXiv Paper Finder & Notifier

This script searches arXiv daily for new papers matching **multiple, user-defined groups of keywords** and sends an email notification **for each group** if new papers are found.

## Features

*   Searches arXiv based on **multiple groups of keywords** defined in the `.env` file.
*   Filters results to include only papers published or updated within the last **7 days on the first run** (per group, based on overall state file), and the last **24 hours (configurable) on subsequent runs**.
*   Keeps track of already reported papers **separately for each group** using a state file (`paper_finder_state.json`) to avoid duplicate notifications.
*   Sends a **separate daily email for each group** summarizing any new findings for those specific keywords.
*   Configurable via environment variables (using a `.env` file).
*   Runs continuously, checking once per day.
*   Includes basic logging.

## Setup

1.  **Clone the repository or download the script:**
    Get the `paper_finder.py` script and the `requirements.txt` file into a directory on your system.

2.  **Create a `.env` file:**
    In the same directory as `paper_finder.py`, create a file named `.env` and add your configuration details. Define **one or more keyword groups** using variables starting with `KEYWORD_GROUP_`:

    ```dotenv
    # --- arXiv Search Keyword Groups ---
    # Define one or more groups. The part after KEYWORD_GROUP_ must be unique.
    # List keywords for each group, separated by commas.
    KEYWORD_GROUP_1="machine learning, large language models"
    KEYWORD_GROUP_NN="neural networks, deep learning, backpropagation"
    KEYWORD_GROUP_OTHER="quantum computing, specific algorithm"
    # Add as many groups as you need...

    # --- Email Settings --- 
    # Replace with your SMTP server details and credentials
    SMTP_SERVER="smtp.gmail.com" 
    SMTP_PORT=587 # Use 587 for TLS (recommended) or 465 for SSL
    SENDER_EMAIL="your_sender_email@example.com"

    # IMPORTANT: For Gmail/Google Workspace, if 2-Factor Authentication (2FA) is enabled, 
    # you *must* create and use an "App Password". 
    # See: https://support.google.com/accounts/answer/185833
    SENDER_PASSWORD="your_sender_email_password_or_app_password" 

    # Email address to send notifications to
    RECEIVER_EMAIL="your_recipient_email@example.com" 
    ```
    *   **Replace the example keywords** and email details with your actual information.
    *   Make sure the identifier after `KEYWORD_GROUP_` (e.g., `1`, `NN`, `OTHER`) is unique for each group.
    *   Remember to use an App Password for `SENDER_PASSWORD` if using Gmail with 2FA.

3.  **Install Dependencies:**
    Make sure you have Python 3 and pip installed. Then, install the required libraries from the `requirements.txt` file (ensure it lists at least `arxiv` and `python-dotenv`):
    ```bash
    pip install -r requirements.txt 
    ```

## Usage

This script is designed to be run continuously.

1.  **Directly (for testing):**
    Navigate to the directory containing the script and `.env` file, then run:
    ```bash
    python paper_finder.py
    ```
    It will perform an initial check and then wait 24 hours before the next check. Press `Ctrl+C` to stop.

2.  **On a Server (Background):**
    Use `nohup`, `screen`, or `tmux` from the script's directory:

    *   **Using `nohup`:**
        ```bash
        nohup python paper_finder.py > paper_finder.log 2>&1 &
        ```
        Check `paper_finder.log` for output.

    *   **Using `screen` or `tmux`:**
        -   Start a session: `screen` or `tmux`
        -   Run the script: `python paper_finder.py`
        -   Detach from the session.

## Notes

*   **Initial Run Search Window:** The very first time the script runs (or if the `paper_finder_state.json` file is missing/invalid), it will search for papers from the **last 7 days for all defined groups**. Subsequent runs will use the configured 24-hour window.
*   **State File:** The `paper_finder_state.json` file will be created in the script's directory to store the IDs of papers that have been emailed, **organized by keyword group**. Do not delete this file unless you want to reset the notification history for all groups (and trigger the 7-day initial search again).
*   **arXiv API Usage:** Be mindful of arXiv's API usage terms. The script currently searches once daily (per group) and limits results per query.
*   **Email Content:** The email includes the title, authors, publication/update date, link, and abstract for each new paper found **for a specific keyword group**. 
import arxiv
import smtplib
import os
from email.message import EmailMessage
import time
import logging
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
import json
import re # Import regex for parsing env vars

# --- Configuration ---
# Load environment variables from the main .env file
load_dotenv()

# Parse Keyword Groups from .env (e.g., KEYWORD_GROUP_1="kw1, kw2")
KEYWORD_GROUPS = {}
for key, value in os.environ.items():
    match = re.fullmatch(r"KEYWORD_GROUP_(\w+)", key, re.IGNORECASE)
    if match and value.strip():
        group_id = f"group_{match.group(1)}" # Consistent internal ID
        keywords = [k.strip() for k in value.split(',') if k.strip()]
        if keywords:
            KEYWORD_GROUPS[group_id] = {
                "name": key, # Original env var name for display
                "keywords": keywords,
                "keywords_string": value # Original string for display
            }
if not KEYWORD_GROUPS:
    logging.warning("No KEYWORD_GROUP_X variables found in .env file. Script will not search.")

# Email Configuration (using the same variables as the citation checker)
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

# State file to store IDs of papers already emailed (now stores multiple groups)
STATE_FILE = "paper_finder_state.json"
CHECK_INTERVAL_HOURS = 24 # Check once a day

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Functions ---

def load_state(filepath):
    """Loads the state dictionary {group_id: set_of_seen_ids} from the state file.
    Returns a tuple: (state_dictionary, file_existed_and_was_valid)
    """
    try:
        file_exists = os.path.exists(filepath)
        if not file_exists:
            logging.info(f"State file {filepath} not found. Assuming initial run for all groups.")
            return {}, False

        with open(filepath, 'r') as f:
            data = json.load(f)
            # Convert lists back to sets for each group
            state = {group_id: set(seen_list) for group_id, seen_list in data.items()}
            logging.info(f"Successfully loaded state for {len(state)} groups from {filepath}.")
            return state, True

    except (json.JSONDecodeError):
        logging.warning(f"State file {filepath} exists but is invalid/empty. Treating as initial run.")
        return {}, False
    except Exception as e:
        logging.error(f"Unexpected error loading state file {filepath}: {e}. Treating as initial run.")
        return {}, False

def save_state(filepath, state):
    """Saves the state dictionary {group_id: set_of_seen_ids} to the state file."""
    try:
        # Convert sets to lists for JSON serialization
        serializable_state = {group_id: sorted(list(seen_set)) for group_id, seen_set in state.items()}
        with open(filepath, 'w') as f:
            json.dump(serializable_state, f, indent=4)
        logging.info(f"Saved state for {len(state)} groups to {filepath}")
    except Exception as e:
        logging.error(f"Error writing state file {filepath}: {e}")

def search_new_papers(keywords, seen_ids, search_timedelta):
    """Searches arXiv for new papers matching keywords, excluding seen ones.
    
    Args:
        keywords (list): List of search keywords.
        seen_ids (set): Set of already processed paper IDs.
        search_timedelta (timedelta): How far back in time to search for new papers.
    """
    new_papers = []
    query = " AND ".join([f'all:"{k}"' for k in keywords])
    logging.info(f"Searching arXiv with query: {query}")

    try:
        search = arxiv.Search(
            query=query,
            max_results=100, # Limit results per query to avoid overwhelming API
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending
        )

        # Define the time window based on the passed timedelta
        cutoff_date = datetime.now(timezone.utc) - search_timedelta
        logging.info(f"Searching for papers published/updated since {cutoff_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        for result in search.results():
            paper_id = result.entry_id.split('/')[-1] # Extract ID like '2301.12345v1'

            # Check if submitted or updated recently and not seen before
            publish_time = result.published.replace(tzinfo=timezone.utc) # Ensure timezone aware
            update_time = result.updated.replace(tzinfo=timezone.utc) # Ensure timezone aware

            if (publish_time >= cutoff_date or update_time >= cutoff_date) and paper_id not in seen_ids:
                new_papers.append(result)
                logging.info(f"Found new paper: ID={paper_id}, Title='{result.title}'")
            elif paper_id in seen_ids:
                 logging.debug(f"Skipping already seen paper: ID={paper_id}")
            else:
                 logging.debug(f"Skipping older paper: ID={paper_id}, Updated={update_time}")


    except Exception as e:
        logging.error(f"An error occurred during arXiv search: {e}")
        # Consider adding specific error handling for connection issues, etc.

    return new_papers

def send_email(subject, body, sender, password, receiver, server, port):
    """Sends an email using SMTP (adapted from citation_checker)."""
    if not all([sender, password, receiver, server, port]):
        logging.error("Email configuration is incomplete. Cannot send email.")
        return False

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = receiver
    # Ensure body is properly encoded, especially if containing non-ASCII characters
    msg.set_content(body, charset='utf-8')


    try:
        logging.info(f"Connecting to SMTP server {server}:{port}")
        # Use SMTP_SSL for port 465, SMTP for port 587 with starttls
        if port == 465:
             with smtplib.SMTP_SSL(server, port) as smtp_server:
                logging.info("Logging into SMTP server (SSL)...")
                smtp_server.login(sender, password)
                logging.info(f"Sending email to {receiver}...")
                smtp_server.send_message(msg)
        else: # Assuming port 587 or other requires STARTTLS
             with smtplib.SMTP(server, port) as smtp_server:
                smtp_server.starttls() # Enable security
                logging.info("Logging into SMTP server (TLS)...")
                smtp_server.login(sender, password)
                logging.info(f"Sending email to {receiver}...")
                smtp_server.send_message(msg)

        logging.info("Email sent successfully.")
        return True
    except smtplib.SMTPAuthenticationError:
        logging.error("SMTP Authentication Error: Check sender email/password (or App Password for Gmail).")
        return False
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        return False

# --- Main Execution ---

if __name__ == "__main__":
    while True:
        try:
            logging.info("--- Starting Paper Check Cycle ---")
            state_changed = False

            if not KEYWORD_GROUPS:
                logging.warning("No keyword groups defined (check KEYWORD_GROUP_X in .env). Skipping cycle.")
            else:
                # Load the entire state dictionary
                current_state, state_file_existed = load_state(STATE_FILE)

                # Process each keyword group
                for group_id, group_info in KEYWORD_GROUPS.items():
                    group_name_display = group_info["name"]
                    keywords = group_info["keywords"]
                    keywords_string_display = group_info["keywords_string"]
                    logging.info(f"-- Checking Group: {group_name_display} ({keywords_string_display}) --")

                    # Get seen IDs for this specific group
                    group_seen_ids = current_state.get(group_id, set())
                    original_group_seen_count = len(group_seen_ids)

                    # Determine search window for this group based on overall state file existence
                    # (Could be refined later to be per-group if state[group_id] didn't exist)
                    if not state_file_existed:
                        search_window = timedelta(days=7)
                        logging.info(f"[{group_name_display}] First run detected: Searching last 7 days.")
                    else:
                        search_window = timedelta(hours=CHECK_INTERVAL_HOURS)
                        # Logging this once per cycle is enough, moved outside loop
                        # logging.info(f"[{group_name_display}] Subsequent run: Searching last {CHECK_INTERVAL_HOURS} hours.")

                    # Search for new papers for this group
                    new_papers = search_new_papers(keywords, group_seen_ids, search_window)

                    if new_papers:
                        logging.info(f"[{group_name_display}] Found {len(new_papers)} new paper(s). Preparing email.")
                        subject = f"New arXiv Papers: {group_name_display} ({len(new_papers)}) - {time.strftime('%Y-%m-%d')}"
                        body = f"Found {len(new_papers)} new paper(s) for keyword group '{group_name_display}' ({keywords_string_display}):\n\n---\n\n"

                        newly_found_ids = set()
                        for paper in new_papers:
                            paper_id = paper.entry_id.split('/')[-1]
                            newly_found_ids.add(paper_id)
                            body += f"Title: {paper.title}\n"
                            body += f"Authors: {', '.join(author.name for author in paper.authors)}\n"
                            body += f"Published: {paper.published.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                            body += f"Updated: {paper.updated.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                            body += f"Link: {paper.entry_id}\n"
                            body += f"Abstract: {paper.summary}\n\n---\n\n"

                        # Send the email for this group
                        email_sent = send_email(subject, body, SENDER_EMAIL, SENDER_PASSWORD, RECEIVER_EMAIL, SMTP_SERVER, SMTP_PORT)

                        # If email sent successfully, update the state *for this group*
                        if email_sent:
                            current_state[group_id] = group_seen_ids.union(newly_found_ids)
                            state_changed = True # Mark that the state needs saving
                            logging.info(f"[{group_name_display}] State updated with {len(newly_found_ids)} new paper IDs.")
                        else:
                            logging.error(f"[{group_name_display}] Email failed to send. State for this group will not be updated.")

                    else:
                        logging.info(f"[{group_name_display}] No new papers found for this group.")

                # Save the state dictionary if any group updated it
                if state_changed:
                    save_state(STATE_FILE, current_state)
                else:
                    logging.info("No state changes detected in this cycle.")

        except Exception as e:
            logging.error(f"An unexpected error occurred during the main check cycle: {e}")
            logging.error("Script will continue to the next cycle after the delay.")

        # Wait for the specified interval before the next check cycle
        wait_seconds = CHECK_INTERVAL_HOURS * 60 * 60
        logging.info(f"--- Paper Check Cycle Finished. Waiting for {CHECK_INTERVAL_HOURS} hours ({wait_seconds} seconds)... ---")
        time.sleep(wait_seconds) 
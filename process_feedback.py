import os
import gspread
from google.oauth2.service_account import Credentials
import requests
import json
from datetime import datetime
import logging
import sys
import traceback

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'llm_evaluation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)

logger = logging.getLogger(__name__)

GOOGLE_SHEET = os.environ.get('GOOGLE_SHEET_NAME', 'YOUR_SHEET_NAME')
CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON', None)
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_MODEL = os.environ.get('OPENROUTER_MODEL', 'openai/gpt-4o')
YOUR_SITE_URL = os.environ.get('SITE_URL', 'https://yourapp.com')
YOUR_SITE_NAME = os.environ.get('SITE_NAME', 'Jira Feedback Processor')

logger.info("=" * 80)
logger.info("LLM FEEDBACK EVALUATION SERVICE STARTED")
logger.info("=" * 80)
logger.info(f"Configuration:")
logger.info(f"  - Google Sheet: {GOOGLE_SHEET}")
logger.info(f"  - OpenRouter Model: {OPENROUTER_MODEL}")
logger.info(f"  - OpenRouter API Key: {'✓ Configured' if OPENROUTER_API_KEY else '✗ Missing'}")
logger.info(f"  - Google Credentials: {'✓ Configured' if CREDENTIALS_JSON else '✗ Missing'}")
logger.info("=" * 80)

def get_google_sheets_client():
    logger.info("Attempting to authorize Google Sheets client...")
    if not CREDENTIALS_JSON:
        logger.error("GOOGLE_CREDENTIALS_JSON not configured")
        return None
    try:
        creds_dict = json.loads(CREDENTIALS_JSON)
        logger.debug(f"Service account email: {creds_dict.get('client_email', 'N/A')}")
        creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        client = gspread.authorize(creds)
        logger.info("✓ Successfully authorized Google Sheets client")
        return client
    except Exception as e:
        logger.error(f"Error authorizing Google Sheets: {e}")
        return None

def read_feedback_rows():
    logger.info("=" * 80)
    logger.info("READING ALL FEEDBACK ROWS FROM GOOGLE SHEETS")
    logger.info("=" * 80)
    client = get_google_sheets_client()
    if not client:
        return []
    try:
        logger.info(f"Opening Google Sheet: '{GOOGLE_SHEET}'...")
        sh = client.open(GOOGLE_SHEET)
        logger.info(f"✓ Successfully opened sheet: '{sh.title}'")
        worksheet = sh.get_worksheet(0)
        logger.info(f"✓ Accessing worksheet: '{worksheet.title}'")
        all_rows = worksheet.get_all_values()
        logger.info(f"✓ Retrieved {len(all_rows)} total rows")
        if len(all_rows) < 2:
            logger.warning("No data rows found in sheet")
            return []
        headers = all_rows[0]
        data_rows = all_rows[1:]
        logger.info(f"Sheet has {len(data_rows)} data rows")
        rows_to_process = []
        for idx, row in enumerate(data_rows, start=2):
            while len(row) < 10:
                row.append('')
            jira_id = row[0] if len(row) > 0 else ''
            summary = row[1] if len(row) > 1 else ''
            priority = row[2] if len(row) > 2 else ''
            justification = row[3] if len(row) > 3 else ''
            feature_impact = row[4] if len(row) > 4 else ''
            releasedate = row[5] if len(row) > 5 else ''
            feedback = row[6] if len(row) > 6 else ''
            if feedback and feedback.strip():
                logger.info(f"  Row {idx} ({jira_id}): ✓ Has feedback")
                rows_to_process.append({'row_index': idx, 'jira_id': jira_id, 'summary': summary, 'priority': priority, 'justification': justification, 'feature_impact': feature_impact, 'releasedate': releasedate, 'feedback': feedback})
        logger.info(f"\nFound {len(rows_to_process)} rows to process")
        logger.info("=" * 80)
        return rows_to_process
    except Exception as e:
        logger.error(f"Error reading feedback rows: {e}")
        return []

def evaluate_individual_feedback(row_data):
    jira_id = row_data['jira_id']
    logger.info(f"\n{'─' * 80}")
    logger.info(f"EVALUATING: {jira_id}")
    logger.info(f"{'─' * 80}")
    if not OPENROUTER_API_KEY:
        return "Error: OPENROUTER_API_KEY not configured"
    try:
        prompt = f"""Analyze this feature's priority assignment against actual post-release feedback:

Feature: {row_data['jira_id']} - {row_data['summary']}
AI Assigned Priority: {row_data['priority']}
Justification: {row_data['justification']}
Expected Impact: {row_data['feature_impact']}
Release Date: {row_data['releasedate']}

Actual Feedback Received:
{row_data['feedback']}

Task: Compare the priority/justification with actual feedback. Was the priority appropriate? Identify key deviations and learnings for future prioritization. (2-3 sentences)"""
        logger.info(f"Calling OpenRouter API...")
        start_time = datetime.now()
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "HTTP-Referer": YOUR_SITE_URL, "X-Title": YOUR_SITE_NAME, "Content-Type": "application/json"},
            data=json.dumps({"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": prompt}]}),
            timeout=60
        )
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Response received in {elapsed:.2f}s")
        if response.status_code == 200:
            result = response.json()
            evaluation = result['choices'][0]['message']['content']
            if 'usage' in result:
                logger.info(f"Tokens used: {result['usage'].get('total_tokens', 'N/A')}")
            logger.info(f"✓ Evaluation: {evaluation[:150]}...")
            return evaluation
        else:
            error = f"API Error: {response.status_code}"
            logger.error(error)
            return error
    except Exception as e:
        error = f"Error: {str(e)}"
        logger.error(error)
        return error

def generate_summary_for_next_cycle(all_evaluations):
    logger.info("\n" + "=" * 80)
    logger.info("GENERATING SUMMARY FOR NEXT CYCLE")
    logger.info("=" * 80)
    if not OPENROUTER_API_KEY:
        return "Error: API key not configured"
    try:
        eval_texts = [f"Feature: {e['jira_id']} - {e['summary']}\nPriority: {e['priority']}\nAnalysis: {e['evaluation']}\n" for e in all_evaluations]
        combined = "\n".join(eval_texts)
        prompt = f"""Analyze these {len(all_evaluations)} feature evaluations from the last prioritization cycle:

{combined}

Synthesize insights for the NEXT prioritization cycle:
1. **Patterns**: What patterns emerge in priority misalignments? Which feature types were over/under-prioritized?
2. **Critical Learnings**: Key insights that should influence future priorities
3. **Adjustments**: Specific factors to weight differently next time
4. **Successes**: What worked well in priority predictions?

Provide a structured summary (300-400 words) to improve next round of LLM priority assignments."""
        logger.info(f"Generating summary for {len(all_evaluations)} features...")
        start_time = datetime.now()
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "HTTP-Referer": YOUR_SITE_URL, "X-Title": YOUR_SITE_NAME, "Content-Type": "application/json"},
            data=json.dumps({"model": OPENROUTER_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}),
            timeout=120
        )
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"Summary generated in {elapsed:.2f}s")
        if response.status_code == 200:
            result = response.json()
            summary = result['choices'][0]['message']['content']
            logger.info(f"✓ Summary generated ({len(summary)} chars)")
            return summary
        else:
            return f"API Error: {response.status_code}"
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return f"Error: {str(e)}"

def write_evaluation_to_sheet(row_index, evaluation_text):
    logger.info(f"Writing evaluation to row {row_index}...")
    client = get_google_sheets_client()
    if not client:
        return False
    try:
        sh = client.open(GOOGLE_SHEET)
        worksheet = sh.get_worksheet(0)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        worksheet.update_cell(row_index, 8, evaluation_text)
        worksheet.update_cell(row_index, 9, 'Processed')
        worksheet.update_cell(row_index, 10, timestamp)
        logger.info(f"✓ Written to row {row_index} at {timestamp}")
        return True
    except Exception as e:
        logger.error(f"Error writing to sheet: {e}")
        return False

def write_summary_to_sheet(summary_text):
    logger.info("Writing overall summary to sheet...")
    client = get_google_sheets_client()
    if not client:
        return False
    try:
        sh = client.open(GOOGLE_SHEET)
        worksheet = sh.get_worksheet(0)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        all_values = worksheet.get_all_values()
        next_row = len(all_values) + 2
        logger.info(f"Writing summary to row {next_row}...")
        worksheet.update_cell(next_row, 1, "=== CYCLE SUMMARY ===")
        worksheet.update_cell(next_row + 1, 1, f"Generated: {timestamp}")
        worksheet.update_cell(next_row + 2, 1, "Summary for Next Prioritization Cycle:")
        worksheet.update_cell(next_row + 3, 1, summary_text)
        logger.info(f"✓ Summary written starting at row {next_row}")
        logger.info(f"Summary preview: {summary_text[:200]}...")
        return True
    except Exception as e:
        logger.error(f"Error writing summary: {e}")
        return False

def process_all_feedback():
    execution_start = datetime.now()
    logger.info("\n" + "=" * 80)
    logger.info("STARTING FEEDBACK PROCESSING")
    logger.info("=" * 80)
    logger.info(f"Started at: {execution_start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    try:
        rows_to_process = read_feedback_rows()
        if not rows_to_process:
            logger.warning("\n⚠ No rows to process. Exiting.")
            return
        logger.info("\n" + "=" * 80)
        logger.info("PROCESSING INDIVIDUAL FEEDBACK")
        logger.info("=" * 80)
        processed_count = 0
        failed_count = 0
        all_evaluations = []
        for idx, row_data in enumerate(rows_to_process, start=1):
            logger.info(f"\n[{idx}/{len(rows_to_process)}] Processing {row_data['jira_id']}...")
            evaluation = evaluate_individual_feedback(row_data)
            if write_evaluation_to_sheet(row_data['row_index'], evaluation):
                processed_count += 1
                all_evaluations.append({'jira_id': row_data['jira_id'], 'summary': row_data['summary'], 'priority': row_data['priority'], 'evaluation': evaluation})
            else:
                failed_count += 1
        logger.info("\n" + "=" * 80)
        logger.info("INDIVIDUAL PROCESSING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Processed: {processed_count}/{len(rows_to_process)}")
        logger.info(f"Failed: {failed_count}")
        logger.info("=" * 80)
        if all_evaluations:
            logger.info("\nGenerating overall summary for next cycle...")
            summary = generate_summary_for_next_cycle(all_evaluations)
            write_summary_to_sheet(summary)
        execution_end = datetime.now()
        duration = (execution_end - execution_start).total_seconds()
        logger.info("\n" + "=" * 80)
        logger.info("EXECUTION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Started: {execution_start.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Ended: {execution_end.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Total rows processed: {processed_count}")
        logger.info(f"Summary generated: {'Yes' if all_evaluations else 'No'}")
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"Fatal error in process_all_feedback: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    process_all_feedback()

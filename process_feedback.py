import os
import gspread
from google.oauth2.service_account import Credentials
import requests
import json
from datetime import datetime
import logging
import sys
import traceback


# Logging configuration: logs to both console and a timestamped file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'llm_evaluation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

# Config loaded from environment
GOOGLE_SHEET = os.environ.get('GOOGLE_SHEET_NAME', 'YOUR_SHEET_NAME')
CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON') or os.environ.get('GOOGLE_CREDS_JSON')
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

try:
    if CREDENTIALS_JSON:
        creds_dict_debug = json.loads(CREDENTIALS_JSON)
        logger.info(f"[DEBUG] Parsed GOOGLE_CREDENTIALS_JSON, client_email: {creds_dict_debug.get('client_email', 'N/A')}")
    else:
        logger.error("[DEBUG] GOOGLE_CREDENTIALS_JSON not available for debug")
except Exception as e:
    logger.error(f"[DEBUG] Failed to parse GOOGLE_CREDENTIALS_JSON: {e}")

def get_google_sheets_client():
    logger.info("Attempting to authorize Google Sheets client...")
    if not CREDENTIALS_JSON:
        logger.error("GOOGLE_CREDENTIALS_JSON not configured")
        return None
    try:
        creds_dict = json.loads(CREDENTIALS_JSON)
        requested_scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=requested_scopes)
        client = gspread.authorize(creds)
        logger.info("✓ Successfully authorized Google Sheets client")
        return client
    except Exception as e:
        logger.error(f"Error authorizing Google Sheets: {e}")
        logger.error(traceback.format_exc())
        return None

def read_feedback_rows():
    logger.info("=" * 80)
    logger.info("READING ALL FEEDBACK ROWS FROM GOOGLE SHEETS")
    logger.info("=" * 80)
    client = get_google_sheets_client()
    if not client:
        return []
    try:
        sh = client.open(GOOGLE_SHEET)
        worksheet = sh.get_worksheet(0)
        all_rows = worksheet.get_all_values()
        logger.info(f"✓ Retrieved {len(all_rows)} total rows")
        if len(all_rows) < 2:
            logger.warning("No data rows found in sheet")
            return []
        data_rows = all_rows[1:]
        rows_to_process = []
        for idx, row in enumerate(data_rows, start=2):
            while len(row) < 9:  # Ensure all columns present
                row.append('')
            jira_id = row[0].strip() if row[0] else ''
            summary = row[1].strip() if row[1] else ''
            priority = row[2].strip() if row[2] else ''
            justification = row[3].strip() if row[3] else ''
            feature_impact = row[4].strip() if row[4] else ''
            releasedate = row[5].strip() if row[5] else ''
            # OUTPUT columns: row[6] = Reflexive Summary, row[7] = wasProcessed, row[8] = Timestamp
            if jira_id and feature_impact:
                rows_to_process.append({
                    'row_index': idx,
                    'jira_id': jira_id,
                    'summary': summary,
                    'priority': priority,
                    'justification': justification,
                    'feature_impact': feature_impact,
                    'releasedate': releasedate
                })
        logger.info(f"\nFound {len(rows_to_process)} rows to process")
        logger.info("=" * 80)
        return rows_to_process
    except Exception as e:
        logger.error(f"Error reading feedback rows: {e}")
        logger.error(traceback.format_exc())
        return []

def evaluate_individual_feedback(row_data):
    logger.info(f"\n{'─' * 80}")
    logger.info(f"EVALUATING: {row_data['jira_id']}")
    logger.info(f"{'─' * 80}")
    if not OPENROUTER_API_KEY:
        return "Error: OPENROUTER_API_KEY not configured"
    try:
        prompt = f"""Reflexive evaluation of Jira feature prioritization.

Jira ID: {row_data['jira_id']}
Jira Summary: {row_data['summary']}
STAR Priority: {row_data['priority']}
Priority Rationale: {row_data['justification']}
Feature Impact: {row_data['feature_impact']}
Task: 
- Write a single reflexive summary sentence (max 40 words) describing any significant deviation between STAR Priority/Rationale and actual Feature Impact.
- Do not add any headings. Do not elaborate further. Do not repeat inputs."""
        logger.info(f"Calling OpenRouter API...")
        start_time = datetime.now()
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": YOUR_SITE_URL,
                "X-Title": YOUR_SITE_NAME,
                "Content-Type": "application/json"
            },
            data=json.dumps({
                "model": OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}]
            }),
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
        logger.error(traceback.format_exc())
        return error

def write_evaluation_to_sheet(row_index, evaluation_text):
    logger.info(f"Writing evaluation to row {row_index}...")
    client = get_google_sheets_client()
    if not client:
        return False
    try:
        sh = client.open(GOOGLE_SHEET)
        worksheet = sh.get_worksheet(0)
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        worksheet.update_cell(row_index, 7, evaluation_text)   # Reflexive Summary (col G/7)
        worksheet.update_cell(row_index, 8, 'Processed')       # wasProcessed (col H/8)
        worksheet.update_cell(row_index, 9, timestamp)         # Timestamp (col I/9)
        logger.info(f"✓ Written to row {row_index} at {timestamp}")
        return True
    except Exception as e:
        logger.error(f"Error writing to sheet: {e}")
        logger.error(traceback.format_exc())
        return False

def generate_html_report(evaluations, output_path):
    logger.info(f"Generating HTML report at {output_path}...")
    try:
        html = []
        html.append("<html><head><meta charset='UTF-8'><title>LLM Reflexive Evaluation Report</title></head><body>")
        html.append("<h1>LLM Reflexive Prioritization Evaluation Report</h1><table border='1' cellpadding='6' cellspacing='0'>")
        html.append(
            "<tr style='background:#cacaca'><th>Jira ID</th><th>Jira Summary</th><th>STAR Priority</th><th>Priority Rationale</th><th>Feature Impact</th><th>Release Date</th><th>Reflexive Summary</th></tr>"
        )
        for entry in evaluations:
            eval_html = entry.get('reflexive_summary', '').replace('\n', '<br>')
            html.append(
                f"<tr><td>{entry.get('jira_id','')}</td>"
                f"<td>{entry.get('summary','')}</td>"
                f"<td>{entry.get('priority','')}</td>"
                f"<td>{entry.get('justification','')}</td>"
                f"<td>{entry.get('feature_impact','')}</td>"
                f"<td>{entry.get('releasedate','')}</td>"
                f"<td>{eval_html}</td></tr>"
            )
        html.append("</table></body></html>")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write('\n'.join(html))
        logger.info(f"✓ HTML report written to {output_path}")
    except Exception as e:
        logger.error(f"Error generating HTML report: {e}")
        logger.error(traceback.format_exc())

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
                all_evaluations.append({
                    'jira_id': row_data['jira_id'],
                    'summary': row_data['summary'],
                    'priority': row_data['priority'],
                    'justification': row_data['justification'],
                    'feature_impact': row_data['feature_impact'],
                    'releasedate': row_data['releasedate'],
                    'reflexive_summary': evaluation
                })
            else:
                failed_count += 1
        logger.info("\n" + "=" * 80)
        logger.info("INDIVIDUAL PROCESSING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Processed: {processed_count}/{len(rows_to_process)}")
        logger.info(f"Failed: {failed_count}")
        logger.info("=" * 80)
        execution_end = datetime.now()
        duration = (execution_end - execution_start).total_seconds()
        logger.info("\n" + "=" * 80)
        logger.info("EXECUTION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Started: {execution_start.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Ended: {execution_end.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Total rows processed: {processed_count}")
        logger.info("=" * 80)
        # HTML report generation
        docs_dir = "docs"
        os.makedirs(docs_dir, exist_ok=True)
        html_report_path = os.path.join(
            docs_dir,
            f"llm_evaluation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )
        generate_html_report(all_evaluations, html_report_path)
        import shutil
        shutil.copyfile(html_report_path, os.path.join(docs_dir, "latest_report.html"))
        logger.info(f"HTML report(s) generated! Publish (commit/push) to GitHub Pages or static host.")
    except Exception as e:
        logger.error(f"Fatal error in process_all_feedback: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    process_all_feedback()

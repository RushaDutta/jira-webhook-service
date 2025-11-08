import os
import gspread
from google.oauth2.service_account import Credentials
import requests
import json
from datetime import datetime

# Google Sheets configuration
GOOGLE_SHEET = os.environ.get('GOOGLE_SHEET_NAME', 'YOUR_SHEET_NAME')
CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON', None)

# Configure OpenRouter API
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
OPENROUTER_MODEL = os.environ.get('OPENROUTER_MODEL', 'openai/gpt-4o')  # Default model
YOUR_SITE_URL = os.environ.get('SITE_URL', 'https://yourapp.com')  # Optional
YOUR_SITE_NAME = os.environ.get('SITE_NAME', 'Jira Feedback Processor')  # Optional

def get_google_sheets_client():
    """Authorize and return Google Sheets client"""
    if not CREDENTIALS_JSON:
        print("Error: GOOGLE_CREDENTIALS_JSON not configured")
        return None
    
    try:
        creds_dict = json.loads(CREDENTIALS_JSON)
        creds = Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        return gspread.authorize(creds)
    except Exception as e:
        print(f"Error authorizing Google Sheets: {e}")
        return None

def read_feedback_rows():
    """Read all rows from Google Sheet that need evaluation"""
    client = get_google_sheets_client()
    if not client:
        return []
    
    try:
        sh = client.open(GOOGLE_SHEET)
        worksheet = sh.get_worksheet(0)  # First worksheet
        
        # Get all rows
        all_rows = worksheet.get_all_values()
        
        if len(all_rows) < 2:
            print("No data rows found in sheet")
            return []
        
        # Headers: jira_id, summary, priority, justification, feature_impact, releasedate, feedback, llm_evaluation, evaluation_status, timestamp
        headers = all_rows[0]
        data_rows = all_rows[1:]
        
        # Filter rows that need evaluation (have feedback but no evaluation)
        rows_to_process = []
        for idx, row in enumerate(data_rows, start=2):  # Start from row 2 (after header)
            # Ensure row has enough columns
            while len(row) < 10:
                row.append('')
            
            jira_id = row[0] if len(row) > 0 else ''
            summary = row[1] if len(row) > 1 else ''
            priority = row[2] if len(row) > 2 else ''
            justification = row[3] if len(row) > 3 else ''
            feature_impact = row[4] if len(row) > 4 else ''
            releasedate = row[5] if len(row) > 5 else ''
            feedback = row[6] if len(row) > 6 else ''
            llm_evaluation = row[7] if len(row) > 7 else ''
            evaluation_status = row[8] if len(row) > 8 else ''
            
            # Process if feedback exists but no evaluation yet
            if feedback and feedback.strip() and not llm_evaluation:
                rows_to_process.append({
                    'row_index': idx,
                    'jira_id': jira_id,
                    'summary': summary,
                    'priority': priority,
                    'justification': justification,
                    'feature_impact': feature_impact,
                    'releasedate': releasedate,
                    'feedback': feedback
                })
        
        print(f"Found {len(rows_to_process)} rows to process")
        return rows_to_process
    
    except Exception as e:
        print(f"Error reading feedback rows: {e}")
        return []

def evaluate_with_llm(row_data):
    """Send data to LLM for evaluation using OpenRouter"""
    if not OPENROUTER_API_KEY:
        return "Error: OPENROUTER_API_KEY not configured"
    
    try:
        # Construct the prompt
        prompt = f"""These are the features that were released in the last eligible cycle, along with the AI predicted feature priority, justification for that priority, and post-release feedback received for the feature.

Feature Details:
- Jira ID: {row_data['jira_id']}
- Summary: {row_data['summary']}
- AI Predicted Priority: {row_data['priority']}
- Justification for Priority: {row_data['justification']}
- Feature Impact: {row_data['feature_impact']}
- Release Date: {row_data['releasedate']}

Post-Release Feedback:
{row_data['feedback']}

Task: Go through these fields and summarize any deviations in the feedback compared to the justification used for prioritizing it - which can be used as a qualitative input for the next prioritization cycle.

Provide a concise summary (2-3 sentences) of key deviations or insights."""
        
        # Call OpenRouter API
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
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            error_msg = f"OpenRouter API Error: {response.status_code} - {response.text}"
            print(error_msg)
            return error_msg
    
    except Exception as e:
        print(f"Error calling LLM API: {e}")
        return f"Error: {str(e)}"

def write_evaluation_to_sheet(row_index, evaluation_text):
    """Write LLM evaluation back to Google Sheet"""
    client = get_google_sheets_client()
    if not client:
        return False
    
    try:
        sh = client.open(GOOGLE_SHEET)
        worksheet = sh.get_worksheet(0)
        
        # Column H (8) = LLM Evaluation, Column I (9) = Status, Column J (10) = Timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        worksheet.update_cell(row_index, 8, evaluation_text)  # LLM Evaluation
        worksheet.update_cell(row_index, 9, 'Processed')  # Status
        worksheet.update_cell(row_index, 10, timestamp)  # Timestamp
        
        print(f"  Written evaluation to row {row_index}")
        return True
    
    except Exception as e:
        print(f"Error writing evaluation: {e}")
        return False

def process_all_feedback():
    """Main function to process all feedback rows"""
    print("Starting feedback processing...")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Read rows that need processing
    rows_to_process = read_feedback_rows()
    
    if not rows_to_process:
        print("No rows to process")
        return
    
    # Process each row
    processed_count = 0
    for row_data in rows_to_process:
        print(f"\nProcessing {row_data['jira_id']}: {row_data['summary']}")
        
        # Get LLM evaluation
        evaluation = evaluate_with_llm(row_data)
        
        # Write back to sheet
        if write_evaluation_to_sheet(row_data['row_index'], evaluation):
            processed_count += 1
    
    print(f"\nProcessing complete. Processed {processed_count}/{len(rows_to_process)} rows")

if __name__ == "__main__":
    process_all_feedback()

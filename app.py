from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Google Sheets configuration
GOOGLE_SHEET = os.environ.get('GOOGLE_SHEET_NAME', 'YOUR_SHEET_NAME')
CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON', None)

@app.route('/jira-to-gsheet', methods=['POST', 'OPTIONS'])
def jira_to_gsheet():
    # Handle CORS preflight
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        
        # Safely extract data with defaults
        jira_id = data.get('issue', {}).get('key', 'UNKNOWN')
        fields = data.get('issue', {}).get('fields', {})
        summary = fields.get('summary', '')
        priority = fields.get('priority', '')
        justification = fields.get('justification', '')
        feature_impact = fields.get('featureImpact', '')
        releasedate = fields.get('releasedate', '')        
        # Log received data
        print(f"Received Jira webhook: ID={jira_id}, Summary={summary}")
        
        # Check if credentials are configured
        if not CREDENTIALS_JSON:
            return jsonify({
                "status": "warning",
                "message": "Google Sheets credentials not configured. Set GOOGLE_CREDENTIALS_JSON environment variable.",
                "received_data": {
                    "jira_id": jira_id,
                    "summary": summary,
                    "priority": priority,
                    "justification": justification,
                    "feature_impact": feature_impact,
                    "releasedate": releasedate                }
            }), 200
        
        # If credentials are available, write to Google Sheets
        try:
            import gspread
            from oauth2client.service_account import ServiceAccountCredentials
            
            scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
            creds_dict = json.loads(CREDENTIALS_JSON)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            gc = gspread.authorize(creds)
                    print(f"✓ Authorized with Google Sheets API")
            sh = gc.open(GOOGLE_SHEET)
                    print(f"✓ Opened sheet: {GOOGLE_SHEET}")
            worksheet = sh.sheet1
            worksheet.append_row([jira_id, summary, priority, justification, feature_impact, releasedate])            
                    print(f"✓ Successfully wrote row: {[jira_id, summary, priority, justification, feature_impact, releasedate]}")
            return jsonify({"status": "success", "message": "Data written to Google Sheets"}), 200
        except Exception as e:
        print(f"✗ Error writing to Google Sheets: {type(e).__name__}: {str(e)}")            return jsonify({
                "status": "error",
                "message": f"Failed to write to Google Sheets: {str(e)}",
                                "received_data": {
                    "jira_id": jira_id,
                    "summary": summary,
                    "priority": priority,
                    "justification": justification,
                    "feature_impact": feature_impact,
                    "releasedate": releasedate
                }
            }), 500
            
    except Exception as e:
        print(f"Error processing request: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/', methods=['GET'])
def health():
    return jsonify({"status": "running", "message": "Jira webhook service is active"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

from flask import Flask, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

app = Flask(__name__)

# Google Sheets configuration
GOOGLE_SHEET = os.environ.get('GOOGLE_SHEET_NAME', 'YOUR_SHEET_NAME')
CREDENTIALS_FILE = 'credentials.json'

scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
gc = gspread.authorize(creds)
sh = gc.open(GOOGLE_SHEET)
worksheet = sh.sheet1

@app.route('/jira-to-gsheet', methods=['POST'])
def jira_to_gsheet():
    data = request.json
    jira_id = data.get('issue', {}).get('key')
    fields = data.get('issue', {}).get('fields', {})
    feature_impact = fields.get('customfield_XXXXX', '')  # Replace with your custom field ID
    summary = fields.get('summary', '')
    releasedate = fields.get('releasedate', '')
    
    worksheet.append_row([jira_id, summary, feature_impact, releasedate])
    return jsonify({"status": "success"}), 200

@app.route('/', methods=['GET'])
def health():
    return jsonify({"status": "running"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

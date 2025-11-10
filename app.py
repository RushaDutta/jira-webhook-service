from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import json
import traceback

app = Flask(__name__)
CORS(app)

# Configuration
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")

@app.route("/jira-to-gsheet", methods=["POST", "OPTIONS"])
def jira_to_gsheet():
    if request.method == "OPTIONS":
        return "", 200

    try:
        data = request.json or {}
        jira_id = data.get("issue", {}).get("key", "UNKNOWN")
        fields = data.get("issue", {}).get("fields", {})
        summary = fields.get("summary", "")
        priority = fields.get("priority", "")
        justification = fields.get("justification", "")
        feature_impact = fields.get("featureImpact", "")
        feature_impact_link = fields.get("featureImpactLink", "")

        print("Received Jira webhook:")
        print(json.dumps(data, indent=2))
        print(f"Extracted: {jira_id} | {summary}")

        if not CREDENTIALS_JSON:
            print("GOOGLE_CREDENTIALS_JSON not found.")
            return jsonify({
                "status": "warning",
                "message": "Missing Google Sheets credentials"
            }), 200

        # Google Sheets write sequence
        import gspread
        from oauth2client.service_account import ServiceAccountCredentials

        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds_dict = json.loads(CREDENTIALS_JSON)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

        print("Authenticating with Google Sheets...")
        gc = gspread.authorize(creds)

        if not GOOGLE_SHEET_ID:
            raise ValueError("GOOGLE_SHEET_ID environment variable missing")

        try:
            sh = gc.open_by_key(GOOGLE_SHEET_ID)
            print(f"Opened spreadsheet: {sh.title} ({GOOGLE_SHEET_ID})")
        except Exception as e:
            print("Failed to open spreadsheet by ID")
            raise

        try:
            worksheet = sh.sheet1
            print(f"Using worksheet: {worksheet.title}")
        except Exception:
            print("Could not access sheet1, attempting first worksheet fallback...")
            worksheet = sh.get_worksheet(0)

        try:
            new_row = [jira_id, summary, priority, justification, feature_impact, feature_impact_link]
            response = worksheet.append_row(new_row, value_input_option="USER_ENTERED")
            print(f"append_row() response: {response}")
            print(f"Successfully wrote row: {new_row}")
            return jsonify({"status": "success", "message": "Row written", "row": new_row}), 200
        except Exception as e:
            print("Error appending row:")
            traceback.print_exc()
            return jsonify({
                "status": "error",
                "message": f"append_row() failed: {str(e)}"
            }), 500

    except Exception as e:
        print("Uncaught error in jira_to_gsheet:")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/", methods=["GET"])
def health():
    return jsonify({"status": "running", "message": "Jira webhook service active"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

import openai
import gspread
import json
import re
import os
from datetime import datetime
from flask import Flask, jsonify, request

app = Flask(__name__)

openai_client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def setup_service_account():
    service_account_info = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if service_account_info:
        with open("service-account.json", "w") as f:
            f.write(service_account_info)

setup_service_account()
GOOGLE_SERVICE_ACCOUNT_JSON = "service-account.json"

def connect_to_sheet():
    gc = gspread.service_account(filename=GOOGLE_SERVICE_ACCOUNT_JSON)
    sheet = gc.open_by_key("1buZXR5C9LdINSQ3BLaDsNyS036fAV-g6XMkL1Fdji_c")
    return sheet.worksheet("Log")

def extract_json_from_gpt(text):
    match = re.search(r"""```json(.*?)```""", text, re.DOTALL)
    if not match:
        raise ValueError("No valid JSON found in GPT response.")
    
    raw_json = match.group(1).strip()
    print("=== Raw GPT Output ===")
    print(raw_json)
    
    def sanitize_reply_field(m):
        reply = m.group(1)
        clean = reply.replace('\\n', ' ').replace('\\r', ' ').replace('\\t', ' ')
        clean = clean.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
        return f'"reply": "{clean}"'
    
    cleaned_json = re.sub(r'"reply":\s*"(.*?)"', sanitize_reply_field, raw_json, flags=re.DOTALL)
    return json.loads(cleaned_json)

def get_nutrition_info(meal_text):
    prompt = f"""
You are a friendly, motivating nutrition coach. A user just told you they ate:
"{meal_text}"

Estimate total calories, protein, carbs, and fat. Reply only in valid JSON format inside triple backticks like this:

```json
{{
  "calories": 220,
  "protein_g": 6,
  "carbs_g": 30,
  "fat_g": 8,
  "reply": "Nice! That gives you about 220 kcal with 6g protein. Light and energizing!"
}}
```
"""
    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    raw_reply = response.choices[0].message.content
    return extract_json_from_gpt(raw_reply)

@app.route('/log-meal', methods=['POST'])
def log_meal():
    try:
        data = request.get_json()
        meal_text = data.get("meal")
        user_id = data.get("user_id", "unknown_user")
        
        if not meal_text:
            return jsonify({"error": "Missing 'meal' field"}), 400
        
        nutrition = get_nutrition_info(meal_text)
        
        sheet = connect_to_sheet()
        sheet.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            user_id,
            meal_text,
            nutrition["calories"],
            nutrition["protein_g"],
            nutrition["carbs_g"],
            nutrition["fat_g"],
            nutrition["reply"]
        ])
        
        return jsonify({"reply": nutrition["reply"]})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "Nutrition Tracking API",
        "endpoints": {
            "/log-meal": "POST - Log a meal and get nutrition info",
            "/health": "GET - Health check"
        }
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

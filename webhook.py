import os
import sys
from datetime import datetime

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, JoinEvent
from openai import OpenAI
# 注意：移除了 APScheduler 和 dotenv (Vercel 環境變數直接在網頁設定)

# ================= 設定區 =================
# 在 Vercel 上，不要使用 load_dotenv()，因為變數是設在 Vercel 後台
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

BOT_TRIGGER_KEYWORD = "@雞蛋鳥健康助手"
BOT_TEST_KEYWORD = "@雞蛋鳥健康助手 測試三餐建議"

DAILY_MORNING_PROMPT = """
請在 200 字以內給我母親今天的三餐飲食建議。
你的回覆格式要是「摯愛的母親早安！雞蛋鳥今天建議你早餐吃XXX，午餐吃XXX，晚餐吃XXX，保持健康愉快好心情，就跟我吃杏仁一樣！」。
請根據以下條件給出建議：
IMPORTANT : 請用台灣常用語句、繁體中文回答。
1. 母親今年 60 歲，BMI 較低，需要吃較多蛋白質和熱量
2. 母親早餐較常吃吐司、蛋餅、漢堡、三明治等西式麵包類食物，午晚餐類別豐富，可以是便當，可以是日本料理或韓式料理，也可以是西餐。
3. 請考慮健康狀況自由組合她合適的三餐，並且按照我給你的格式回覆就好，不要講額外的話。
4. 此外，可以在最後根據當天是禮拜幾，加上額外行程通知：禮拜一她要去針灸，禮拜二禮拜三禮拜四要打太極拳，禮拜六禮拜天提醒她要出門走走。
"""

app = Flask(__name__)

# 檢查變數 (防止忘記設環境變數)
if not all([LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, OPENAI_API_KEY]):
    print("Warning: 環境變數未設定完整")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
client = OpenAI(api_key=OPENAI_API_KEY)

def get_chatgpt_response(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "你是一個有幫助的 LINE 助理。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return "抱歉，我的 AI 大腦暫時短路了。"

# ================= 新增：Vercel Cron 專用觸發點 =================
@app.route("/cron_trigger", methods=['GET'])
def cron_trigger():
    # 這裡可以加上驗證機制，防止路人隨便撞這個網址
    # 簡單的做法是檢查 Vercel 帶來的 Header，或只要不公開網址即可
    print(f"[{datetime.now()}] Vercel Cron 喚醒，執行早報任務...")
    
    ai_msg = get_chatgpt_response(DAILY_MORNING_PROMPT)
    try:
        line_bot_api.broadcast(TextSendMessage(text=f"早安！\n{ai_msg}"))
        return "Morning Broadcast Sent!", 200
    except Exception as e:
        print(f"Error: {e}")
        return f"Error: {e}", 500

# ================= 原本的 Webhook =================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@app.route("/")
def home():
    return "EggBird LineBot is Running on Vercel!"

@handler.add(JoinEvent)
def handle_join(event):
    welcome_msg = "摯愛的母親早安！我是雞蛋鳥健康助手，以後每天早上 8 點會準時提醒您吃飯喔！"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=welcome_msg))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.strip()
    
    if BOT_TEST_KEYWORD in user_msg:
        reply_text = get_chatgpt_response(DAILY_MORNING_PROMPT)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        return
    
    if BOT_TRIGGER_KEYWORD in user_msg:
        clean_prompt = user_msg.replace(BOT_TRIGGER_KEYWORD, "").strip()
        if not clean_prompt:
            reply_text = "雞蛋鳥健康助手登場！"
        else:
            reply_text = get_chatgpt_response(clean_prompt)
        
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# Vercel 不需要 app.run()，它會自動尋找 app 物件
if __name__ == "__main__":
    app.run(port=5000, debug=True)
import os
import sys
from datetime import datetime, timedelta, timezone

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, JoinEvent
from openai import OpenAI

# ================= 設定區 =================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

# 機器人觸發關鍵字
BOT_TRIGGER_KEYWORD = "@雞蛋鳥健康助手"

app = Flask(__name__)

# 檢查變數
if not all([LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET, OPENAI_API_KEY]):
    print("Warning: 環境變數未設定完整")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
line_handler = WebhookHandler(LINE_CHANNEL_SECRET)
client = OpenAI(api_key=OPENAI_API_KEY)

# ================= 核心邏輯：動態產生 Prompt =================
def get_daily_prompt():
    # 1. 取得台灣時間 (UTC+8)
    utc_now = datetime.now(timezone.utc)
    tw_now = utc_now + timedelta(hours=8)
    
    # 2. 判斷今天是禮拜幾 (0=週一, 1=週二, ..., 6=週日)
    weekday = tw_now.weekday()
    
    # 3. 根據星期幾決定「額外行程」
    schedule_text = ""
    if weekday == 0:   # 週一
        schedule_text = "今天是禮拜一，提醒媽媽今天要去推拿。"
    elif weekday == 1: # 週二
        schedule_text = "今天是禮拜二，提醒媽媽早上要針灸，晚上要打太極拳。"
    elif weekday == 2: # 週三
        schedule_text = "今天是禮拜三，提醒媽媽晚上要打太極拳。"
    elif weekday == 3: # 週四
        schedule_text = "今天是禮拜四，提醒媽媽早上要針灸，晚上要打太極拳。"
    elif weekday == 4: # 週五
        schedule_text = "今天是禮拜五，又是開心的一天！"
    elif weekday == 5: # 週六
        schedule_text = "今天是禮拜六，週末愉快！提醒媽媽要出門走走，曬曬太陽。"
    elif weekday == 6: # 週日
        schedule_text = "今天是禮拜天，提醒媽媽要出門走走，放鬆心情。"

    # 4. 組合最終 Prompt
    prompt = f"""
請在 200 字以內給我母親今天的三餐飲食建議。
你的回覆格式要是「摯愛的母親早安！雞蛋鳥今天建議你早餐吃XXX，午餐吃XXX，晚餐吃XXX，保持健康愉快好心情，就跟我吃杏仁一樣！」。

請根據以下條件給出建議：
IMPORTANT : 請用台灣常用語句、繁體中文回答。
1. 母親今年 60 歲，BMI 較低，需要吃較多蛋白質和熱量
2. 母親早餐較常吃吐司、蛋餅、漢堡、三明治等西式麵包類食物，午晚餐類別豐富，可以是便當，可以是日本料理或韓式料理，也可以是西餐。
3. 請考慮健康狀況自由組合她合適的三餐，並且按照我給你的格式回覆就好，不要講額外的話。
4. 此外，請務必在最後加上這句行程提醒：「{schedule_text}」
"""
    return prompt

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

# ================= Vercel Cron 觸發點 =================
@app.route("/cron_trigger", methods=['GET'])
def cron_trigger():
    print("Vercel Cron 喚醒，準備產生今日建議...")
    
    # 呼叫上面的函式，取得「今天專屬」的 Prompt
    todays_prompt = get_daily_prompt()
    
    ai_msg = get_chatgpt_response(todays_prompt)
    try:
        line_bot_api.broadcast(TextSendMessage(text=f"早安！\n{ai_msg}"))
        return "Morning Broadcast Sent!", 200
    except Exception as e:
        print(f"Error: {e}")
        return f"Error: {e}", 500

# ================= LINE Webhook =================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@line_handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.strip()
    
    # 測試功能：手動測試時，也會自動帶入「今天的星期」邏輯
    if BOT_TRIGGER_KEYWORD in user_msg:
        clean_prompt = user_msg.replace(BOT_TRIGGER_KEYWORD, "").strip()
        
        if "測試" in clean_prompt:
             # 如果是測試，也使用動態 Prompt
            todays_prompt = get_daily_prompt()
            reply_text = get_chatgpt_response(todays_prompt)
        elif not clean_prompt:
            reply_text = "雞蛋鳥健康助手登場！"
        else:
            reply_text = get_chatgpt_response(clean_prompt)
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )

# Vercel 需要這個來當入口
if __name__ == "__main__":
    app.run(port=5000, debug=True)
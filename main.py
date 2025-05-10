from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageMessage
)
import requests
import openai
import base64
import pytz
from datetime import datetime, timedelta

# 用來追蹤哪些使用者進入 AI 模式（user_id: timestamp）
ai_session_tracker = {}

# 請替換為你自己的金鑰
import os
load_dotenv()
print("LINE token:", os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"))
print("OpenAI key:", os.environ.get("OPENAI_API_KEY")[:8], "...")

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")


line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

app = Flask(__name__)

@app.route("/")
def home():
    return "LINE MomBot is running!"

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 文字訊息處理
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_text = event.message.text.strip()
    user_id = event.source.user_id
    now = datetime.now()

    if any(keyword in user_text for keyword in ["親愛的再見", "親愛的謝謝你", "謝謝你親愛的", "結束AI", "結束"]):
        reply = "好的～AI 模式已經結束囉 💗 隨時再叫我陪妳聊天～"
        del ai_session_tracker[user_id]
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        return
    
    if user_id in ai_session_tracker:
        time_elapsed = now - ai_session_tracker[user_id]
        if time_elapsed <= timedelta(minutes=10):
            # 10 分鐘內 → 用 GPT 回應
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "你是一個遠在美國的貼心的女兒，總是給溫暖又真誠的建議，用繁體中文回應"},
                        {"role": "user", "content": user_text}
                    ],
                    max_tokens=200
                )
                reply = response['choices'][0]['message']['content']
            except Exception as e:
                reply = f"AI 回覆失敗：{str(e)}"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return
        else:
            # 超過 10 分鐘 → 移除狀態
            del ai_session_tracker[user_id]

    # ✅ 第一次觸發 AI 模式
    if user_text.startswith("親愛的"):
        prompt = user_text
        ai_session_tracker[user_id] = now  # 開啟 AI 模式
        try:
            response = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "你是一個遠在美國的貼心的女兒，總是給溫暖又真誠的建議，用繁體中文回應"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200
            )
            reply = response['choices'][0]['message']['content']
        except Exception as e:
            reply = f"AI 回覆失敗：{str(e)}"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"(AI 模式開啟 10 分鐘)\n{reply}"))
        return

    # ✅ 正常邏輯（非 AI 模式）
    # 你原本的其他條件都放這裡
    if "天氣" in user_text:
        city = user_text.replace("天氣", "").strip()
        reply = get_weather(city)
    elif "鼓勵我" in user_text:
        reply = "妳很棒了，慢慢來，一切都會更好 💪"
    elif "我愛你" in user_text:
        reply = "我也超愛你～永遠支持你 💕"
    elif "女兒時間" in user_text:
        

        tw_time = datetime.now(pytz.timezone("Asia/Taipei"))
        hour = tw_time.hour
        us_time = datetime.now(pytz.timezone("America/Chicago"))


        if 5 <= hour <= 11:
            reply = f"現在是 {us_time.strftime('%Y-%m-%d %H:%M:%S')} ☀️\n媽咪～早安呀！新的一天開始了，祝你今天心情很好很好喔～"
        elif 12 <= hour <= 17:
            reply = f"現在是 {us_time.strftime('%Y-%m-%d %H:%M:%S')} 🍵\n媽咪～午安！別忘了吃點好吃的，我在芝加哥想妳～"
        elif 18 <= hour <= 22:
            reply = f"現在是 {us_time.strftime('%Y-%m-%d %H:%M:%S')} 🌆\n媽咪～辛苦一整天了，要記得放鬆一下，好好休息喔 ❤️"
        else:
            reply = f"現在是 {us_time.strftime('%Y-%m-%d %H:%M:%S')} 🌙\n媽咪～太晚了吧！都這麼晚了，要記得早點睡，晚安喔 💤"

    else:
        reply = "媽～我愛妳喔～祝妳母親節快樂 ❤️"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )

# 圖片訊息處理
@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        message_id = event.message.id
        image_content = line_bot_api.get_message_content(message_id)
        image_bytes = b''.join(chunk for chunk in image_content.iter_content())
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        image_data_uri = f"data:image/jpeg;base64,{base64_image}"

        response = openai.ChatCompletion.create(
            model="gpt-4-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "幫我描述這張圖片"},
                        {"type": "image_url", "image_url": {"url": image_data_uri}}
                    ]
                }
            ],
            max_tokens=300
        )

        gpt_reply = response['choices'][0]['message']['content']

    except Exception as e:
        gpt_reply = f"我在看圖片時出錯了：{str(e)}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=gpt_reply)
    )

# 天氣查詢
def get_weather(city):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=zh_tw"
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return "我查不到這個城市的天氣喔，換一個再試試～"

        data = response.json()
        weather = data['weather'][0]['description']
        temp_min = data['main']['temp_min']
        temp_max = data['main']['temp_max']
        feels_like = data['main']['feels_like']
        rain = data.get('rain', {}).get('1h', 0)
        wind_speed = data['wind']['speed']

        return (
            f"{city}今天是{weather}，氣溫約 {temp_min:.0f}～{temp_max:.0f}°C，"
            f"體感溫度 {feels_like:.0f}°C，風速 {wind_speed} m/s。\n"
            f"{'可能會下雨，記得帶傘喔 ☔️' if rain > 0 else '幾乎不會下雨，安心出門吧 ☀️'}\n\n"
            "媽～記得多喝水、別太累，我在美國很想妳～ 💖"
        )
    except Exception as e:
        return f"查詢天氣出錯了：{str(e)}"

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)

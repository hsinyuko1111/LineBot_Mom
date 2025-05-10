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

    if "天氣" in user_text:
        city = user_text.replace("天氣", "").strip()
        reply = get_weather(city)
    elif user_text.startswith("問AI:"):
        reply = "這是 ChatGPT 功能，未來會開放唷！"
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

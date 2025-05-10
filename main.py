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
from openai import OpenAI

# 用來追蹤哪些使用者進入 AI 模式（user_id: timestamp）
ai_session_tracker = {}

# 請替換為你自己的金鑰
import os
load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")


line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

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
                response = client.chat.completions.create(
                    model="o4-mini",
                    messages=[
                        {"role": "system", "content": "你是一個遠在美國的貼心的女兒，總是給溫暖又真誠的建議，用繁體中文回應"},
                        {"role": "user", "content": user_text}
                    ],
                    max_tokens=200
                )
                reply = response.choices[0].message.content
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
            response = client.chat.completions.create(
                model="o4-mini",
                messages=[
                    {"role": "system", "content": "你是一個遠在美國的貼心的女兒，總是給溫暖又真誠的建議，用繁體中文回應"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200
            )
            reply = response.choices[0].message.content
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

        def format_time_readable(dt):
            weekday_map = ['一', '二', '三', '四', '五', '六', '日']
            weekday = weekday_map[dt.weekday()]

            hour = dt.hour
            if hour < 12:
                period = "上午"
            else:
                period = "下午"
                if hour > 12:
                    hour -= 12

            return f"{dt.strftime('%Y 年 %m 月 %d 日')}（星期{weekday}）{period} {hour:02d} 點 {dt.strftime('%M 分')}"


        tw_time = datetime.now(pytz.timezone("Asia/Taipei"))
        hour = tw_time.hour
        us_time = datetime.now(pytz.timezone("America/Chicago"))
        formatted_time = format_time_readable(us_time)

        if 5 <= hour <= 11:
            reply = f"現在是 {formatted_time} ☀️\n媽咪～早安呀！新的一天開始了，祝你今天心情很好很好喔～"
        elif 12 <= hour <= 17:
            reply = f"現在是 {formatted_time} 🍵\n媽咪～午安！別忘了吃點好吃的，我在芝加哥想妳～"
        elif 18 <= hour <= 22:
            reply = f"現在是 {formatted_time} 🌆\n媽咪～辛苦一整天了，要記得放鬆一下，好好休息喔 ❤️"
        else:
            reply = f"現在是 {formatted_time} 🌙\n媽咪～太晚了吧！都這麼晚了，要記得早點睡，晚安喔 💤"

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

        response = client.chat.completions.create(
            model="o4-mini",
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

        gpt_reply = response.choices[0].message.content

    except Exception as e:
        gpt_reply = f"我在看圖片時出錯了：{str(e)}"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=gpt_reply)
    )

# 天氣查詢

def resolve_city_name(city_input):
    """使用 OpenWeather 地理 API 模糊解析城市名稱"""
    geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={city_input}&limit=1&appid={OPENWEATHER_API_KEY}"
    res = requests.get(geo_url)
    data = res.json()
    if not data:
        return None
    return data[0]['name'], data[0]['lat'], data[0]['lon']

def get_weather(city_input):
    try:
        # 解析城市名稱
        city_info = resolve_city_name(city_input)
        if not city_info:
            return "我找不到這個地點耶，要不要換個名字試試看？🥺"

        city, lat, lon = city_info
        url = f"http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric&lang=zh_tw"
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            return "我查不到這個城市的天氣喔，換一個再試試～"

        data = response.json()
        weather = data['weather'][0]['description']
        temp_min = data['main']['temp_min']
        temp_max = data['main']['temp_max']
        feels_like = data['main']['feels_like']
        # rain = data.get('rain', {}).get('1h', 0)
        wind_speed = data['wind']['speed']

        # 加入暖心提醒
        tips = []
        if temp_min < 15:
            tips.append("今天有點冷，記得加件外套 🧥")
        if "雨" in weather:
            tips.append("可能會下雨，記得帶傘 ☔️")
        if "晴" in weather:
            tips.append("今天天氣不錯，可以出門散步 🌞")

        tip_text = "\n".join(tips) if tips else "祝妳有個平安愉快的一天 🌷"

        # 加入時間段問候語
        tw_time = datetime.now(pytz.timezone("Asia/Taipei"))
        hour = tw_time.hour
        if 5 <= hour < 11:
            greeting = "早安，媽咪 ☀️"
        elif 11 <= hour < 17:
            greeting = "午安，媽咪 🍵"
        elif 17 <= hour < 22:
            greeting = "晚上好，媽咪 🌇"
        else:
            greeting = "夜深了，媽咪 🌙 要早點睡喔"

        time_str = tw_time.strftime("%Y 年 %m 月 %d 日（%A）%H 點 %M 分")

        return (
            f"{greeting}\n現在是 🕰️ {time_str}\n\n"
            f"{city}今天是 {weather}，氣溫約 {temp_min:.0f}～{temp_max:.0f}°C，"
            f"體感溫度 {feels_like:.0f}°C，風速 {wind_speed} m/s。\n\n"
            f"{tip_text}\n\n愛您喔啾啾 ❤️"
        )
    except Exception as e:
        return f"查詢天氣出錯了：{str(e)}"

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port)

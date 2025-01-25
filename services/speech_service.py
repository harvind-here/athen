import base64
import requests
import json
from config.settings import ELEVENLABS_API_KEY, VOICE_ID

def text_to_speech(text):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream/with-timestamps"
    headers = {
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    data = {
        "text": text,
        "model_id": "eleven_turbo_v2",
        "voice_settings": {
            "stability": 0.7,
            "similarity_boost": 0.7,
            "style": 0.0,
            "use_speaker_boost": False
        }
    }
    response = requests.post(
        url,
        json=data,
        headers=headers,
        stream=True
    )
    if response.status_code != 200:
        return None

    audio_bytes = b""
    for line in response.iter_lines():
        if line:
            json_string = line.decode("utf-8")
            response_dict = json.loads(json_string)
            audio_bytes_chunk = base64.b64decode(response_dict["audio_base64"])
            audio_bytes += audio_bytes_chunk

    return base64.b64encode(audio_bytes).decode('utf-8')
    
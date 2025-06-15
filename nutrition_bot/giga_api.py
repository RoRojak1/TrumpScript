import os
import requests

GIGA_ENDPOINT = os.getenv("GIGACHAT_URL", "https://api.gigachat.com/v1/chat")

class GigaChatClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret

    def generate(self, prompt: str) -> str:
        try:
            response = requests.post(
                GIGA_ENDPOINT,
                json={"prompt": prompt},
                auth=(self.client_id, self.client_secret),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except Exception as e:
            return f"Error contacting GigaChat: {e}"

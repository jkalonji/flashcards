import os
from datetime import date

import requests

from drive_sync import get_service, load_cards


def main():
    token = os.environ["TELEGRAM_TOKEN"]
    user_id = int(os.environ["TELEGRAM_USER_ID"])

    service = get_service()
    cards = load_cards(service)["cards"]
    today = date.today().isoformat()
    due = [c for c in cards if c.get("next_review", today) <= today]
    count = len(due)

    if count == 0:
        text = "✅ Aucune carte à réviser aujourd'hui !"
    else:
        text = (
            f"⏰ *{count} carte(s)* à réviser aujourd'hui.\n\n"
            "Lance `/review` pour commencer !"
        )

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": user_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )
    resp.raise_for_status()


if __name__ == "__main__":
    main()

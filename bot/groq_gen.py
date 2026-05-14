import json
import os
import re

from groq import Groq

_client: Groq | None = None

_PROMPT = """\
Tu es un expert en apprentissage par répétition espacée (méthode Anki/SM-2).

À partir du texte ci-dessous, génère des flashcards qui testent les concepts clés.
Réponds UNIQUEMENT avec un tableau JSON valide — aucun texte autour, aucun bloc markdown.

Format attendu :
[
  {{"question": "...", "answer": "...", "topic": "..."}},
  ...
]

Règles :
- Entre 5 et 25 cartes selon la richesse du contenu
- Questions claires et précises (une seule idée par carte)
- Réponses concises mais complètes
- "topic" : thème principal de la carte (2-4 mots)

Texte :
{text}"""


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


def generate_flashcards(text: str) -> list[dict]:
    # Cap à ~30 000 caractères pour rester dans des limites raisonnables
    if len(text) > 30_000:
        text = text[:30_000] + "\n...[contenu tronqué]"

    response = _get_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": _PROMPT.format(text=text)}],
        temperature=0.3,
    )

    raw = response.choices[0].message.content.strip()

    # Nettoyer un éventuel bloc markdown ```json ... ```
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    cards = json.loads(raw)
    if not isinstance(cards, list):
        raise ValueError("La réponse Groq n'est pas un tableau JSON.")
    return cards

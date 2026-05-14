# Flashcards Bot

Bot Telegram de révision par répétition espacée (algorithme SM-2), avec génération automatique de flashcards par IA à partir de vidéos YouTube et de fichiers Google Drive.

## Fonctionnalités

- **Révision SM-2** : sessions manuelles (`/review`) et automatiques (8h et 20h)
- **Génération automatique** : envoie un lien YouTube ou un fichier Drive, le bot génère les cartes avec Groq (`llama-3.3-70b-versatile`)
- **Stockage Drive** : les cartes sont sauvegardées dans `Flashcards/flashcards.json` sur ton Google Drive
- **Ajout manuel** : commande `/add` pour créer une carte à la main

## Commandes Telegram

| Commande | Description |
|----------|-------------|
| `/start` | Affiche l'aide |
| `/review` | Lance une session de révision |
| `/stats` | Total de cartes, dues aujourd'hui, matures |
| `/add` | Ajoute une carte manuellement |
| `/ingest` | Génère des cartes depuis une URL YouTube ou Google Drive (PDF ou TXT) |

## Stack

- Python 3.14
- `python-telegram-bot` 22.7
- `APScheduler` — sessions automatiques
- `google-api-python-client` — Google Drive
- `groq` — génération de flashcards par LLM
- `youtube-transcript-api` — extraction de transcripts YouTube
- `PyMuPDF` — extraction de texte depuis des PDFs

## Installation

### 1. Prérequis Google Cloud

1. Créer un projet Google Cloud
2. Activer l'API **Google Drive**
3. Configurer un accès **OAuth 2.0** (type "Application de bureau")
4. Télécharger `credentials.json` et le placer dans `bot/`
5. Ajouter ton email comme "Utilisateur test" dans l'écran de consentement OAuth

### 2. Variables d'environnement

Copie `.env.example` en `.env` et remplis les valeurs :

```
TELEGRAM_TOKEN=    # Token obtenu via @BotFather
TELEGRAM_USER_ID=  # Ton ID Telegram numérique
TIMEZONE=Europe/Brussels
GROQ_API_KEY=      # Clé API depuis console.groq.com
```

### 3. Lancement

```bash
cd bot
pip install -r requirements.txt
python main.py
```

La première exécution ouvre un navigateur pour autoriser l'accès Google Drive et génère `token.json`.

## Format des cartes (`flashcards.json`)

```json
{
  "cards": [
    {
      "id": "uuid-v4",
      "question": "...",
      "answer": "...",
      "topic": "...",
      "source": "https://...",
      "easiness_factor": 2.5,
      "interval": 1,
      "repetitions": 0,
      "next_review": "2026-05-15"
    }
  ]
}
```

## Utilisation de `/ingest`

1. Envoie `/ingest` dans Telegram
2. Colle une URL :
   - **YouTube** : le bot extrait le transcript et génère les cartes
   - **Google Drive (PDF ou TXT)** : le bot télécharge le fichier et génère les cartes
3. Les cartes sont ajoutées immédiatement dans Drive et disponibles à la prochaine session `/review`

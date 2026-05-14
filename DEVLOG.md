# Flashcards Bot — État des lieux (15 mai 2026)

## Objectif du projet

Système de flashcards personnelles basé sur la répétition espacée (algorithme SM-2 / style Anki), avec :
- Envoi automatique des cartes via **Telegram**
- Stockage des cartes sur **Google Drive** (fichier `flashcards.json` dans un dossier "Flashcards")
- Génération automatique de cartes depuis du contenu consulté (YouTube, PDF, fichiers texte) via **Groq AI**
- Déploiement sans serveur via **GitHub Actions** (session quotidienne de 1h à 13h30)

---

## Architecture

```
Flash_cards_automatiques/
├── .github/
│   └── workflows/
│       └── daily_notify.yml  # GitHub Actions : notif + bot 1h à 13h30
├── bot/
│   ├── main.py               # Bot Telegram principal
│   ├── sm2.py                # Algorithme SM-2
│   ├── drive_sync.py         # Lecture/écriture Google Drive
│   ├── ingest.py             # Extraction de contenu (YouTube, Drive PDF/TXT)
│   ├── groq_gen.py           # Génération de flashcards via Groq API
│   ├── notify.py             # Script autonome de notification Telegram
│   ├── requirements.txt
│   ├── credentials.json      # Credentials Google Cloud OAuth (ne pas committer)
│   └── token.json            # Token OAuth auto-généré (ne pas committer)
├── .env                      # Variables d'environnement (ne pas committer)
├── .env.example              # Modèle .env
└── DEVLOG.md                 # Ce fichier
```

### Stack technique
- **Python 3.14** (Windows 11) / **Python 3.12** (GitHub Actions)
- `python-telegram-bot==22.7` — bot Telegram (long polling)
- `APScheduler==3.10.4` — sessions automatiques à 8h et 20h (inactif en prod GitHub Actions)
- `google-api-python-client` + `google-auth-oauthlib` — Google Drive API
- `groq` — génération de flashcards via LLM (llama-3.3-70b-versatile)
- `youtube-transcript-api==1.x` — extraction de transcripts YouTube
- `PyMuPDF` — extraction de texte depuis des PDFs

---

## Format des données (`flashcards.json`)

```json
{
  "cards": [
    {
      "id": "uuid-v4",
      "question": "...",
      "answer": "...",
      "topic": "...",
      "source": "NotebookLM | Manuel | URL",
      "easiness_factor": 2.5,
      "interval": 1,
      "repetitions": 0,
      "next_review": "2026-05-14"
    }
  ]
}
```

---

## Fonctionnement du bot Telegram

| Commande | Description |
|----------|-------------|
| `/start` | Message de bienvenue + liste des commandes |
| `/review` | Lance une session manuelle (cartes dues selon SM-2) |
| `/stats` | Statistiques (total, dues aujourd'hui, matures >21j) |
| `/add` | Ajout manuel d'une carte (conversation multi-étapes) |
| `/ingest` | Génère des cartes depuis une URL (YouTube ou Google Drive PDF/TXT) |

**Session automatique (scheduler)** : à 8h et 20h, le bot envoie les cartes dont `next_review <= aujourd'hui`.

**Flux de révision** :
1. Bot envoie la question
2. Utilisateur répond (texte libre)
3. Bot affiche la réponse + 4 boutons : ❌ Raté (0) / 😅 Difficile (2) / 👍 Bien (3) / ✅ Facile (4)
4. SM-2 recalcule l'intervalle et la prochaine date de révision
5. Carte suivante dans la queue

---

## Algorithme SM-2

Implémenté dans `sm2.py`. Ratings mappés sur l'échelle 0–5 de SM-2 :
- 0 = raté → reset (interval=1, repetitions=0)
- 2 = difficile → reset
- 3 = bien → avance normalement
- 4 = facile → avance avec bonus

`easiness_factor` minimum : 1.3 (plancher SM-2 standard).

---

## Configuration requise

### Variables d'environnement (`.env`)
```
TELEGRAM_TOKEN=<token @BotFather>
TELEGRAM_USER_ID=<ID numérique Telegram>
TIMEZONE=Europe/Brussels
GROQ_API_KEY=<clé API Groq — console.groq.com>
```

### Google Cloud
1. Projet Google Cloud créé
2. **Google Drive API** activée
3. **OAuth 2.0** configuré (type "Desktop application")
4. `credentials.json` téléchargé et placé dans `bot/`
5. Email utilisateur ajouté comme **"Test user"** dans OAuth consent screen (mode Test)
6. Première exécution : ouvre le navigateur pour autoriser → génère `token.json`

### Installation
```powershell
cd bot
pip install -r requirements.txt
python main.py
```

---

## Essais et erreurs rencontrés

### 1. `python-telegram-bot` incompatible avec Python 3.14

**Versions testées :** 20.7, puis 21.3  
**Erreur :**
```
AttributeError: 'Updater' object has no attribute '_Updater__polling_cleanup_cb'
and no __dict__ for setting new attributes
```
**Cause :** Python 3.14 a modifié le comportement des `__slots__` avec le name mangling des attributs `__dunder`. Les versions ≤21.x n'avaient pas encore adapté leur code.  
**Fix :** Mise à jour vers `python-telegram-bot==22.7` (sortie mars 2026), qui intègre explicitement le support Python 3.14 (fix event loop + `__slots__`).

---

### 2. Google OAuth — Erreur 403 `access_denied`

**Erreur :**
```
Erreur 403 : access_denied
flowName=GeneralOAuthFlow
```
**Cause :** L'app OAuth est en mode **"Test"** dans Google Cloud Console. En mode Test, seuls les utilisateurs explicitement listés comme "Test users" peuvent autoriser l'app.  
**Fix :** Dans Google Cloud Console → APIs & Services → OAuth consent screen → section "Test users" → ajouter l'email Google de l'utilisateur.

---

### 3. Import NotebookLM — abandonné

**Problème initial :** Le lien de partage NotebookLM redirige vers une page de connexion Google. Même les liens "partagés" nécessitent un compte Google connecté, rendant l'automatisation complexe.

**Tentatives infructueuses :**
- `WebFetch` → redirige vers `accounts.google.com/ServiceLogin` (302)
- `copy(document.body.innerText)` dans la console → capture le chat, pas l'artifact de flashcards
- Export "Save to Drive" → non disponible pour ce type d'artifact

**Décision (15 mai 2026) :** NotebookLM abandonné comme source. Remplacé par une approche plus directe et robuste : `/ingest` avec Groq AI sur des liens YouTube et fichiers Google Drive (PDF, TXT). Playwright et `chrome_profile/` supprimés du projet.

---

### 4. `youtube-transcript-api` v1.x — API breaking change

**Erreur :**
```
type object 'YouTubeTranscriptApi' has no attribute 'get_transcript'
```
**Cause :** La v1.x a remplacé le classmethod `get_transcript()` par une API instance-based.  
**Fix :** Instancier la classe et utiliser `.fetch()` :
```python
api = YouTubeTranscriptApi()
transcript = api.fetch(video_id, languages=["fr", "en"])
text = " ".join(snippet.text for snippet in transcript)
```

---

## État actuel (15 mai 2026)

| Composant | État |
|-----------|------|
| Bot Telegram (`main.py`) | ✅ Opérationnel |
| Google Drive sync | ✅ Authentifié |
| SM-2 algorithm | ✅ Implémenté (bug d'affichage de l'intervalle à corriger) |
| `/ingest` YouTube | ✅ Testé et fonctionnel |
| `/ingest` Drive (PDF/TXT) | ✅ Implémenté, non testé |
| Notification quotidienne (GitHub Actions) | ✅ Opérationnelle |
| Session bot 1h/jour (GitHub Actions) | ✅ Opérationnelle |
| Import NotebookLM | ❌ Abandonné |
| Scheduler 8h/20h | ⚠️ Inactif en prod (GitHub Actions, fenêtre 1h à 13h30) |

---

## Prochaines étapes

Voir section **TO BE DONE** ci-dessous.

---

## TO BE DONE

### 1. Ingestion multi-sources depuis Drive

Permettre de déposer plusieurs fichiers (PDF, TXT, YouTube URLs) dans un dossier Drive dédié, et que le système les ingère automatiquement pour générer des cartes issues de sources variées.

**Question ouverte :** faut-il mélanger les cartes de sources différentes lors des sessions `/review`, ou les regrouper par sujet/source ? Les deux approches ont des mérites :
- **Mélangé** : meilleure rétention inter-domaines, simule un environnement d'examen réel
- **Par sujet** : plus cohérent pour des apprentissages structurés en séquence

---

### 2. Correction de l'algorithme SM-2 (bug critique)

**Problème constaté :** quelle que soit la réponse donnée (Raté / Difficile / Bien / Facile), le bot répond toujours "prochaine révision dans 1 jour(s)". L'intervalle n'est pas dynamique.

**Comportement attendu :**
- ❌ **Raté** → retente demain (1 jour)
- 😅 **Difficile** → retente dans quelques jours
- 👍 **Bien** → intervalle croissant selon SM-2 (ex. 4 jours → 10 jours → 25 jours…)
- ✅ **Facile** → intervalle long d'emblée (ex. 3 semaines)

Le processus doit être dynamique et cumulatif : plus une carte est bien connue, moins elle revient souvent, pour maximiser la rétention à long terme.

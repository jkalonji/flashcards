# Flashcards Bot — État des lieux (14 mai 2026)

## Objectif du projet

Système de flashcards personnelles basé sur la répétition espacée (algorithme SM-2 / style Anki), avec :
- Envoi automatique des cartes via **Telegram**
- Stockage des cartes sur **Google Drive** (fichier `flashcards.json` dans un dossier "Flashcards")
- Import des cartes depuis **NotebookLM** (source initiale)
- **Phase 2 (non commencée)** : génération automatique de cartes depuis n'importe quel contenu consulté (YouTube, PDF, articles web)

---

## Architecture

```
Flash_cards_automatiques/
├── bot/
│   ├── main.py               # Bot Telegram principal
│   ├── sm2.py                # Algorithme SM-2
│   ├── drive_sync.py         # Lecture/écriture Google Drive
│   ├── fetch_notebooklm.py   # Script Playwright pour importer depuis NotebookLM
│   ├── chrome_profile/       # Profil Chromium persistant (connexion Google conservée)
│   ├── requirements.txt
│   ├── credentials.json      # Credentials Google Cloud OAuth (ne pas committer)
│   └── token.json            # Token OAuth auto-généré (ne pas committer)
├── .env                      # Variables d'environnement (ne pas committer)
├── .env.example              # Modèle .env
└── DEVLOG.md                 # Ce fichier
```

### Stack technique
- **Python 3.14** (Windows 11)
- `python-telegram-bot==22.7` — bot Telegram (long polling)
- `APScheduler==3.10.4` — sessions automatiques à 8h et 20h
- `google-api-python-client` + `google-auth-oauthlib` — Google Drive API
- `playwright` — scraping NotebookLM (navigateur headless avec profil persistant)

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
python -m playwright install chromium
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

### 3. Impossible d'accéder aux flashcards NotebookLM

**Problème :** Le lien de partage NotebookLM (`utm_source=nlm_web_share`) redirige vers une page de connexion Google. Même les liens "partagés" via l'interface nécessitent un compte Google connecté.

**Tentatives :**
- `WebFetch` depuis Claude Code → redirige vers `accounts.google.com/ServiceLogin` (302)
- `copy(document.body.innerText)` dans la console navigateur → capture le texte du chat NotebookLM, pas celui de l'artifact de flashcards
- Export "Save to Drive" → non disponible pour ce type d'artifact dans l'interface NotebookLM

**Solution retenue :** Script `fetch_notebooklm.py` avec **Playwright** et un profil Chromium persistant. Le script :
1. Ouvre un navigateur avec le profil Google conservé (connexion unique)
2. Navigue vers l'URL de l'artifact
3. Essaie une liste de sélecteurs CSS pour trouver le conteneur de l'artifact
4. Sauvegarde le contenu brut dans `raw_content.txt` (fallback si parsing échoue)
5. Parse les flashcards (patterns Q/R, Front/Back, numérotés) et les importe dans Drive

**État actuel :** Script écrit mais pas encore exécuté avec succès (en attente de test).

---

### 4. Commande `playwright` non trouvée

**Erreur :**
```
'playwright' n'est pas reconnu en tant que commande interne ou externe
```
**Cause :** Playwright installé dans `%APPDATA%\Python\Python314\Scripts` qui n'est pas dans le PATH Windows.  
**Fix :** Utiliser `python -m playwright install chromium` au lieu de `playwright install chromium`.

---

## État actuel (14 mai 2026)

| Composant | État |
|-----------|------|
| Bot Telegram (`main.py`) | ✅ Opérationnel |
| Scheduler 8h/20h | ✅ Actif |
| Google Drive sync | ✅ Authentifié |
| SM-2 algorithm | ✅ Implémenté |
| Import NotebookLM | ⏳ Script écrit, test en cours |
| Cartes dans Drive | ❌ 0 cartes (import pas encore complété) |
| Phase 2 (auto-génération) | ❌ Non commencée |

---

## Prochaines étapes

### Immédiat
1. Finaliser l'import des cartes NotebookLM via `fetch_notebooklm.py`
   - Si le parsing auto échoue : analyser `raw_content.txt` et ajuster le parser
   - Vérifier que les cartes apparaissent dans Drive → `Flashcards/flashcards.json`
   - Tester `/review` dans Telegram

### Phase 2 — Génération automatique de cartes
Ajouter une commande `/ingest <url>` dans le bot qui :
1. Reçoit une URL (YouTube, article, PDF Google Drive)
2. Extrait le contenu (transcript YouTube via `youtube-transcript-api`, article via `trafilatura`, PDF via `PyMuPDF`)
3. Appelle l'API Claude (`claude-sonnet-4-6`) avec un prompt de génération de flashcards
4. Ajoute les cartes générées dans Drive
5. Confirme à l'utilisateur

**Dépendances à ajouter :** `anthropic`, `youtube-transcript-api`, `trafilatura`, `PyMuPDF`

### Déploiement (optionnel)
Le bot tourne actuellement en local (doit rester allumé). Pour le rendre permanent :
- **Option simple** : Windows Task Scheduler → lance `python main.py` au démarrage
- **Option cloud** : déployer sur un VPS (Railway, Render, Oracle Free Tier) avec un `Dockerfile`

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

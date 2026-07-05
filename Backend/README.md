# Novaris AI — Backend

Plateforme de lutte contre la fraude Mobile Money en Afrique de l'Ouest, développée dans le
cadre du hackathon organisé par **Clapay**. Novaris AI analyse les transactions Mobile Money
en temps réel, calcule un score de risque explicable et applique une politique de décision
configurable (autoriser, surveiller, examiner ou bloquer temporairement).

> Ce dépôt contient le backend. La plateforme cible complète comprend 14 modules
> spécialisés coordonnés par un Risk Orchestrator (voir [Vision et périmètre](#vision-et-périmètre)) ;
> **seul le module Transaction Monitoring est implémenté à ce stade**, conformément à la
> priorité "noyau stable" de la feuille de route produit.

## Sommaire

- [Vision et périmètre](#vision-et-périmètre)
- [Architecture](#architecture)
- [Stack technique](#stack-technique)
- [Module implémenté : Transaction Monitoring](#module-implémenté--transaction-monitoring)
- [Démarrage rapide](#démarrage-rapide)
- [Résultats du modèle ML](#résultats-du-modèle-ml)
- [Limites connues et prochaines étapes](#limites-connues-et-prochaines-étapes)

## Vision et périmètre

Novaris AI est pensé comme une solution d'entreprise, pas une simple démo : chaque module
expose une logique métier claire, produit un score, explique ses raisons, s'intègre à un
**Risk Orchestrator** central et peut fonctionner avec des données simulées (mock) avant
connexion à de vraies API (opérateur, KYC, core wallet...).

| Statut | Modules |
|---|---|
| ✅ Implémenté | **Transaction Monitoring** (moteur central de scoring en temps réel) |
| 🗺️ Planifié (roadmap) | Device Intelligence, Behavioural Biometrics, AML Engine, Agent Fraud Detection, SIM Swap Intelligence, Social Engineering Detection, Fraud Graph Intelligence, Geospatial Intelligence, AI Investigator, Identity Intelligence, BCEAO Compliance Engine, Predictive Fraud AI, Novaris Trust Score, Alerts/Dashboard |

Le choix de se concentrer sur un seul module en profondeur plutôt que 14 en surface est
délibéré : la feuille de route produit elle-même conclut que *"la réussite dépendra moins
du nombre de modules annoncés que de la fiabilité du noyau : recevoir une transaction,
mesurer son risque, expliquer le résultat, appliquer une politique contrôlée et conserver
une preuve complète de la décision."*

## Architecture

```
Backend/
├── main.py                        # Point d'entrée FastAPI
├── api/
│   ├── router.py                  # Agrège les routers de tous les modules
│   └── dependencies.py            # Dépendances partagées (session DB, ...)
├── core/
│   └── decision_engine.py         # Agrégation règles+ML, politique de décision (partagé
│                                   # entre modules quand le Risk Orchestrator sera étendu)
├── shared/
│   ├── config/                    # Settings (env), constantes métier
│   ├── database/                  # Engine SQLAlchemy, session, base déclarative
│   └── utils/                     # Génération d'ID, scoring générique
├── modules/
│   └── transaction_monitoring/    # Seul module implémenté (voir README dédié)
│       ├── api.py                 # Endpoints REST
│       ├── service.py             # Orchestration : enrichissement → règles → ML → décision
│       ├── repository.py          # Accès base de données
│       ├── schemas.py             # Contrats Pydantic (in/out)
│       ├── models.py              # Modèles SQLAlchemy (Customer, Transaction, Analysis)
│       ├── rules.py               # Moteur de règles métier
│       ├── ml.py                  # Inférence ML + explicabilité SHAP
│       ├── feature_engineering.py # Logique de features partagée entraînement/production
│       └── README.md              # Documentation détaillée du module
├── scripts/
│   ├── generate_synthetic_data.py # Génère un dataset réaliste de transactions
│   └── train_model.py             # Entraîne et évalue le modèle XGBoost
├── ml_models/                      # Artefacts entraînés (modèle + colonnes + métriques)
├── data/                           # Données générées (CSV, base SQLite) — non versionné
└── tests/                          # Tests unitaires et d'intégration (pytest)
```

Chaque module suit la même structure (`api / service / repository / schemas / models /
rules / ml`) : quand un nouveau module sera développé, il pourra se brancher au même
`api/router.py` et, à terme, au même `core/decision_engine.py` sans réorganisation.

## Stack technique

| Couche | Choix | Justification |
|---|---|---|
| API | FastAPI | Typage natif via Pydantic, performant, documentation OpenAPI automatique |
| Base de données | SQLAlchemy + SQLite | Zéro configuration pour le hackathon, migration vers PostgreSQL possible sans changer le code applicatif |
| Machine Learning | XGBoost + SHAP | Données tabulaires structurées, dataset synthétique de taille modeste, **explicabilité obligatoire** (cf. section suivante) — un modèle de Deep Learning n'apporterait aucun bénéfice ici et serait moins auditable |
| Tests | pytest + FastAPI TestClient | Tests unitaires (règles, décision) et d'intégration (API bout-en-bout) |

## Module implémenté : Transaction Monitoring

Analyse chaque transaction Mobile Money avant validation et retourne un score 0-100, un
niveau de risque, une décision et les raisons qui l'expliquent.

### Modèle de données

- **Customer** : titulaire de portefeuille suivi (émetteur), créé automatiquement au
  premier contact si inconnu (kyc_level, type de client, ville, ancienneté du compte).
- **Transaction** : 12 champs minimum reçus du canal d'entrée (téléphones émetteur/
  destinataire, montant, devise, type, canal, timestamp, ville, device_id, note).
- **TransactionAnalysis** : résultat d'analyse (scores règles/ML/final, décision,
  raisons, facteurs SHAP, version du modèle) — constitue la piste d'audit.

### Moteur hybride règles + ML

1. **Règles métier** (`rules.py`, 7 règles) : pic de montant, vélocité anormale,
   bénéficiaire inconnu pour un montant élevé, activité nocturne, nouveau compte à
   forte valeur, fractionnement (structuring), distribution vers plusieurs
   bénéficiaires (fan-out). Chaque règle est déterministe, pondérée et documentée en
   langage naturel — auditable indépendamment du modèle ML.
2. **Modèle ML** (`ml.py`) : XGBoost entraîné sur données synthétiques, avec un
   explicateur SHAP qui traduit les 3 facteurs les plus influents en phrases lisibles
   par un analyste.
3. **Agrégation** (`core/decision_engine.py`) : score final = moyenne pondérée
   (45 % règles / 55 % ML) avec un **plancher de sécurité** — si le score de règles
   seul dépasse 80, le score final ne peut jamais être dilué par un score ML plus bas.
   Cela garantit qu'un signal réglementaire explicite reste toujours prioritaire.

Matrice de décision (alignée sur le document produit) :

| Score final | Niveau | Décision |
|---|---|---|
| 0-29 | Faible | `ALLOW` |
| 30-59 | Modéré | `MONITOR` |
| 60-79 | Élevé | `REVIEW` |
| 80-100 | Critique | `TEMPORARY_BLOCK` |

### API

**`POST /api/v1/transactions/analyze`** — analyse une transaction et persiste le résultat.

```json
// Requête
{
  "sender_phone": "+2250700000001",
  "receiver_phone": "+2250700000099",
  "amount": 15000,
  "transaction_type": "transfer",
  "channel": "mobile_app"
}
```

```json
// Réponse (extrait)
{
  "transaction_id": "TXN-6D05ED0FC7A24086",
  "rule_score": 0.0,
  "ml_score": 0.84,
  "final_score": 0.46,
  "risk_level": "low",
  "decision": "ALLOW",
  "confidence": 0.99,
  "reasons": ["Signal ML : Montant de la transaction (impact -)"]
}
```

**`GET /api/v1/transactions/{transaction_id}`** — relit une analyse déjà calculée.

**`GET /health`** — vérification de disponibilité du service.

La documentation interactive complète (schémas, essais en direct) est disponible sur
`http://localhost:8010/docs` une fois le serveur lancé.

Détails complets (moteur de règles, feature engineering, entraînement) :
[modules/transaction_monitoring/README.md](modules/transaction_monitoring/README.md).

## Démarrage rapide

```bash
# 1. Environnement virtuel et dépendances
python -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.txt

# 2. Générer le dataset synthétique (customers.csv, transactions.csv dans data/)
venv/Scripts/python.exe scripts/generate_synthetic_data.py

# 3. Entraîner le modèle ML (sauvegardé dans ml_models/)
venv/Scripts/python.exe scripts/train_model.py

# 4. Lancer le serveur
venv/Scripts/python.exe -m uvicorn main:app --reload --port 8010

# 5. Lancer les tests
venv/Scripts/python.exe -m pytest tests/ -v
```

La base SQLite (`data/novaris.db`) et les tables sont créées automatiquement au premier
démarrage du serveur.

## Résultats du modèle ML

Sur le dataset synthétique (≈1500 clients, ≈503 000 transactions sur **12 mois**, 6
scénarios de fraude injectés, jeu de test = 20 %) :

| Métrique | Valeur |
|---|---|
| AUC-ROC | 0.999 |
| AUC-PR | 0.92 |
| Recall (seuil 0.5) | 0.97 |
| Precision (seuil 0.5) | 0.28 |

Les variables les plus influentes selon SHAP : type de transaction, bénéficiaire connu/
inconnu, écart du montant par rapport à l'habitude du client, montant moyen habituel sur
30 jours, montant, cumul des montants sur 1h. `day_of_month` et `is_payday_window`
(saisonnalité mensuelle, voir ci-dessous) figurent aussi dans le top 10.

La precision (0.60 → 0.28) a baissé par rapport à une version antérieure sur 60 jours : le
volume de transactions normales a été multiplié par ~4.5 sur 12 mois pendant que le nombre
de fraudes injectées restait stable, ce qui fait chuter le taux de fraude de 0.78 % à
0.18 % — beaucoup plus proche d'un taux réel. C'est un effet statistique attendu à recall
constant, pas une régression : c'est justement pour ça que la zone `REVIEW` existe, pour
absorber les faux positifs vers une revue humaine plutôt qu'un blocage automatique.

## Limites connues et prochaines étapes

- **Fenêtre de simulation étendue à 12 mois avec signal de paie** : une première version
  sur 60 jours ne pouvait capturer aucune saisonnalité mensuelle (ex : pics de retraits en
  début/fin de mois liés aux salaires). Le dataset simule maintenant cet effet
  (`day_of_month`, `is_payday_window`) sur un cycle annuel complet. Restent hors périmètre,
  volontairement : les dates de fêtes (Tabaski, Noël...) et les tendances pluriannuelles
  (croissance de l'usage Mobile Money, inflation), qui demanderaient soit un calendrier
  précis non vérifié, soit des données réelles multi-années.
- **Séparabilité élevée du dataset synthétique** : les scénarios de fraude injectés restent
  individuellement assez distincts des transactions normales, d'où un AUC-ROC très élevé.
  Avec des données réelles de pilote, un recalibrage des seuils et un backtesting seront
  nécessaires (cf. feuille de route produit, Phase 2 - V1 Pilote).
- **Pas de frontend** : ce dépôt est backend uniquement ; le dashboard analyste (React,
  prévu par la feuille de route) n'est pas dans ce périmètre.
- **Un seul module actif** : les 13 autres modules de la vision Novaris AI restent à l'état
  de roadmap et ne sont pas scaffoldés dans ce dépôt pour éviter de disperser l'effort
  avant que le noyau (ce module) ne soit solide.
- **Pas de file d'attente asynchrone** : les traitements batch (AML, graphe de fraude,
  prédictif) prévus par la roadmap nécessiteront une infrastructure de tâches (worker +
  broker) non présente ici.

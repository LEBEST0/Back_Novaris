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
│   └── utils/                     # ID, scoring, téléphonie/pays (18 pays), conversion devise
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
  destinataire, montant, devise, type, canal, timestamp, ville, device_id, note), plus
  `batch_id`, `agent_id`, `balance_before_sender`/`balance_after_sender` (tous optionnels).
- **TransactionAnalysis** : résultat d'analyse (scores règles/ML/final, décision,
  raisons, facteurs SHAP, version du modèle) — constitue la piste d'audit.

### Multi-pays et passerelle de paiement

Clapay opère dans 18 pays avec plusieurs devises et un vrai produit d'interopérabilité
transfrontalière et de paiement de masse. Conséquences dans le code : montants normalisés en
équivalent XOF pour le scoring (les seuils gardent le même sens réel en NGN ou GHS), un
`batch_id` optionnel pour qu'un paiement de masse déclaré (Clapay B2B, N bénéficiaires en une
opération) ne soit jamais confondu avec un fan-out frauduleux, et une détection de transit
transfrontalier (reçu d'un pays, renvoyé vers un autre en moins d'une heure — schéma de
blanchiment par superposition). Détails et résultats vérifiés en direct dans le
[README du module](modules/transaction_monitoring/README.md#modélisation-multi-pays-et-passerelle-de-paiement).

### Moteur hybride règles + ML

1. **Règles métier** (`rules.py`, 14 règles) : pic de montant, vélocité anormale,
   bénéficiaire inconnu pour un montant élevé, activité nocturne, nouveau compte à
   forte valeur, fractionnement (structuring), distribution vers plusieurs bénéficiaires
   hors paiement de masse déclaré (fan-out), transit transfrontalier, paiement de masse
   détourné (`SUSPICIOUS_BATCH`), changement d'appareil suspect (`SIM_SWAP_SIGNAL`),
   ingénierie sociale (`SOCIAL_ENGINEERING_SIGNAL`), complicité d'agent sur dépôt ou
   retrait (`AGENT_COLLUSION_CASHOUT`), solde vidé (`ACCOUNT_DRAINED`), blanchiment via
   faux marchand (`MERCHANT_LAYERING_SIGNAL`). Chaque règle est déterministe, pondérée et
   documentée en langage naturel — auditable indépendamment du modèle ML. Détail complet
   dans le [README du module](modules/transaction_monitoring/README.md).
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
  "sender_country": "Côte d'Ivoire",
  "is_cross_border": false,
  "batch_id": null,
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

**`GET /api/v1/transactions?limit=`** — liste les analyses les plus récentes (1-200,
défaut 50), pour l'interface Admin.

**`PATCH /api/v1/transactions/{transaction_id}/feedback`** — enregistre le feedback d'un
analyste (`CONFIRMED` ou `FALSE_POSITIVE`) avec une note optionnelle, pour le suivi qualité
et le calcul du taux de faux positifs.

**`GET /api/v1/dashboard/kpis`** — agrégats calculés en SQL (transactions analysées,
alertes actives, taux de blocage, revues en attente, montant de fraude confirmée, taux de
faux positifs) pour les cartes KPI du dashboard.

**`GET /api/v1/dashboard/trend?days=`** — série temporelle (transactions/alertes/score
moyen par jour) pour le graphique d'activité du dashboard.

**`GET /health`** — vérification de disponibilité du service.

La documentation interactive complète (schémas, essais en direct) est disponible sur
`http://localhost:8010/docs` une fois le serveur lancé.

Détails complets (moteur de règles, feature engineering, entraînement) :
[modules/transaction_monitoring/README.md](modules/transaction_monitoring/README.md).

## Interface Admin (Dashboard)

Un frontend React + TypeScript (`../Frontend`) consomme cette API pour donner à un
analyste ou expert risque une vue complète sur chaque décision : score final, décomposition
règles/ML, règles déclenchées, facteurs SHAP (`top_ml_factors`) et validation analyste
(confirmation / faux positif). Il reprend le thème, la typographie et les styles d'une
maquette fournie séparément (pas de Tailwind, design system CSS custom dans `src/styles.css`).

Périmètre actuel (phase 1) : dashboard (KPIs + tendance réels), formulaire d'analyse de
transaction, dossier d'investigation détaillé, rapport imprimable, et un graphe centré sur
une transaction (émetteur/destinataire/agent/device/batch — uniquement les entités
réellement présentes dans les données, nœuds = cercles, relations = arêtes avec leurs
propriétés visibles au survol). Relier entre eux les nœuds de *plusieurs* transactions (vue
réseau multi-comptes, outils de théorie des graphes, puis GNN prédictif) reste prévu pour une
phase ultérieure.

**Identité des nœuds — téléphone vs KYC** : le numéro de téléphone seul ne suffit pas à
identifier une personne dans un écosystème multi-opérateurs/multi-pays comme celui de
Clapay (un même individu peut avoir un compte Orange Money en Côte d'Ivoire et un compte
M-Pesa au Kenya). `Customer.national_id` (`modules/transaction_monitoring/models.py`) porte
donc un identifiant KYC interne, renseigné uniquement pour `kyc_level != "basic"` (KYC
basique = vérification SMS seule, pas de pièce d'identité collectée — réaliste, cf.
`KYC_WEIGHTS` dans `scripts/generate_synthetic_data.py`). Deux comptes qui partagent le même
`national_id` désignent la même personne. Le graphe et l'écran Investigation utilisent cet
identifiant quand il existe, sinon retombent sur le téléphone — jamais l'inverse.

```bash
cd ../Frontend
npm install
npm run dev  # http://localhost:5173 (ou le port suivant si occupé)
```

`VITE_API_BASE_URL` permet de pointer vers un autre backend qu'en local. Le backend autorise
tout `http://localhost:<port>` / `http://127.0.0.1:<port>` en CORS (`main.py`,
`allow_origin_regex`) car Vite change de port silencieusement s'il en trouve un déjà occupé.

**Peupler la base avec des données de démo** (transactions réalistes des 7 derniers jours,
via le vrai pipeline règles + ML, pour que le dashboard ne soit pas vide) :

```bash
venv/Scripts/python.exe scripts/seed_admin_dashboard.py
```

Inclut volontairement quelques clients KYC complet possédant deux comptes (numéros/
opérateurs/pays différents) partageant le même `national_id`, pour illustrer le cas
d'identité inter-réseaux ci-dessus.

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

Sur le dataset synthétique (≈1500 clients répartis sur **18 pays**, ≈150 agents,
≈520 000 transactions sur **12 mois**, 11 scénarios de fraude par client + 1 scénario
centré agent en 2 variantes (dépôt/retrait), jeu de test = 20 %) :

| Métrique | Valeur |
|---|---|
| AUC-ROC | 0.9997 |
| AUC-PR | 0.98 |
| Recall (seuil 0.5) | 0.98 |
| Precision (seuil 0.5) | 0.63 |

Les variables les plus influentes selon SHAP : type de transaction, montant moyen habituel
du client, bénéficiaire connu/inconnu, écart par rapport à l'habitude, montant (équivalent
XOF), cumul sur 1h. `is_new_device`, `minutes_since_last_incoming` et `batch_size_so_far`
figurent aussi dans le top 10 — le modèle exploite bien les signaux appareil/transit/batch,
pas seulement montant/vélocité. La fraude était initialement concentrée à 100% sur `transfer`
et `withdrawal` (angle mort identifié en revue) ; elle couvre maintenant aussi `deposit` et
`merchant_payment` — `bill_payment`/`airtime_purchase` restent un angle mort assumé (volume
plus faible, pas de schéma majeur documenté par le GSMA pour ces deux types).

## Limites connues et prochaines étapes

- **Fenêtre de simulation de 12 mois avec signal de paie** : capture la saisonnalité
  mensuelle (pics de retraits en début/fin de mois liés aux salaires). Restent hors
  périmètre, volontairement : les dates de fêtes (Tabaski, Noël...) et les tendances
  pluriannuelles, qui demanderaient soit un calendrier précis non vérifié, soit des données
  réelles multi-années.
- **Conversion de devise approximative** : `shared/utils/currency.py` utilise des ordres de
  grandeur indicatifs figés dans le code pour normaliser les montants entre pays, pas un
  taux de change temps réel. Suffisant pour que les seuils de règles restent cohérents entre
  devises en démo ; une intégration réelle nécessiterait un service de taux à jour.
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

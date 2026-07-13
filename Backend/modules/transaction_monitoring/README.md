# Transaction Monitoring

Module central de détection en temps réel du Risk Orchestrator Novaris AI. Analyse chaque
transaction Mobile Money avant validation et retourne un score, une décision et des raisons
explicables, en combinant un **moteur de règles** et un **modèle ML (XGBoost)**.

Conçu en tenant compte du fonctionnement réel d'une passerelle de paiement (Clapay) :
multi-pays, multi-devises et transferts transfrontaliers sont des cas normaux du produit, pas
des exceptions — voir [Modélisation multi-pays](#modélisation-multi-pays-et-passerelle-de-paiement).

**Périmètre volontairement restreint** aux wallets (dépôt, retrait, transfert P2P) via l'app
ou en agence physique — pas de paiement marchand, pas de paiement de masse B2B, pas de canaux
USSD/web/API. Ces cas n'étaient pas représentatifs des fintechs ciblées par Novaris et ont été
retirés (règles, dataset synthétique, schéma) plutôt que laissés comme angle mort silencieux.

## Endpoint

`POST /api/v1/transactions/analyze`

```json
{
  "sender_phone": "+2250700000001",
  "receiver_phone": "+2250700000099",
  "amount": 15000,
  "transaction_type": "transfer",
  "channel": "mobile_app"
}
```

`transaction_type` : `deposit` | `withdrawal` | `transfer`. `channel` : `mobile_app` | `agent`.
`currency` est optionnel et déduit du pays de l'émetteur si absent.

Champs optionnels supplémentaires : `agent_id` (dépôt/retrait traité par un agent physique),
`balance_before_sender`/`balance_after_sender` (solde du portefeuille, si le système appelant
les transmet).

Réponse : `rule_score`, `ml_score`, `final_score` (0-100), `risk_level`, `decision`
(`ALLOW`/`MONITOR`/`REVIEW`/`TEMPORARY_BLOCK`), `confidence`, `reasons` (règles + facteurs
SHAP en langage naturel), `sender_country`, `receiver_country`, `is_cross_border`.

`GET /api/v1/transactions/{transaction_id}` relit une analyse déjà calculée.

## Modèle de données

- **Customer** : titulaire de portefeuille suivi (émetteur), créé à la volée au premier
  contact si inconnu. Inclut `operator`, `country` et `customer_type` (`individual` /
  `merchant` / `agent`, utilisé pour moduler la sensibilité de certaines règles).
- **Transaction** : téléphones, montant, devise, type, canal, timestamp, ville, `device_id`,
  `agent_id`, `balance_before_sender`/`balance_after_sender` (tous deux optionnels — Novaris
  ne gère pas les soldes, il les reçoit s'ils existent).
- **TransactionAnalysis** : résultat 1:1 de l'analyse (scores, décision, raisons, version du
  modèle) — sert de piste d'audit.

### Numéros de téléphone et heure : réalisme des données

- Les numéros ivoiriens suivent le plan de numérotation à 10 chiffres (`+225` + 2 chiffres
  d'opérateur + 8 chiffres). La correspondance préfixe → opérateur (Orange : 07/08/09, MTN :
  05/06, Moov Africa : 01/02/03) est **indicative**, à usage de démo — à valider auprès de
  l'ARTCI avant tout usage hors hackathon. Pour les 17 autres pays couverts (voir plus bas),
  seuls l'indicatif et la devise sont fiables (codes ITU/ISO 4217) ; l'opérateur est assigné
  parmi les opérateurs majeurs réellement présents dans le pays, pas déduit d'un préfixe
  précis. `operator_from_phone()` retombe sur `"Autre / inconnu"` hors Côte d'Ivoire plutôt
  que d'inventer une correspondance non vérifiée.
- L'heure (`hour`) et le jour de la semaine (`day_of_week`) de chaque transaction sont
  calculés dans `feature_engineering.py` et utilisés à la fois par la règle
  `NIGHT_ACTIVITY` et comme variable du modèle ML.
- **Saisonnalité mensuelle (période de paie)** : `day_of_month` et `is_payday_window`
  (5 premiers/derniers jours du mois) sont calculés et injectés comme variables ML. Le
  dataset synthétique simule un vrai effet de paie (montants majorés en début/fin de mois),
  pour que le modèle apprenne à ne pas confondre ce pic récurrent avec une anomalie.
  Volontairement, aucune date de fête (Tabaski, Noël...) n'est simulée — le risque de
  calendrier erroné dépasserait le bénéfice pour ce module.

## Modélisation multi-pays et passerelle de paiement

Clapay opère dans 18 pays (Bénin, Burkina Faso, Cameroun, Congo, Côte d'Ivoire, Gabon,
Gambie, Ghana, Guinée Conakry, Kenya, Mali, Niger, Nigeria, Ouganda, Rwanda, Sénégal, Sierra
Leone, Tanzanie, Togo) avec plusieurs devises (XOF, XAF, GHS, NGN, KES, RWF, UGX, TZS, GMD,
GNF, SLE) et un vrai produit d'interopérabilité transfrontalière ("un seul envoi touche 10
proches à la fois, en Côte d'Ivoire comme dans la sous-région"). Trois conséquences directes
sur la conception :

### 1. Montants normalisés en équivalent XOF pour le scoring

Un seuil "montant élevé" doit avoir le même sens réel qu'il s'agisse de XOF, NGN ou GHS.
`shared/utils/currency.py` convertit chaque montant vers un équivalent XOF **uniquement pour
la logique de scoring** (ratios, seuils de règles, feature ML `amount_xof_equivalent`) ; le
montant brut et la devise d'origine restent stockés et affichés tels quels dans les raisons
et l'audit. Ces facteurs de conversion sont des **ordres de grandeur indicatifs figés dans le
code**, pas un flux de taux de change temps réel — une intégration réelle utiliserait un
service de taux à jour (même principe mock-aujourd'hui/API-demain que les autres connecteurs
du produit).

### 2. Compte mule récidiviste : la répétition + la source, pas juste le pass-through

Un cycle isolé "dépôt/réception puis retrait rapide" est un usage parfaitement normal (cash
reçu puis renvoyé à un proche dans l'heure). Ce qui distingue un compte mule, c'est la
**répétition dans le temps** combinée à une **source de financement qui se répète** — le même
complice (ou le même agent) qui alimente le compte encore et encore, plutôt que la diversité
de clients d'un commerce légitime.

`feature_engineering.compute_passthrough_cycles` reconstitue, sur 30 jours glissants, les
jambes entrantes (dépôt en agence ou transfert reçu) et sortantes (retrait ou transfert
envoyé) de CE compte, et cherche des paires entrée→sortie de montant équivalent en moins d'une
heure (mêmes constantes que le transit transfrontalier ci-dessous : `PASSTHROUGH_WINDOW_MINUTES`,
`PASSTHROUGH_AMOUNT_RATIO_RANGE`). La règle `MULE_PASSTHROUGH_PATTERN` se déclenche à partir de
3 cycles, sauf si la source de financement n'est identifiable pour aucun cycle (seuil relevé à
5, cf. `PASSTHROUGH_MIN_CYCLES_UNVERIFIED_SOURCE`) ou si `customer_type == "merchant"` (seuil
relevé à 6, pour absorber le commerce informel qui encaisse aussi en rafale mais depuis une
clientèle variée).

Vérifié en direct (`scripts/seed_admin_dashboard.py`) : 5 cycles dépôt-agence → retrait rapide,
tous financés par le même agent, sur 4 semaines — la règle reste silencieuse sur les deux
premiers cycles (sous le seuil de répétition) puis se déclenche à partir du 3ᵉ, avec
`1 source identifiée sur 5 cycles traçables` dans la description générée.

### 3. Transit transfrontalier (layering via un pays tiers)

Une technique de blanchiment classique : recevoir de l'argent dans un pays, le renvoyer très
vite vers un pays différent (parfois via un pays intermédiaire), pour casser la traçabilité.
Le module retrouve maintenant, pour l'émetteur d'une transaction, sa **dernière transaction
reçue** dans les 6 heures précédentes (`repository.get_receiver_history`, fenêtre courte car
le passthrough se joue en minutes/heures). Nouvelle règle `CROSS_BORDER_PASSTHROUGH` (poids
40) : se déclenche si un montant équivalent a été reçu il y a moins d'une heure d'un pays, et
que la transaction courante renvoie vers un pays différent. `is_cross_border` (transfert
international normal, ex : remise familiale) n'est **pas** en soi un signal de risque — c'est
un vrai produit Clapay — seule la combinaison réception-puis-renvoi-rapide-vers-un-autre-pays
l'est.

**Note technique** : la jambe entrante de ce scénario (le tiers étranger qui envoie au client
cible) a délibérément un `sender_phone` absent de `customers.csv` — ce tiers n'est pas un
client suivi par Novaris (~45 lignes sur ~520k, toutes rattachées à ce scénario, vérifié).
Ce n'est pas un bug de génération, mais ça exigeait un repli explicite côté entraînement
(`scripts/train_model.py`) : sans lui, `account_age_days` serait `NaN` et `is_cross_border`
serait calculé sur un pays manquant pour ces lignes. Le repli applique la même logique qu'en
production pour un émetteur inconnu (`repository.get_or_create_customer`) : compte considéré
vu pour la première fois à l'instant de la transaction, KYC de base, pays déduit du numéro.

Vérifié en direct : réception de 500 000 XOF du Sénégal, puis renvoi de 490 000 XOF
vers le Nigeria 20 minutes après → `CROSS_BORDER_PASSTHROUGH` déclenchée, `TEMPORARY_BLOCK`
(score 97.7).

## Réalisme du dataset : alignement GSMA / PaySim / MoMTSim

Une revue du dataset synthétique (basée sur le rapport GSMA de typologie de la fraude Mobile
Money 2024 et les travaux de référence PaySim/MoMTSim sur la simulation Mobile Money) a
identifié plusieurs écarts avec la réalité du secteur, corrigés comme suit :

| Écart identifié | Correction |
|---|---|
| Distribution uniforme des types de transaction | Le Mobile Money est avant tout une infrastructure cash-in/cash-out : distribution repondérée (deposit ~40%, withdrawal ~37%, transfer ~23%) |
| Volume d'agence irréaliste (plafonné à quelques transactions/heure) | Densité d'agents réduite + agent préféré par client (85% du temps) + heures d'affluence partagées (`AGENT_PEAK_HOURS`) — un agent occupé atteint désormais 15-30 opérations/heure en pointe, contre un plafond artificiel de 7 avant correction |
| Aucune donnée de solde | `balance_before_sender`/`balance_after_sender` simulés (ledger cohérent rejoué chronologiquement par client) ; un solde qui tombe à (quasi) zéro est l'un des signaux les plus prédictifs selon PaySim/MoMTSim |
| Scénarios de fraude = uniquement des motifs AML/blanchiment, absents des schémas dominants GSMA (usurpation, ingénierie sociale, SIM swap, fraude interne) | 3 nouveaux scénarios : `sim_swap_takeover`, `social_engineering`, `mule_passthrough` (compte mule récidiviste, cycles répétés dépôt/réception → retrait rapide) |
| `device_id` présent mais inexploité | Suivi de l'appareil habituel par client ; un changement brutal alimente `SIM_SWAP_SIGNAL` |

**Périmètre volontairement réduit** (décision produit, pas un oubli) : paiement marchand,
paiement de masse B2B et complicité d'agent au niveau agrégat (« cash-out mill ») ont été
retirés du dataset et du moteur de règles — les deux premiers car hors du périmètre wallet
app + agence de Novaris, le troisième car son seuil de déclenchement s'est avéré irréaliste
(calibré sur un volume d'agence artificiellement bas) et sa conception a été jugée trop
complexe à corriger correctement dans l'immédiat ; à reprendre plus tard avec un signal
relatif (déviation par rapport à la baseline propre de l'agent) plutôt qu'un seuil absolu.

## Moteur hybride

1. **Règles** (`rules.py`) : 13 règles déterministes et auditables. Chaque règle a un poids
   fixe et une description humaine, montants exprimés dans la devise d'origine de la
   transaction pour rester lisibles par l'analyste.
2. **ML** (`ml.py`) : XGBoost entraîné sur données synthétiques (`scripts/train_model.py`),
   avec explicabilité SHAP par transaction (top 3 facteurs).
3. **Agrégation** (`core/decision_engine.py`) : score final = moyenne pondérée
   (45% règles / 55% ML), avec un **plancher de sécurité** : si le score de règles seul
   dépasse 80, il ne peut jamais être dilué par un score ML plus bas.

| Règle | Poids | Fraude ciblée |
|---|---|---|
| `AMOUNT_SPIKE` | 35 | Montant ≥5x la moyenne habituelle du client |
| `STRUCTURING_SUSPECTED` | 35 | Fractionnement sous le seuil de déclaration |
| `CROSS_BORDER_PASSTHROUGH` | 40 | Réception puis renvoi rapide vers un autre pays (layering) |
| `MULE_PASSTHROUGH_PATTERN` | 35 | Cycles répétés dépôt/réception → retrait rapide, source de financement concentrée (compte mule récidiviste) |
| `SIM_SWAP_SIGNAL` | 35 | Nouvel appareil sur un compte établi + signal de risque |
| `HIGH_VELOCITY` | 30 | ≥3 transactions en 10 min |
| `NEW_ACCOUNT_HIGH_VALUE` | 30 | Compte <7 jours + montant élevé |
| `SOCIAL_ENGINEERING_SIGNAL` | 30 | Virement isolé (sans rafale) très supérieur à l'habitude, vers un inconnu, en self-service |
| `ACCOUNT_DRAINED` | 30 | Solde qui tombe à (quasi) zéro après la transaction |
| `UNKNOWN_RECEIVER_HIGH_AMOUNT` | 25 | Bénéficiaire jamais utilisé + montant élevé |
| `FANOUT_PATTERN` | 20 | ≥4 bénéficiaires distincts en 1h |
| `TRANSACTION_BEHAVIOUR_ANOMALY` | 20 | Confirmation trop rapide ou nombre inhabituel de modifications du montant (signal transmis par le canal appelant, ex. Amani Wallet) |
| `NIGHT_ACTIVITY` | 15 | Transaction nocturne (0h-4h) + montant significatif |

Pourquoi ML + règles et pas seulement l'un ou l'autre : les règles restent explicables et
auditables même sans modèle entraîné (garde-fou réglementaire), le ML capture des
combinaisons de signaux faibles que des règles fixes ne couvrent pas. Voir le choix ML vs
Deep Learning documenté dans la conversation d'architecture (tabulaire, dataset modeste,
explicabilité obligatoire → XGBoost + SHAP, pas de DL).

### Variables utilisées par le modèle ML (`feature_engineering.py` / `ml.py`)

| Variable | Rationale |
|---|---|
| `amount_xof_equivalent`, `sender_avg_amount_30d`, `amount_to_avg_ratio`, `has_history` | Montant normalisé multi-devises, jugé relativement à l'historique propre du client |
| `tx_count_last_10min`, `tx_count_last_1h`, `sum_amount_last_1h`, `distinct_receivers_last_1h` | Vélocité : rafales, fractionnement, fan-out |
| `hour`, `day_of_week` | Activité à des horaires atypiques |
| `day_of_month`, `is_payday_window` | Saisonnalité mensuelle (période de paie) |
| `is_known_receiver` | Signal classique : transfert vers un bénéficiaire jamais contacté |
| `account_age_days` | Prise de contrôle de compte neuf |
| `is_cross_border` | Transfert international (normal en soi, contextualise les autres signaux) |
| `minutes_since_last_incoming`, `incoming_amount_ratio`, `is_cross_border_passthrough` | Détection de transit/layering transfrontalier |
| `is_new_device` | Changement d'appareil brutal (SIM swap / prise de contrôle) |
| `is_balance_drained` | Solde qui tombe à (quasi) zéro après la transaction (si le solde est transmis) |
| `passthrough_cycle_count_30d`, `passthrough_identified_cycle_count_30d`, `passthrough_distinct_sources_30d` | Cycles dépôt/réception → retrait rapide sur 30 jours et concentration de la source de financement (compte mule récidiviste) |
| `kyc_level`, `customer_type`, `transaction_type`, `channel` (one-hot) | Niveau de vérification client, type de client, nature et canal de la transaction |

Volontairement **exclus** du modèle : les numéros bruts (sender_phone/receiver_phone —
apprendre "ce numéro précis = fraude" ne généralise pas, relève du futur module Fraud
Graph Intelligence), `sender_city` (relève de Geospatial Intelligence). `device_id` n'est
plus exclu : `is_new_device` (dérivé, pas l'identifiant brut) alimente `SIM_SWAP_SIGNAL`.

## Données synthétiques et entraînement

```bash
python scripts/generate_synthetic_data.py   # data/customers.csv, data/transactions.csv, data/agents.csv
python scripts/train_model.py               # ml_models/transaction_risk_model.joblib
```

~1500 clients répartis sur 18 pays, ~25 agents (densité calibrée pour produire des pics
horaires réalistes de 15-30+ opérations/agent, cf. section précédente), ~530k transactions sur
**12 mois**, 10 scénarios de fraude par client : `amount_spike`, `velocity_burst`,
`structuring`, `night_fraud`, `new_account_takeover`, `fanout_mule`,
`cross_border_passthrough`, `sim_swap_takeover`, `social_engineering`, `mule_passthrough`
(compte mule récidiviste, 4-7 cycles répétés sur plusieurs semaines). Résultats sur le jeu de
test (20%) : AUC-ROC ≈ 0.9997, AUC-PR ≈ 0.97, recall ≈ 0.99, precision ≈ 0.44 (seuil 0.5) — la
precision plus basse qu'une version antérieure du modèle reflète surtout le volume de fraude
labellisée nettement réduit après le recentrage du périmètre (dataset multi-pays généraliste →
wallet + agence uniquement), pas une régression de qualité du signal.

**Limite connue** : les scénarios synthétiques restent assez séparables individuellement
(d'où l'AUC très élevé) ; avec des données réelles, prévoir un recalibrage des seuils et un
backtesting (cf. feuille de route produit, Phase 2 - V1 Pilote). Les facteurs de conversion
de devise sont des ordres de grandeur indicatifs, pas des taux de change réels ; les soldes
sont simulés par un ledger cohérent mais fictif, pas des soldes réels de portefeuille.

## Lancer le serveur

```bash
venv/Scripts/python.exe -m uvicorn main:app --reload --port 8010
```

## Tests

```bash
venv/Scripts/python.exe -m pytest tests/test_transaction_monitoring.py -v
```

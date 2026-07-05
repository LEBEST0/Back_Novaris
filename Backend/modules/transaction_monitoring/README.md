# Transaction Monitoring

Module central de détection en temps réel du Risk Orchestrator Novaris AI. Analyse chaque
transaction Mobile Money avant validation et retourne un score, une décision et des raisons
explicables, en combinant un **moteur de règles** et un **modèle ML (XGBoost)**.

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

Réponse : `rule_score`, `ml_score`, `final_score` (0-100), `risk_level`, `decision`
(`ALLOW`/`MONITOR`/`REVIEW`/`TEMPORARY_BLOCK`), `confidence`, `reasons` (règles + facteurs
SHAP en langage naturel).

`GET /api/v1/transactions/{transaction_id}` relit une analyse déjà calculée.

## Modèle de données

- **Customer** : titulaire de portefeuille suivi (émetteur), créé à la volée au premier
  contact si inconnu. Inclut un champ `operator` (Orange / MTN / Moov Africa) déduit du
  préfixe du numéro via `shared/utils/phone.py`.
- **Transaction** : 12 champs bruts minimum reçus du canal d'entrée (téléphones, montant,
  devise, type, canal, timestamp, ville, device_id...).
- **TransactionAnalysis** : résultat 1:1 de l'analyse (scores, décision, raisons, version du
  modèle) — sert de piste d'audit.

### Numéros de téléphone et heure : réalisme des données

- Les numéros générés suivent le plan de numérotation ivoirien à 10 chiffres (`+225` +
  2 chiffres d'opérateur + 8 chiffres). La correspondance préfixe → opérateur (Orange :
  07/08/09, MTN : 05/06, Moov Africa : 01/02/03) est **indicative**, à usage de démo — à
  valider auprès de l'ARTCI avant tout usage hors hackathon. `operator_from_phone()`
  retombe sur `"Autre / inconnu"` pour tout numéro hors de ce format (ex : client d'un
  autre pays), donc reste robuste en production.
- Le dataset synthétique est volontairement recentré sur la **Côte d'Ivoire** (villes
  réelles : Abidjan, Bouaké, Yamoussoukro, San-Pédro, Korhogo, Daloa, Man, Gagnoa) plutôt
  que sur plusieurs pays approximatifs, pour que le format des numéros et la géographie
  restent cohérents entre eux.
- L'heure (`hour`) et le jour de la semaine (`day_of_week`) de chaque transaction sont
  calculés dans `feature_engineering.py` et utilisés à la fois par la règle
  `NIGHT_ACTIVITY` et comme variable du modèle ML (l'heure ressort régulièrement dans le
  top 3 des facteurs SHAP sur les cas de fraude nocturne).
- **Saisonnalité mensuelle (période de paie)** : `day_of_month` et `is_payday_window`
  (5 premiers/derniers jours du mois — `feature_engineering.is_payday_window`) sont
  calculés et injectés comme variables ML. Le dataset synthétique simule un vrai effet de
  paie (montants de retrait/dépôt/transfert majorés en début/fin de mois pour les
  particuliers), pour que le modèle apprenne à ne pas confondre ce pic récurrent avec une
  anomalie. Volontairement, aucune date de fête (Tabaski, Noël...) n'est simulée — le
  risque de calendrier erroné dépasserait le bénéfice pour ce module.

## Moteur hybride

1. **Règles** (`rules.py`) : 7 règles déterministes et auditables (pic de montant, vélocité,
   bénéficiaire inconnu, activité nocturne, nouveau compte, fractionnement/structuring,
   distribution vers plusieurs bénéficiaires). Chaque règle a un poids fixe et une
   description humaine.
2. **ML** (`ml.py`) : XGBoost entraîné sur données synthétiques (`scripts/train_model.py`),
   avec explicabilité SHAP par transaction (top 3 facteurs).
3. **Agrégation** (`core/decision_engine.py`) : score final = moyenne pondérée
   (45% règles / 55% ML), avec un **plancher de sécurité** : si le score de règles seul
   dépasse 80, il ne peut jamais être dilué par un score ML plus bas.

Pourquoi ML + règles et pas seulement l'un ou l'autre : les règles restent explicables et
auditables même sans modèle entraîné (garde-fou réglementaire), le ML capture des
combinaisons de signaux faibles que des règles fixes ne couvrent pas. Voir le choix ML vs
Deep Learning documenté dans la conversation d'architecture (tabulaire, dataset modeste,
explicabilité obligatoire → XGBoost + SHAP, pas de DL).

### Variables utilisées par le modèle ML (`feature_engineering.py` / `ml.py`)

| Variable | Rationale |
|---|---|
| `amount`, `sender_avg_amount_30d`, `amount_to_avg_ratio`, `has_history` | Montant jugé relativement à l'historique propre du client, pas à un seuil fixe |
| `tx_count_last_10min`, `tx_count_last_1h`, `sum_amount_last_1h`, `distinct_receivers_last_1h` | Vélocité : rafales, fractionnement, distribution vers plusieurs comptes (fan-out) |
| `hour`, `day_of_week` | Activité à des horaires atypiques |
| `day_of_month`, `is_payday_window` | Saisonnalité mensuelle (période de paie) — évite de confondre un pic récurrent avec une anomalie |
| `is_known_receiver` | Signal classique : transfert vers un bénéficiaire jamais contacté |
| `account_age_days` | Prise de contrôle de compte neuf |
| `kyc_level`, `transaction_type`, `channel` (one-hot) | Niveau de vérification client, nature et canal de la transaction |

Volontairement **exclus** du modèle : les numéros bruts (sender_phone/receiver_phone —
apprendre "ce numéro précis = fraude" ne généralise pas, relève du futur module Fraud
Graph Intelligence), `device_id` et `sender_city` (relèvent de Device Intelligence /
Geospatial Intelligence, hors périmètre de ce module).

## Données synthétiques et entraînement

```bash
python scripts/generate_synthetic_data.py   # data/customers.csv, data/transactions.csv
python scripts/train_model.py               # ml_models/transaction_risk_model.joblib
```

~1500 clients, ~503k transactions sur **12 mois** (et non 60 jours comme dans une première
version — une fenêtre de 2 mois était insuffisante pour qu'un effet de paie mensuel
apparaisse plusieurs fois et soit appris), 6 scénarios de fraude injectés (amount_spike,
velocity_burst, structuring, night_fraud, new_account_takeover, fanout_mule). Résultats sur
le jeu de test (20%) : AUC-ROC ≈ 0.999, AUC-PR ≈ 0.92, recall ≈ 0.97 à precision ≈ 0.28
(seuil 0.5).

**Pourquoi la precision a baissé par rapport à la version 60 jours (0.60 → 0.28)** : le
taux de fraude synthétique est resté à ~900 transactions en valeur absolue mais le volume
total a été multiplié par ~4.5 (plus de transactions normales sur 12 mois), ce qui fait
chuter mécaniquement le taux de fraude de 0.78% à 0.18% — beaucoup plus proche d'un taux de
fraude réel. À recall constant (0.97), une prévalence plus faible dégrade toujours la
precision : c'est un effet statistique attendu, pas une régression du modèle. C'est aussi
pour cela que le seuil `TEMPORARY_BLOCK` (80) est réservé aux cas les plus critiques et que
la zone `REVIEW` (60-79) existe : elle absorbe les faux positifs vers une revue humaine
plutôt qu'un blocage automatique.

**Limite connue** : les scénarios synthétiques restent assez séparables individuellement
(d'où l'AUC très élevé) ; avec des données réelles, prévoir un recalibrage des seuils et un
backtesting (cf. feuille de route produit, Phase 2 - V1 Pilote). Une fenêtre de 12 mois
capture la saisonnalité mensuelle mais pas les tendances pluriannuelles (croissance de
l'usage Mobile Money, inflation) — hors de portée d'un dataset synthétique de toute façon.

## Lancer le serveur

```bash
venv/Scripts/python.exe -m uvicorn main:app --reload --port 8010
```

## Tests

```bash
venv/Scripts/python.exe -m pytest tests/test_transaction_monitoring.py -v
```

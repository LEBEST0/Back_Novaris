# Transaction Monitoring

Module central de détection en temps réel du Risk Orchestrator Novaris AI. Analyse chaque
transaction Mobile Money avant validation et retourne un score, une décision et des raisons
explicables, en combinant un **moteur de règles** et un **modèle ML (XGBoost)**.

Conçu en tenant compte du fonctionnement réel d'une passerelle de paiement (Clapay) :
multi-pays, multi-devises, transferts transfrontaliers et paiements de masse sont des cas
normaux du produit, pas des exceptions — voir [Modélisation multi-pays](#modélisation-multi-pays-et-passerelle-de-paiement).

## Endpoint

`POST /api/v1/transactions/analyze`

```json
{
  "sender_phone": "+2250700000001",
  "receiver_phone": "+2250700000099",
  "amount": 15000,
  "transaction_type": "transfer",
  "channel": "mobile_app",
  "batch_id": null
}
```

`batch_id` est optionnel : à renseigner quand la transaction fait partie d'une opération de
paiement de masse (Clapay B2B) contenant plusieurs bénéficiaires. `currency` est optionnel et
déduite du pays de l'émetteur si absente.

Champs optionnels supplémentaires : `agent_id` (dépôt/retrait traité par un agent physique),
`balance_before_sender`/`balance_after_sender` (solde du portefeuille, si le système appelant
les transmet).

Réponse : `rule_score`, `ml_score`, `final_score` (0-100), `risk_level`, `decision`
(`ALLOW`/`MONITOR`/`REVIEW`/`TEMPORARY_BLOCK`), `confidence`, `reasons` (règles + facteurs
SHAP en langage naturel), `sender_country`, `receiver_country`, `is_cross_border`, `batch_id`.

`GET /api/v1/transactions/{transaction_id}` relit une analyse déjà calculée.

## Modèle de données

- **Customer** : titulaire de portefeuille suivi (émetteur), créé à la volée au premier
  contact si inconnu. Inclut `operator` et `country`, déduits du numéro
  (`shared/utils/phone.py`).
- **Transaction** : téléphones, montant, devise, type, canal, timestamp, ville, `device_id`,
  `batch_id`, `agent_id`, `balance_before_sender`/`balance_after_sender` (tous deux optionnels
  — Novaris ne gère pas les soldes, il les reçoit s'ils existent).
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

### 2. Paiement de masse (batch) : un lot déclaré n'est pas un fan-out frauduleux

Clapay B2B propose un vrai produit de paiement de masse (payer plusieurs fournisseurs/
salariés en une opération). Sans en tenir compte, la règle `FANOUT_PATTERN` (≥4
bénéficiaires distincts en 1h) générerait des faux positifs massifs sur cet usage légitime.
Solution : un `batch_id` optionnel sur la transaction. Les entrées d'historique qui
partagent le même `batch_id` que la transaction courante sont **exclues** des agrégats de
vélocité/fan-out (`tx_count_last_1h`, `sum_amount_last_1h`, `distinct_receivers_last_1h`) —
un envoi groupé à 10 bénéficiaires reste une opération unique, pas 10 signaux de risque.
Vérifié en direct : 6 transferts à 6 bénéficiaires distincts en 5 minutes **sans** batch_id
déclenchent `FANOUT_PATTERN` + `HIGH_VELOCITY` (REVIEW, score ~77) ; le même schéma **avec**
un batch_id partagé reste `ALLOW` (score ~1).

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
l'est. Vérifié en direct : réception de 500 000 XOF du Sénégal, puis renvoi de 490 000 XOF
vers le Nigeria 20 minutes après → `CROSS_BORDER_PASSTHROUGH` déclenchée, `TEMPORARY_BLOCK`
(score 97.7).

## Réalisme du dataset : alignement GSMA / PaySim / MoMTSim

Une revue du dataset synthétique (basée sur le rapport GSMA de typologie de la fraude Mobile
Money 2024 et les travaux de référence PaySim/MoMTSim sur la simulation Mobile Money) a
identifié plusieurs écarts avec la réalité du secteur, corrigés comme suit :

| Écart identifié | Correction |
|---|---|
| Distribution uniforme des 6 types de transaction (~16,7% chacun) | Le Mobile Money est avant tout une infrastructure cash-in/cash-out : distribution repondérée (deposit ~29%, withdrawal ~26%, transfer ~18%, merchant_payment ~12%, bill_payment ~9%, airtime ~6%) |
| Fraude enfermée dans le seul type `transfer` | La fraude s'étend maintenant à `withdrawal` (via `agent_collusion_cashout`) — le retrait chez un agent complice est un point d'exfiltration documenté par le GSMA |
| Aucune donnée de solde | `balance_before_sender`/`balance_after_sender` simulés (ledger cohérent rejoué chronologiquement par client) ; un solde qui tombe à (quasi) zéro est l'un des signaux les plus prédictifs selon PaySim/MoMTSim |
| Scénarios de fraude = uniquement des motifs AML/blanchiment, absents des schémas dominants GSMA (usurpation, ingénierie sociale, SIM swap, fraude interne/agent) | 3 nouveaux scénarios : `sim_swap_takeover`, `social_engineering`, `agent_collusion_cashout` |
| Rôle de l'agent absent (pas d'`agent_id`) | Pool de ~150 agents (`data/agents.csv`), lié aux dépôts/retraits ; permet de détecter un agent qui traite un volume anormal pour de nombreux clients différents |
| `device_id` présent mais inexploité | Suivi de l'appareil habituel par client ; un changement brutal alimente `SIM_SWAP_SIGNAL` |

Un point soulevé pendant cette revue mérite d'être noté explicitement : **un paiement de
masse (batch) peut lui-même être détourné** — un compte compromis peut disperser des fonds
vers des comptes mules sous couvert d'une opération "groupée" déclarée. Le module ne fait donc
pas confiance à un `batch_id` par défaut : voir `SUSPICIOUS_BATCH` ci-dessous.

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
| `SUSPICIOUS_BATCH` | 35 | Paiement de masse déclaré mais majoritairement vers des inconnus |
| `SIM_SWAP_SIGNAL` | 35 | Nouvel appareil sur un compte établi + signal de risque |
| `HIGH_VELOCITY` | 30 | ≥3 transactions en 10 min |
| `NEW_ACCOUNT_HIGH_VALUE` | 30 | Compte <7 jours + montant élevé |
| `SOCIAL_ENGINEERING_SIGNAL` | 30 | Virement isolé (sans rafale) très supérieur à l'habitude, vers un inconnu, en self-service |
| `AGENT_COLLUSION_CASHOUT` | 30 | Agent traitant un volume anormal pour de nombreux clients différents |
| `ACCOUNT_DRAINED` | 30 | Solde qui tombe à (quasi) zéro après la transaction |
| `UNKNOWN_RECEIVER_HIGH_AMOUNT` | 25 | Bénéficiaire jamais utilisé + montant élevé |
| `FANOUT_PATTERN` | 20 | ≥4 bénéficiaires distincts en 1h hors paiement de masse déclaré |
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
| `tx_count_last_10min`, `tx_count_last_1h`, `sum_amount_last_1h`, `distinct_receivers_last_1h` | Vélocité : rafales, fractionnement, fan-out — hors transactions du même batch déclaré |
| `hour`, `day_of_week` | Activité à des horaires atypiques |
| `day_of_month`, `is_payday_window` | Saisonnalité mensuelle (période de paie) |
| `is_known_receiver` | Signal classique : transfert vers un bénéficiaire jamais contacté |
| `account_age_days` | Prise de contrôle de compte neuf |
| `is_batch_operation`, `batch_size_so_far`, `batch_unknown_receiver_ratio` | Paiement de masse : taille du lot et part de bénéficiaires inconnus (détecte un batch détourné) |
| `is_cross_border` | Transfert international (normal en soi, contextualise les autres signaux) |
| `minutes_since_last_incoming`, `incoming_amount_ratio`, `is_cross_border_passthrough` | Détection de transit/layering transfrontalier |
| `is_new_device` | Changement d'appareil brutal (SIM swap / prise de contrôle) |
| `is_balance_drained` | Solde qui tombe à (quasi) zéro après la transaction (si le solde est transmis) |
| `agent_tx_count_last_1h`, `agent_distinct_senders_last_1h` | Volume/diversité de clients traités par l'agent (complicité agent) |
| `kyc_level`, `transaction_type`, `channel` (one-hot) | Niveau de vérification client, nature et canal de la transaction |

Volontairement **exclus** du modèle : les numéros bruts (sender_phone/receiver_phone —
apprendre "ce numéro précis = fraude" ne généralise pas, relève du futur module Fraud
Graph Intelligence), `sender_city` (relève de Geospatial Intelligence). `device_id` n'est
plus exclu : `is_new_device` (dérivé, pas l'identifiant brut) alimente `SIM_SWAP_SIGNAL`.

## Données synthétiques et entraînement

```bash
python scripts/generate_synthetic_data.py   # data/customers.csv, data/transactions.csv, data/agents.csv
python scripts/train_model.py               # ml_models/transaction_risk_model.joblib
```

~1500 clients répartis sur 18 pays, ~150 agents, ~519k transactions sur **12 mois**, 10
scénarios de fraude injectés (amount_spike, velocity_burst, structuring, night_fraud,
new_account_takeover, fanout_mule, cross_border_passthrough, **sim_swap_takeover**,
**social_engineering**, **batch_mule_fanout**) + un scénario indépendant centré sur l'agent
(**agent_collusion_cashout**), plus des opérations de paiement de masse légitimes (~1400
lots) pour entraîner l'exclusion batch de `FANOUT_PATTERN`. Résultats sur le jeu de test
(20%) : AUC-ROC ≈ 1.000, AUC-PR ≈ 0.99, recall ≈ 0.99, precision ≈ 0.60 (seuil 0.5) — la
precision remonte nettement par rapport à la version précédente (0.28) car les nouveaux
signaux (device, solde, agent) rendent la fraude plus distinctement séparable.

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

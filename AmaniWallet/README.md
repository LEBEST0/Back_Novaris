# Amani Wallet

Application cliente (PWA) de démonstration pour Novaris AI — dans l'esprit général des
portefeuilles Mobile Money africains. Aucune identité visuelle, logo, couleur ou texte de
ClaPay ou d'une autre entreprise n'est réutilisé.

Amani Wallet ne déplace jamais de vrai argent : la préparation de transfert affiche un
récapitulatif et s'arrête là (voir `TransferPrepare.tsx`).

## Lancer l'app

```bash
cd AmaniWallet
npm install
npm run dev   # http://127.0.0.1:5180
```

Le backend (`../Backend`) doit tourner sur `http://127.0.0.1:8010` (`uvicorn main:app --port 8010`
depuis `Backend/`, ou peupler d'abord les données de démo avec
`venv/Scripts/python.exe scripts/seed_wallet_demo.py`).

`VITE_NOVARIS_RISK_ENGINE_URL` permet de pointer vers un autre backend qu'en local.

### Compte de démonstration

```
Téléphone : +2250700000001
Code PIN  : 1234
```

Sur l'appareil/navigateur habituel (celui utilisé pour la démo), ce compte est reconnu
automatiquement (`use_trusted_device` par défaut) → **Scénario 1 : ALLOW**.

## Mode démonstration (caché)

5 clics sur le logo de l'écran de démarrage ouvrent le sélecteur de scénario. Il n'est
jamais visible ou accessible pour un utilisateur normal. 10 scénarios sont disponibles
(NORMAL_USER, NEW_DEVICE, IMPOSSIBLE_TRAVEL, CLONED_DEVICE_ID, ROOTED_DEVICE,
EMULATOR_DEVICE, RECENT_SIM_SWAP, FAILED_BIOMETRIC, FAILED_LIVENESS,
MULTIPLE_RISK_SIGNALS) — catalogue défini côté backend
(`Backend/scripts/seed_wallet_demo.py`), lu via `GET /api/v1/wallet/demo/scenarios`.

Code OTP de démonstration (écran de vérification) : **123456**.

## Ce qui est réel, calculé, ou simulé

| Donnée | Statut | Détail |
|---|---|---|
| `local_device_uuid`, empreinte d'appareil (SHA-256) | **Calculé, réel côté navigateur** | Généré/persisté localement, jamais un vrai Android ID/IMEI (`src/lib/device.ts`) |
| Plateforme, OS apparent, navigateur, écran, langue, fuseau | **Réel** | Lu depuis `navigator`/`window.screen`/`Intl` |
| Géolocalisation | **Réel si autorisé** | `navigator.geolocation`, avec gestion du refus |
| Distance/anomalie de localisation, voyage impossible | **Calculé côté serveur** | Formule haversine réelle contre la position habituelle du client et la session précédente |
| Android ID, intégrité (Play Integrity), émulateur, root, SIM/eSIM, résultat biométrique/liveness | **Simulé (mock)** | Toujours suffixé `_mock` dans le contrat API — jamais présenté comme une donnée matérielle réelle |
| Score de risque, règles déclenchées, décision (`next_action`) | **Calculé côté serveur (Novaris Risk Engine)** | `Backend/modules/wallet_access/access_rules.py` — l'app ne décide jamais elle-même |
| Solde, historique, bénéficiaires | **Fictif** | Données de démonstration seedées, aucun lien avec un système bancaire réel |

## Endpoints Novaris Risk Engine utilisés

```
POST /api/v1/access/events/access          — journalisation d'événements (APP_OPENED, etc.)
POST /api/v1/wallet/auth/login             — connexion + pipeline de risque complet
POST /api/v1/access/risk/evaluate-access   — soumission d'une réponse de défi (OTP/biométrie/liveness)
POST /api/v1/access/risk/device-check      — vérification isolée (documentation/tests)
POST /api/v1/access/risk/identity-check    — vérification isolée
POST /api/v1/access/risk/behaviour-check   — vérification isolée
POST /api/v1/access/risk/sim-check         — vérification isolée
GET  /api/v1/wallet/dashboard
GET  /api/v1/wallet/beneficiaries · POST
POST /api/v1/wallet/transfer/prepare
GET  /api/v1/wallet/history
GET  /api/v1/wallet/profile
GET  /api/v1/wallet/demo/scenarios
```

## Événements envoyés

Voir `Backend/modules/wallet_access/schemas.py` (`AccessEventIn`) pour le contrat exact.
`event_type` observés : `APP_OPENED`, `LOGIN_ATTEMPT`, `ACCESS_CHALLENGE_RESPONSE`,
`BENEFICIARY_ADDED`, `TRANSFER_PREPARED` — tous journalisés dans la table
`wallet_security_events`.

## Gestion des erreurs

`src/lib/api.ts` distingue un moteur de risque indisponible (`ApiUnavailableError`, réseau
en échec) d'une réponse d'erreur métier (identifiants invalides, session introuvable...) —
dans les deux cas, l'app affiche un message explicite et n'accorde jamais un accès par
défaut si le moteur ne répond pas.

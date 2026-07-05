# Device Intelligence

## 1. Rôle du module

Device Intelligence évalue la fiabilité d'un appareil avant une action sensible: connexion, PIN, transaction ou changement de mot de passe.

## 2. Fonctionnement production

En production, le backend reçoit un payload de métadonnées collecté côté mobile, le compare à l'historique de l'utilisateur, calcule un score de risque et renvoie une décision d'accès.

## 3. Différence entre SDK réel et payload mocké

Le SDK réel Android/iOS collecte les signaux localement sur le terminal. Dans ce sprint, le backend reçoit des données mockées envoyées directement par API pour valider le contrat fonctionnel.

## 4. Données collectées

- `user_id`
- `device_id`
- marque, modèle
- système d'exploitation et version
- état root / émulateur / VPN / proxy
- adresse IP, pays, ville
- latitude, longitude
- langue
- version applicative

## 5. Règles de scoring

- Rooted: +40
- Emulator: +45
- VPN: +20
- Proxy: +20
- Nouvel appareil: +30
- Changement de marque: +25
- Changement de modèle: +20
- Changement de pays: +25
- Changement de ville: +10
- OS très différent: +10

Cas critiques:

- `is_rooted = true` ou `is_emulator = true` force un niveau critique.
- `is_rooted = true` et `is_emulator = true` déclenche un blocage immédiat.
- `is_vpn = true` avec changement de pays élève le risque au moins au niveau `HIGH`.

Le score final est borné à `0..100`.

## 6. Décisions possibles

- `ALLOW_PIN`
- `REQUIRE_OTP`
- `REQUIRE_STEP_UP`
- `DENY_PIN`

## 7. Endpoints API

- `POST /api/v1/device-intelligence/enroll`
- `POST /api/v1/device-intelligence/analyze`
- `GET /api/v1/device-intelligence/users/{user_id}/devices`

## 8. Exemple de payload

```json
{
  "user_id": "user-001",
  "device_id": "device-001",
  "brand": "Samsung",
  "model": "Galaxy S23",
  "os_name": "Android",
  "os_version": "14",
  "app_version": "1.0.0",
  "is_rooted": false,
  "is_emulator": false,
  "is_vpn": false,
  "is_proxy": false,
  "ip_address": "196.0.0.1",
  "country": "CI",
  "city": "Abidjan",
  "latitude": 5.36,
  "longitude": -4.01,
  "language": "fr"
}
```

## 9. Exemple de réponse

```json
{
  "module_name": "device_intelligence",
  "user_id": "user-001",
  "device_id": "device-001",
  "score": 0,
  "risk_level": "LOW",
  "decision": "ALLOW_PIN",
  "reasons": [],
  "evidence": {},
  "adapter_mode": "RULE_BASED"
}
```

## 10. Limites actuelles

- Pas de vrai SDK mobile intégré.
- Pas de modèle ML entraîné.
- Pas de corrélation réseau avancée.
- Les sessions de persistance sont volontairement simples pour ce sprint.

## 11. Évolutions futures Android/iOS

- Intégration du collector natif Android/iOS.
- Ajout de signaux device integrity et attestation.
- Normalisation des buckets de version OS.
- Enrichissement avec signaux comportementaux.

## 12. Points de sécurité et confidentialité

- Ne pas collecter IMEI ni numéro de série matériel.
- Ne pas demander `READ_PHONE_STATE`.
- Réduire les données brutes envoyées au backend.
- Hasher les attributs device sensibles côté SDK.
- L'IP et le pays peuvent aussi être déterminés côté backend à partir de la requête.


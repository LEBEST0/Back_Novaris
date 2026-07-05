# Device Intelligence

Module de scoring de confiance appareil pour Novaris AI.

- Analyse rule-based pour ce sprint.
- Enrôle un appareil de confiance par utilisateur.
- Retourne une décision d'accès sensible: `ALLOW_PIN`, `REQUIRE_OTP`, `REQUIRE_STEP_UP`, `DENY_PIN`.
- Prévu pour accueillir un prédicteur ML plus tard sans changer le contrat API.

## Persistance durable de l'historique appareil

L'historique appareil est stocké dans SQLite via SQLAlchemy pour garder une mémoire entre redémarrages en environnement de développement.

- `create_all()` est utilisé pour ce sprint V1 afin d'initialiser les tables.
- Cela reste acceptable tant qu'Alembic n'est pas encore en place.
- En production, il faudra migrer vers PostgreSQL avec des migrations Alembic.

Le module ne stocke pas de données matérielles sensibles non nécessaires comme IMEI ou numéro de série.

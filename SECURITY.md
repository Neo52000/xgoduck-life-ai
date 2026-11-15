# Sécurité du projet XGO-Duck Life AI

Projet expérimental : **ne pas exposer publiquement le tableau de bord sans audit de sécurité préalable**.

- Garder le dépôt **privé** pendant les essais.
- Générer des valeurs uniques pour `ADMIN_PASSWORD`, `ROBOT_API_KEY`, `DB_PASSWORD`.
- Placer les secrets dans `.env` ou un coffre à secrets, jamais dans Git.
- Limiter l'accès au VPS avec VPN ou reverse proxy HTTPS; sauvegarder chiffré la base de mémoire et les images.
- Ne pas permettre au moteur d'auto-amélioration de modifier la production directement; examen humain systématique.
- Ne pas donner à l'agent de génération de code les identifiants de production ou un accès direct aux souvenirs privés.
- Toute fuite de secret nécessite une rotation immédiate du secret et une recherche dans l'historique Git.
- Le contrôle moteur n'entre pas dans le périmètre de Life AI V3.3.

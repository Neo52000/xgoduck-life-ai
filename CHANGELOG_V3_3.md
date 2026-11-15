# Changelog — Life AI V3.3

## Nouveau

- `lifeai/continuous.py` : cycles quotidiens, archivage des mesures, benchmark visuel hors échantillon, comparaisons et dossier de validation.
- `lifeai/models.py` : tables additives `evolution_cycles` et `release_assessments`, sans altération des données précédentes.
- `lifeai/app.py` : cinq nouvelles routes administrateur en lecture/écriture contrôlée, aucune commande système ni moteur.
- `lifeai/run_continuous.py` : exécution quotidienne par cron possible dans le conteneur Docker.
- `tools/run_continuous.py` : même cycle en local.
- Interface web enrichie : métriques quotidiennes, tableau de versions et dossier de revue.
- `tests/test_v33_continuous.py` : huit nouveaux tests hors réseau.

## Maintenu depuis V3

- Reconnaissance et apprentissage visuels supervisés.
- Mémoire SQLite ou PostgreSQL persistante.
- Recherche encyclopédique limitée, validation des connaissances.
- Analyse des erreurs et propositions d'amélioration.
- Génération facultative de correctifs sur une machine indépendante.
- Aucune fusion/déploiement automatique ni contrôle moteur.

## Limites documentées

- Les mesures de reconnaissance hors échantillon dépendent des images réellement fournies.
- Le système n'authentifie pas cryptographiquement l'origine des attestations CI.
- Les dossiers de version décrivent une décision humaine ; ils ne la remplacent pas.
- Pas de branche ou PR GitHub créée automatiquement.
- Aucun test sur un VPS réel ou un robot physique dans cet environnement.

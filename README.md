# XGO-Duck Evolution — Life AI V3.3 / Continuous Self-Evolution

**Prototype exécutable, version 3.3 — 15 novembre 2026.**

La V3.3 étend directement la V3 et conserve V1, V2 et V3 : perception par photographie, mémoire locale/PostgreSQL, propositions d'IA, connaissances vérifiées, diagnostic mesurable et préparation supervisée de patches de code. **Aucun servomoteur, firmware ou contrôle de locomotion n'est inclus.**

## Nouveautés opérationnelles V3.3

1. **Bilan quotidien indépendant** `python -m tools.run_continuous` ou `POST /api/evolution/continuous/cycle`. Maximum un cycle par date UTC, conservé en base.
2. **Historique de mesures** : révision du programme, erreurs récurrentes, observations inconnues, données de mémoire, tendances et diagnostic V3 lié.
3. **Banc d'essai visuel reproductible hors ligne** : pour chaque objet confirmé, la première photo est la référence ; les autres photos confirmées sont testées comme vues indépendantes. Copies exactement identiques et empreintes contradictoires exclues. Les résultats incluent succès, confusions, abstentions, couverture et SHA-256 du jeu de test.
4. **Comparaison prudente de versions** : le programme refuse d'attribuer un progrès à une nouvelle version si les empreintes des jeux de test diffèrent ou s'il y a moins de huit vues évaluables. Les tendances de simples compteurs ne prouvent pas une amélioration du code.
5. **Dossier de préparation de version** : une proposition V3 déjà approuvée pour étude peut être associée à deux bilans de révisions distinctes, un compte rendu CI, une revue de sécurité et un plan de retour arrière. Verdict : `eligible_for_human_review` ou `insufficient_evidence`.
6. **Validation à deux niveaux** : le responsable approuve d'abord l'étude du correctif, puis examine séparément le dossier de version. Même l'approbation finale **ne fusionne, n'installe et ne déploie jamais de code**.
7. **Tableau de bord V3.3** : nouveaux indicateurs, historique des cycles, dossiers et formulaire avancé facultatif. API protégée : la clé robot ne peut ni effectuer de bilan technique ni autoriser une version.

### Ce que V3.3 ne fait pas

- Pas d'entraînement de réseaux neuronaux, pas de correction garantie : les résultats d'une IA restent soumis à validation.
- Pas de développement automatique déclenché par le VPS : l'agent de génération de patches V3 reste **facultatif**, indépendant et exécuté après accord sur une machine de développement.
- Pas de déploiement, de fusion Git, de commandes shell depuis le tableau de bord, d'accès au firmware, ni de commande des moteurs.
- Pas de vérification cryptographique de l'origine des comptes rendus CI transmis : les valeurs saisies constituent des attestations humaines. Le SHA-256 aide à identifier le rapport, pas à prouver la validité de son contenu.
- Le banc de tests visuel mesure uniquement la correspondance de vues **déjà confirmées**. Il ne mesure pas une vraie précision à grande échelle sur des objets jamais vus ou sur des scènes complexes.

## Démarrage local (sans VPS ni IA payante)

**Python 3.12 recommandé**. Dans le dossier extrait :

```bash
python -m pip install -r requirements.txt
python tools/init_local.py
python tools/start_local.py
```

Ouvrir **http://127.0.0.1:8000** et se connecter avec le mot de passe généré par `init_local.py`. Dans le tableau de bord, aller à « **08 / V3.3 — Évolution continue** », puis **Lancer le cycle V3.3**.

- Sans images confirmées, le test visuel renvoie `accuracy: null` et `sufficient_for_release: false`. C'est normal.
- Avec au moins deux objets connus et plusieurs vues distinctes par objet, il mesure les correspondances.
- Chaque nouveau cycle quotidien archive les mesures et permet d'observer les évolutions.

**Ne pas relancer** `init_local.py` par-dessus une ancienne installation sans lire la migration ci-dessous et sauvegarder les données.

## Mise à niveau de V3 vers V3.3 — priorité à la mémoire

La V3.3 ajoute seulement **deux tables** : `evolution_cycles` et `release_assessments`. Les tables de souvenirs V3 ne changent pas. `Base.metadata.create_all()` crée les tables manquantes, mais **n'est pas un système général de migrations**.

1. **Arrêter V3.** Sauvegarder ensemble la base SQL et toutes les images (`DATA_DIR`). Sauvegarder aussi une copie du `.env` et les réglages Docker. Tester la restauration sur une copie isolée.
2. **Conserver le projet Docker Compose et ses volumes** : ne pas renommer l'ancien dossier Compose si cela change son *project name*. Au besoin, exporter `COMPOSE_PROJECT_NAME` identique à l'ancien ou spécifier `-p ancien_nom`.
3. Installer uniquement le **code V3.3** à la place du code V3, sans remplacer l'ancien `.env` ni le dossier des données. Garder `ADMIN_PASSWORD`, `ROBOT_API_KEY`, `DB_PASSWORD`, `DATABASE_URL` et les volumes.
4. Ajouter dans `.env` : `LIFEAI_CODE_REVISION=lifeai-3.3.0`, idéalement remplacer par le SHA Git réel et unique à chaque version.
5. Redémarrer et vérifier `GET /health`, les objets déjà appris et l'onglet « Self-Evolution » avant de lancer le premier cycle V3.3.
6. En cas d'échec, arrêter V3.3, restaurer **ensemble** la base et les images sauvegardées, puis relancer l'ancienne version de code V3.

Les sauvegardes doivent être cohérentes : **l'export JSON du tableau de bord ne suffit pas** pour rétablir les images et la base.

## VPS privé — Docker et bilan planifié

Une installation neuve utilise le même déploiement HTTPS/Compose que V3 ; exemple :

```bash
cp .env.example .env
# Fournir trois mots de passe forts indépendants : ADMIN_PASSWORD, ROBOT_API_KEY, DB_PASSWORD.
# Renseigner LIFEAI_CODE_REVISION avec la version réellement installée.
chmod 600 .env
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

**Une seule exécution par jour** peut être programmée sur le VPS. En Docker V3.3, `tools/` n'est pas présent dans l'image ; utiliser le module inclus dans `lifeai/` :

```cron
15 3 * * * cd /opt/xgoduck_life_ai_v3_3 && /usr/bin/docker compose exec -T app python -m lifeai.run_continuous >> /var/log/lifeai-continuous.log 2>&1
```

En local, `python -m tools.run_continuous` reste disponible. Un cycle de bilan **n'exécute aucune proposition de code** et ne réalise aucun appel IA payant.

En production publique, prévoir un audit sécurité complémentaire, des sauvegardes supervisées, des limites de requêtes et un durcissement de l'authentification Basic Auth ; préférer dans un premier temps un tunnel SSH ou VPN privé.

## Comparer une version de référence et une candidate

Pour obtenir des mesures réellement comparables, utiliser une **copie de staging**, avec le **même jeu de photos de test figé**, jamais la mémoire privée de production. Identifier les deux révisions par leurs commits Git, exécuter la suite de tests CI sur la candidate, puis produire un bilan reproductible de chaque révision. Une mesure effectuée sur deux jours différents de production ne suffit pas à prouver un gain.

**Le formulaire avancé** demande : proposition approuvée, bilan de référence, bilan de candidate, nombre de tests réussis/total, SHA-256 du rapport CI, revue sécurité et plan de retour arrière. Il archive les preuves **déclarées** et calcule des objections explicites. Les dossiers créés sont consultables mais ne représentent pas des autorisations d'installation.

Règles du contrôle V3.3 :

- Les commits ou versions comparés doivent être différents.
- La signature SHA-256 des exemples de test doit être **identique** et comporter au moins **8 vues hors référence**.
- La candidate ne doit pas augmenter les confusions, ni diminuer l'exactitude ou la couverture.
- Tous les tests CI doivent être déclarés réussis, avec une empreinte de rapport de 64 caractères hexadécimaux.
- La revue de sécurité et le retour arrière doivent être attestés.
- Même un verdict favorable n'autorise qu'une **revue humaine supplémentaire** : un opérateur qualifié décide manuellement de la suite, hors de Life AI.

**Limite actuelle :** la V3.3 n'importe pas automatiquement les rapports provenant de bases de staging différentes. La comparaison par API utilise deux bilans déjà présents dans **la même base**. L'intégration directe d'un pipeline GitHub Actions avec des preuves attestées est une évolution future. Ne pas copier une base de production sur une machine de test sans anonymisation et autorisation.

## API V3.3 (administrateur uniquement)

| Méthode | Route | Fonction |
|---|---|---|
| `GET` | `/api/evolution/continuous` | Historique des 45 cycles et 40 dossiers récents |
| `POST` | `/api/evolution/continuous/cycle` | Diagnostic + mesures + benchmark, une fois par jour UTC |
| `GET` | `/api/evolution/benchmark` | Banc d'essai visuel à la demande, sans enregistrer de bilan |
| `POST` | `/api/evolution/releases/assess` | Évaluer un dossier de préparation, sans exécuter de code |
| `POST` | `/api/evolution/releases/{id}/review` | Examiner ou rejeter un dossier déjà évalué |

Exemple de corps JSON pour `/api/evolution/releases/assess` :

```json
{
  "proposal_id": "UUID_PROP_VALIDEE",
  "baseline_cycle_id": "UUID_BILAN_REFERENCE",
  "candidate_cycle_id": "UUID_BILAN_CANDIDATE",
  "tests_total": 32,
  "tests_passed": 32,
  "ci_report_sha256": "SHA256_HEX_64_CARACTERES",
  "security_review_attested": true,
  "rollback_prepared_attested": true
}
```

Les UUID et le SHA sont des **emplacements à remplacer** : l'exemple ci-dessus ne peut pas être utilisé tel quel. La clé `X-Robot-Key` est systématiquement refusée sur ces routes.

## Vérifications et tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check lifeai/static/app.js # facultatif, si Node.js est installé
```

**28 tests automatisés hors réseau validés** lors de la création de V3.3 : 20 hérités de V3 et 8 nouveaux. Ils couvrent la persistance, l'API administrateur, la clé robot refusée, le journal quotidien, l'indétermination des échantillons trop petits, la comparaison de révisions et le blocage de dossiers insuffisants. La fiabilité en production et la qualité visuelle sur de vraies photos nécessitent encore des essais sur l'infrastructure réelle.

---

# Historique et fonctionnalités héritées de Life AI V3

**Livrable opérationnel de démonstration — 15 novembre 2026.** Cette version reprend les fonctionnalités V2 et ajoute un diagnostic technique mesurable, des suggestions d'amélioration enregistrées dans la base, une validation administrateur et un assistant de production de *patches* **facultatif**. Aucun moteur, firmware ou système embarqué n'est contrôlé.

**État réel :** code et tests locaux fournis ; aucun VPS, fournisseur IA ou dépôt GitHub de l'utilisateur n'a été modifié. Les correctifs proposés par un modèle d'IA ne sont jamais considérés comme sûrs sans examen humain. Les appels IA payants sont facultatifs et désactivés par défaut.

## Capacités

### V1/V2 conservées

- Import JPEG, PNG ou WEBP, prétraitement et suppression des métadonnées EXIF.
- Mémoire SQLite/PostgreSQL persistante : observations, objets confirmés, exemples, faits et événements.
- Reconnaissance locale de photos identiques ou très proches ; comparaison de vues différentes facultative via API d'IA visuelle, avec confirmation humaine.
- Recherche Wikipedia FR plafonnée et connaissances issues du Web en attente de validation.
- Tableau de bord sécurisé Basic Auth (usage privé), export JSON et interface de synchronisation des connaissances **confirmées seulement** pour le futur robot.
- Docker, HTTPS via Caddy, simulateur sans robot, tests sans Internet.

### Nouvelles fonctions V3

1. **Diagnostic automatique et mesurable** (`POST /api/evolution/diagnose` ou tâche quotidienne) : analyse des corrections humaines, inconnus, erreurs d'analyse et files de validation.
2. **Propositions vérifiables** : règle, priorité, métriques constatées, périmètre autorisé et critères d'acceptation. Pas de pseudo-mesure d'intelligence.
3. **Aucune duplication active** : le même défaut ne génère pas plusieurs demandes ouvertes ; diagnostic plafonné à une fois par jour UTC.
4. **Approbation administrateur** : « autoriser l'étude » ou « rejeter » ; cela n'autorise jamais une fusion, une installation ou un déploiement.
5. **Brief téléchargeable** pour Claude Code, Codex ou tout autre agent de programmation, contenant des exigences de tests, de sécurité et de retour arrière.
6. **Brouillon de modification optionnel**, créé avec une API IA seulement sur une machine de développement, après opt-in explicite et validation du périmètre. Sortie : `proposal.patch`, `candidate.py.txt`, `review.md`, `manifest.json`. **Jamais appliqué automatiquement.**
7. **Validation en CI** : GitHub Actions sans secrets ; option de tests de candidat dans un conteneur Docker privé du réseau, à lancer manuellement après lecture du diff.
8. **Interface V3** : panneau Self-Evolution avec métriques, exécution du diagnostic, liste de demandes et approbation/rejet.

### Ce qui n'est PAS automatisé

- Aucun agent IA ne modifie directement le code déployé ; le serveur de production n'exécute **jamais** les correctifs produits.
- Aucune branche GitHub ni pull request n'est créée en arrière-plan. Le `brief` et le patch peuvent être transmis à un développeur ou à Claude Code **après ton accord**.
- Aucun réentraînement autonome de modèle neuronal. Le système diagnostique et propose, mais ses résultats ne garantissent pas une amélioration.
- Pas de contrôle des moteurs, mouvement, Arduino UNO Q, recharge ou mise à jour de firmware.

## Installation sur un PC : démo locale sans VPS

**Python 3.12 recommandé.** Dans le dossier extrait :

```bash
python -m pip install -r requirements.txt
python tools/init_local.py
python tools/start_local.py
```

Ouvrir **http://127.0.0.1:8000**. `init_local.py` génère les secrets dans `.env`, sans écraser un fichier existant. La première connexion utilise l'identifiant `admin` et le mot de passe affiché par le script. L'API demeure liée à `127.0.0.1` en mode local.

**Premier parcours V3, sans service payant :**

1. Envoyer et confirmer plusieurs photos via le tableau de bord V2.
2. Laisser trois observations inconnues, puis cliquer **Lancer un diagnostic** dans Self-Evolution.
3. Consulter l'amélioration proposée, ses métriques, sa priorité et ses conditions d'acceptation.
4. Cliquer **Autoriser l'étude** ou **Rejeter** ; télécharger le brief Markdown.
5. Arrêter puis relancer le serveur et vérifier que les propositions et leur statut persistent.

Un diagnostic n'invente pas une erreur s'il n'en trouve pas. La règle « erreurs d'identification récurrentes » est déclenchée après au moins deux noms proposés puis corrigés humainement au cours des 30 derniers jours.

## Installation VPS Linux avec Docker + PostgreSQL

Prévoir Docker Engine et `docker compose` (par exemple VPS de 2 vCPU, 4 Go et 40 Go SSD), avec HTTPS pour accès externe.

```bash
unzip xgoduck_life_ai_v3.zip
cd xgoduck_life_ai_v3
cp .env.example .env
# Remplacer ADMIN_PASSWORD, ROBOT_API_KEY et DB_PASSWORD par TROIS secrets aléatoires indépendants.
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
nano .env
chmod 600 .env
docker compose up -d --build
curl http://127.0.0.1:8000/health
```

En mode privé, l'API n'écoute qu'en local sur le VPS. Pour y accéder depuis un ordinateur, établir un tunnel SSH : `ssh -L 8000:127.0.0.1:8000 utilisateur@adresse-vps` puis ouvrir `http://127.0.0.1:8000` sur cet ordinateur.

Avec un domaine DNS `LIFEAI_DOMAIN` et les ports 80/443 correctement configurés :

```bash
docker compose -f compose.yml -f compose.prod.yml up -d --build
```

Caddy assure HTTPS. Ne jamais exposer PostgreSQL ni le port HTTP de l'application directement. Pour une véritable production publique, ajouter protection anti-bruteforce, gestion des sessions, sauvegardes supervisées et audit de sécurité.

### Diagnostic quotidien facultatif

Le VPS peut déclencher **uniquement les diagnostics**, sans toucher au code. Exemple de cron à installer **manuellement** après validation :

```cron
30 2 * * * cd /opt/xgoduck_life_ai_v3 && docker compose exec -T app python -m lifeai.run_diagnosis >> /var/log/lifeai-diagnostic.log 2>&1
```

La limite d'un diagnostic par jour UTC reste active. Pas de boucle d'auto-modification.

## Générer un candidat de correctif avec l'IA (facultatif)

**Sur un ordinateur de développement indépendant du VPS**, après validation d'une demande `approved_for_development` via le tableau de bord :

1. Récupérer une copie **sans données privées** du dépôt sur cette machine. Préserver `.env`, les images et les bases uniquement sur le VPS.
2. Installer les dépendances et renseigner `DATABASE_URL` vers une **copie de la base d'essai** contenant la demande approuvée (ou utiliser un export/import contrôlé).
3. Définir la clé `DEV_OPENAI_API_KEY` de façon sûre et ne **pas** la mettre dans Git. L'API est payante selon le fournisseur.
4. Lancer :

```bash
python -m tools.create_candidate \
  --proposal-id IDENTIFIANT_APPROUVE \
  --source lifeai/multiview.py \
  --output-dir /chemin/hors/projet/mes-candidats \
  --consent-share-code
```

Le développeur IA reçoit **uniquement** le contenu du module explicitement choisi et le brief du diagnostic, pas le fichier `.env`, les images, la base de production, les logs bruts ou le firmware. Les chemins autorisés sont `lifeai/vision.py` et `lifeai/multiview.py`, et doivent aussi figurer dans le périmètre de la proposition approuvée.

Le résultat est un fichier patch et un module candidat **non exécutés**. Le contrôle AST ne vérifie que la syntaxe ; il ne garantit pas la sécurité, la pertinence ni l'absence de régression.

### Tester un candidat isolément (après revue humaine du diff)

Sur une **machine de développement**, avec Docker installé :

```bash
docker build -f Dockerfile.tests -t xgoduck-lifeai-tests:local .
python -m tools.verify_candidate --candidate-dir /chemin/hors/projet/mes-candidats/IDENTIFIANT_APPROUVE --reviewed-diff
```

Le candidat est copié dans un dossier temporaire, puis les tests sont exécutés dans un conteneur Docker sans accès réseau, avec système de fichiers en lecture seule, privilèges réduits et limites de CPU/mémoire. Cela réduit les risques mais **n'est pas une garantie absolue** contre du code hostile. Ne jamais tester du code non fiable sur le VPS ou à proximité de secrets sensibles.

Une *pull request* GitHub peut ensuite être ouverte **manuellement**, après approbation du diff, pour lancer la CI de `.github/workflows/ci.yml`. La fusion et le déploiement restent manuels et hors du périmètre de Life AI.

## Mise à niveau depuis la V2

1. Arrêter la V2. Sauvegarder **ensemble** la base de données et les fichiers images, puis vérifier la sauvegarde.
2. Conserver les anciens secrets `.env`, les volumes Docker et le chemin du dossier de données. En Docker, éviter de renommer le projet Compose, car un nouveau nom peut créer de nouveaux volumes vides. En local, conserver la même adresse SQLite et le même `DATA_DIR`.
3. Mettre à jour **les fichiers de code seulement**. `Base.metadata.create_all()` ajoute automatiquement les **deux nouvelles tables** `diagnosis_runs` et `improvement_proposals` ; les tables V2 existantes ne sont pas modifiées.
4. Redémarrer, vérifier `/health`, la mémoire précédente, puis la nouvelle section Self-Evolution.
5. Garder la sauvegarde V2 jusqu'à validation. Pour des évolutions futures du schéma, utiliser Alembic plutôt que des créations automatiques de tables.

**Restauration :** arrêter V3 et restaurer la copie sauvegardée de la base ainsi que les images avant de relancer V2. Les propositions V3 disparaîtront si tu restaures la base V2, mais les connaissances anciennes seront conservées jusqu'à la date de la sauvegarde.

## Endpoints V3

| Méthode | Route | Autorisation | Fonction |
|---|---|---|---|
| `GET` | `/health` | public | Service et désactivation moteurs |
| `GET` | `/api/evolution` | admin | Métriques, diagnostics et améliorations |
| `POST` | `/api/evolution/diagnose` | admin | Diagnostic borné (1/jour UTC) |
| `POST` | `/api/evolution/proposals/{id}/review` | admin | `{"approve":true/false}` ; pas de déploiement |
| `GET` | `/api/evolution/proposals/{id}/brief` | admin | Export Markdown pour un agent développeur |
| `GET` | `/api/learning/report` | admin ou robot | Progression de la mémoire V2 |
| `GET` | `/api/robot/knowledge` | admin ou robot | Connaissances vérifiées uniquement |
| `POST` | `/api/observations` | admin ou robot | Nouvelle image |

Le jeton `X-Robot-Key` ne peut pas consulter ni autoriser les propositions de code. Aucune route de pilotage moteur ni exécution de commande système n'est ajoutée.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Tous les appels IA et réseau sont simulés dans les tests. Les tests de V3 vérifient la persistance, l'accès administrateur, le refus des clés robot, l'idempotence, l'apprentissage corrigé, la génération contrôlée de brouillons et l'absence de modification des fichiers d'origine.

## Sécurité et limites

- **Pas d'auto-déploiement**. Une proposition « approuvée » ne donne droit qu'à sa préparation dans une copie isolée.
- Les suggestions basées sur des statistiques ne prouvent pas qu'une correction améliorera réellement les performances.
- Les contenus externes (sites, images, notes d'utilisateur, résultats IA) sont des **données non fiables** ; ils ne doivent pas dicter des commandes système.
- Par défaut, aucun appel à un fournisseur IA ni transfert automatique de photos. L'option multivue de V2 peut transmettre des exemples visuels si explicitement activée.
- L'API Basic Auth et SQLite conviennent aux essais locaux ou à une exposition privée soigneusement contrôlée. Pour un service public, renforcer l'authentification, les limites de requêtes et la supervision.
- La recherche Wikipedia et la génération de brouillons utilisent des fournisseurs réseau uniquement lorsqu'elles sont déclenchées et autorisées ; surveiller les frais et la confidentialité.
- Les fichiers d'images et la base ne sont pas inclus dans l'export JSON : organiser des sauvegardes cohérentes séparées.

## Organisation du projet

```text
lifeai/                  Application FastAPI, mémoire, vision, diagnostic V3
lifeai/static/           Tableau de bord, y compris Self-Evolution
tools/                   Démarrage, simulateur, diagnostic, brouillon et contrôle isolé
tests/                   Régressions V1, V2 et V3
.github/workflows/       CI sans secrets, non déployante
deploy/                  HTTPS Caddy et extension PostgreSQL
compose.yml              API / PostgreSQL local VPS
compose.prod.yml         Proxy HTTPS optionnel
Dockerfile.tests         Image de tests isolée, hors production
```

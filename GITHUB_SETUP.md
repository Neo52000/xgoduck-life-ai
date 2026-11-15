# GitHub — XGO-Duck Life AI V3.3

Dépôt : <https://github.com/Neo52000/xgoduck-life-ai>

## État

- Le propriétaire a demandé explicitement une publication **publique** du code.
- Aucun secret, photographie, souvenir privé ou fichier `.env` ne doit être ajouté au dépôt.
- La branche `main` comporte la V3.3 ; la CI GitHub Actions exécute les tests sans secrets réels.
- Le code GitHub ne déploie pas automatiquement le VPS ni ne met à jour le robot.

## Cloner et tester

```bash
git clone https://github.com/Neo52000/xgoduck-life-ai.git
cd xgoduck-life-ai
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Publier une amélioration

Créer une branche Git, soumettre une pull request et attendre la revue humaine avant de fusionner. Ne pas exposer la base de données ou les photos utilisées dans Life AI. Les correctifs proposés par le module Self-Evolution doivent être vérifiés en environnement isolé.

## Confidentialité

Le dépôt est public : **ne jamais y placer de clés API ou de données privées**. Vérifier les termes des dépendances et l'attribution des éventuels modules externes avant redistribution.

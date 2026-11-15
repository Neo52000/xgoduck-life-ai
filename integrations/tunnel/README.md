# XGO-Duck Life AI — passerelle MCP + tunnel OpenAI

Module expérimental **lecture seule**, sans SSH, commande shell, mémoire privée, déploiement de code ni moteurs. Deux outils uniquement : `lifeai_health` et `lifeai_gateway_scope`. Déploiement indépendant de `compose.yml` (production).

**État : code publié, installation sur le VPS NON exécutée.** Ce module ne peut être connecté à ChatGPT que lorsque ton compte/organisation dispose d'un tunnel OpenAI autorisé et des permissions ChatGPT MCP appropriées.

Sources officielles :
- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- https://github.com/openai/tunnel-client/blob/master/docs/onboarding.md
- https://github.com/openai/tunnel-client/blob/master/docs/deployment/docker.md

## Préconditions sur Ubuntu 24.04

1. Life AI fonctionne déjà localement : `curl -fsS http://127.0.0.1:8000/health`.
2. Docker et Docker Compose sont disponibles.
3. Ports **18765** (passerelle) et **18766** (santé tunnel) libres. Ils ne seront **jamais exposés** sur Internet.
4. HTTPS sortant vers `api.openai.com:443`.
5. Accès à https://platform.openai.com/settings/organization/tunnels pour créer un tunnel et une clé runtime avec droits `Tunnels Read + Use`. L'activation de ChatGPT Sites est restreinte à certains espaces Enterprise ; un tunnel Platform ne garantit pas la disponibilité dans ChatGPT.

## 1 — Récupérer le projet sur le VPS avec un vrai terminal SSH

```bash
if [ -d /opt/xgoduck-life-ai/.git ]; then
  sudo git -C /opt/xgoduck-life-ai pull --ff-only
else
  sudo git clone https://github.com/Neo52000/xgoduck-life-ai.git /opt/xgoduck-life-ai
fi
```

Cette opération n'installe ni ne redémarre Life AI.

## 2 — Démarrer uniquement la passerelle MCP (sans clé OpenAI)

Vérifier qu'aucun processus n'utilise 18765 et 18766 : `sudo ss -lntp | grep -E ':(18765|18766) '`.

```bash
cd /opt/xgoduck-life-ai
sudo docker compose -f integrations/tunnel/compose.gateway.yml up -d --build
sudo docker compose -f integrations/tunnel/compose.gateway.yml ps
sudo docker compose -f integrations/tunnel/compose.gateway.yml logs --tail=40
```

La passerelle s'écoute uniquement sur `127.0.0.1:18765/mcp`. Elle interroge uniquement `http://127.0.0.1:8000/health`. Pas de socket Docker monté, pas de secrets Life AI lus.

## 3 — Fournir les autorisations OpenAI (UNIQUEMENT si disponibles)

Création d'un tunnel : https://platform.openai.com/settings/organization/tunnels

Création d'une clé runtime : https://platform.openai.com/settings/organization/api-keys

**Ne jamais transmettre la clé dans ChatGPT, GitHub, un prompt Hostinger ou une capture d'écran.**

Dans le **terminal du VPS** :

```bash
sudo install -d -m 700 /etc/xgoduck-tunnel
read -r -s -p "OpenAI tunnel runtime key: " RUNTIME_KEY; echo
printf '%s' "$RUNTIME_KEY" | sudo tee /etc/xgoduck-tunnel/runtime.key >/dev/null
unset RUNTIME_KEY
sudo chmod 600 /etc/xgoduck-tunnel/runtime.key

read -r -p "OpenAI Tunnel ID (tunnel_...): " TUNNEL_ID
case "$TUNNEL_ID" in tunnel_*) ;; *) echo "ID invalide"; exit 1;; esac
printf 'CONTROL_PLANE_TUNNEL_ID=%s\n' "$TUNNEL_ID" | sudo tee /etc/xgoduck-tunnel/tunnel.env >/dev/null
unset TUNNEL_ID
sudo chmod 600 /etc/xgoduck-tunnel/tunnel.env
```

## 4 — Démarrer et vérifier le client officiel OpenAI

```bash
cd /opt/xgoduck-life-ai
sudo docker compose --env-file /etc/xgoduck-tunnel/tunnel.env -f integrations/tunnel/compose.tunnel.yml up -d
sudo docker compose --env-file /etc/xgoduck-tunnel/tunnel.env -f integrations/tunnel/compose.tunnel.yml ps
curl -fsS http://127.0.0.1:18766/readyz
```

Le conteneur officiel `ghcr.io/openai/tunnel-client:v0.0.21` communique vers OpenAI en HTTPS sortant, sans ouvrir de port d'administration. La clé est montée en secret Docker via un fichier local et ne figure pas dans Git.

En cas de problème, consulter les logs **après avoir masqué toute information sensible** :

```bash
sudo docker compose --env-file /etc/xgoduck-tunnel/tunnel.env -f integrations/tunnel/compose.tunnel.yml logs --tail=40
```

## 5 — Rattacher ChatGPT

Dans ChatGPT : Paramètres > Plugins > Ajouter un serveur MCP personnalisé > connexion **Tunnel** (si disponible), sélectionner le tunnel de la même organisation, tester d'abord `lifeai_gateway_scope`, puis `lifeai_health`.

**La connexion n'est considérée opérationnelle qu'après un appel MCP réussi dans ChatGPT.**

## Arrêt sans effet sur la mémoire ou les autres projets

```bash
cd /opt/xgoduck-life-ai
sudo docker compose --env-file /etc/xgoduck-tunnel/tunnel.env -f integrations/tunnel/compose.tunnel.yml down
sudo docker compose -f integrations/tunnel/compose.gateway.yml down
```

L'arrêt ne touche ni aux volumes PostgreSQL ni au `compose.yml` principal.

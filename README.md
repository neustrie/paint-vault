# Paint Vault

Inventaire de peintures pour figurines et fiches projets. FastAPI + SQLite, sans authentification (usage LAN/ZeroTier).

## Déploiement (spirou)

    cd /opt/docker-compose/peinture
    git clone https://github.com/neustrie/paint-vault .   # ou git pull
    sudo chown -R 1000:1000 data                          # le conteneur tourne en uid 1000
    docker compose up -d --build

Interface : http://192.168.1.30:8090

## Données

Tout est dans `./data` (couvert par la sauvegarde restic de `/opt/docker-compose`) :
`paintvault.db` (SQLite, mode WAL), `photos/`, `exports/inventaire.csv` (réécrit chaque jour).
Au premier démarrage, la base est remplie depuis `app/seed.json` (inventaire du .docx et du .xlsx).

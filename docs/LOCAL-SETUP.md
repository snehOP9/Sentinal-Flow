# Local setup reference

Use the repository name when cloning and entering the project directory:

```bash
git clone https://github.com/snehOP9/Sentinal-Flow.git
cd Sentinal-Flow
cp .env.example .env
docker compose up --build
```

The application uses the repository's `frontend` and backend layout; the old `fraud-detection-system` directory name should not be used as the local working directory unless you deliberately renamed the clone.

For Python-only development, follow the commands in the root README and keep production authentication disabled only in the explicitly documented synthetic demo configuration.

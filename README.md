# CloudVault

A secure file-sharing API that hands out **time-limited download links** and cleans up after itself — built with Flask and deployed on AWS (S3, RDS, Lambda, EC2), containerized, and shipped through a self-hosted CI/CD pipeline.

## What it does

CloudVault lets a client upload a file over HTTP; the file is stored in S3, its metadata (name, upload time, expiry) is recorded in a Postgres database, and any later request for it gets back a presigned S3 URL that expires in an hour. A scheduled AWS Lambda separately sweeps the bucket and permanently deletes anything older than 24 hours, so nothing lives longer than intended without extra ops work.

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full system design, data flow, and the reasoning behind the AWS setup.

## Features

- **Presigned download links** — files are never served directly or made public; every download URL is generated on demand and expires after 1 hour.
- **Automatic expiry** — a scheduled Lambda deletes files older than 24 hours, independent of the API.
- **Upload metadata tracking** — every upload is logged to PostgreSQL (RDS) with its upload and expiry timestamps.
- **Containerized** — runs identically locally and in production via Docker.
- **CI/CD pipeline** — GitHub Actions runs the test suite, builds the Docker image, and deploys to EC2 on every push to `main`.
- **Observability** — structured logging, CloudWatch alarms, and CloudTrail audit logging on the AWS side.

## Tech stack

| Layer | Choice |
|---|---|
| API | Python, Flask |
| Storage | AWS S3 |
| Database | PostgreSQL (AWS RDS) |
| Scheduled jobs | AWS Lambda |
| Compute | AWS EC2 (VPC, 2 public + 2 private subnets) |
| Packaging | Docker |
| CI/CD | GitHub Actions (self-hosted runner) |
| Testing | pytest |

## API

| Method | Route | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/upload` | Accepts a file (`multipart/form-data`), stores it in S3, logs metadata to RDS |
| `GET` | `/download/<filename>` | Returns a presigned S3 URL for the file, valid for 1 hour |

## Getting started

```bash
git clone https://github.com/SurepallyBhavani/cloudvault-app.git
cd cloudvault-app
python -m venv venv
venv\Scripts\activate        # or `source venv/bin/activate` on macOS/Linux
pip install -r requirements.txt -r requirements-dev.txt
```

Create a `.env` file (never committed — see `.gitignore`) with:

```
AWS_REGION=<your-region>
S3_BUCKET_NAME=<your-bucket-name>
DB_HOST=<your-db-host>
DB_PORT=5432
DB_NAME=<your-db-name>
DB_USER=<your-db-user>
DB_PASSWORD=<your-db-password>
```

Then:

```bash
python init_db.py     # creates the file_uploads table
python app.py          # starts the API on http://localhost:5000
```

### Run with Docker instead

```bash
docker build -t cloudvault-app .
docker run --env-file .env -p 5000:5000 cloudvault-app
```

## Testing

```bash
pytest tests/ -v
```

AWS calls and the database connection are mocked in tests, so no live AWS resources are needed to run the suite.

## Project structure

```
cloudvault-app/
├── app.py                    # Flask API: upload / download / health
├── init_db.py                 # creates the file_uploads table
├── lambda/
│   └── auto_expiry.py         # scheduled Lambda: deletes files older than 24h
├── tests/
│   └── test_app.py
├── docs/
│   ├── ARCHITECTURE.md
│   └── vpc-ec2-setup.md
├── Dockerfile
└── .github/workflows/ci.yml   # test -> docker build -> deploy
```

## Deployment

Every push to `main` runs the test suite, builds the Docker image, and — if both pass — deploys straight to the EC2 instance via a self-hosted GitHub Actions runner (`git pull`, reinstall dependencies, restart the Flask process).

## Security notes

- No secret ever lives in the repo — credentials are read from environment variables (`.env` locally, Lambda/EC2 environment config in AWS) and `.env`/`*.pem` are gitignored.
- Files are never public; every download goes through a short-lived presigned URL.
- CloudTrail is enabled on the AWS account for auditing API activity.

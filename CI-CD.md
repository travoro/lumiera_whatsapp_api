# CI/CD Pipeline Documentation

This document describes the complete CI/CD setup for automated testing, code quality checks, and deployment.

## Table of Contents

- [Overview](#overview)
- [GitHub Actions Workflows](#github-actions-workflows)
- [Setup Instructions](#setup-instructions)
- [Deployment Options](#deployment-options)
- [Docker Deployment](#docker-deployment)
- [Secrets Configuration](#secrets-configuration)
- [Badge Setup](#badge-setup)

## Overview

The CI/CD pipeline automatically:
- ✅ Runs tests on every push and pull request
- 🔍 Performs security scans
- 📊 Checks code quality and generates reports
- 🚀 Deploys to production on main branch pushes
- 📦 Updates dependencies weekly
- 🐳 Builds and pushes Docker images

## GitHub Actions Workflows

### 1. CI Workflow (`.github/workflows/ci.yml`)

**Triggers:** Push to main/develop, Pull Requests

**What it does:**
- Sets up Python 3.12 environment
- Starts PostgreSQL and Redis services
- Installs dependencies
- Runs linting (flake8, black, isort)
- Runs type checking (mypy)
- Executes all tests with coverage
- Uploads coverage reports to Codecov
- Performs security scans (safety, bandit)
- Generates coverage reports as artifacts

**How to view results:**
- Check the "Actions" tab in GitHub
- Coverage report: Download artifact or check Codecov
- Security reports: Download from workflow artifacts

### 2. CD Workflow (`.github/workflows/cd.yml`)

**Triggers:** Push to main branch, Manual trigger

**Deployment Methods:**

#### Option A: SSH Deployment (Default)
Deploys to your server via SSH:
```bash
# On the server:
git pull → pip install → run tests → restart service
```

#### Option B: Docker Deployment
Builds and pushes Docker image to Docker Hub:
```bash
docker build → docker push → deploy container
```

#### Option C: Cloud Platform
Deploy to cloud platforms (customize for your needs):
- Google Cloud Run
- AWS ECS/Fargate
- Azure App Service
- Railway
- Heroku

**Choose deployment method:**
Set the `DEPLOYMENT_METHOD` variable in GitHub:
- `ssh` (default) - Deploy via SSH
- `docker` - Build and push Docker image
- `cloud` - Cloud platform deployment

### 3. Code Quality Workflow (`.github/workflows/code-quality.yml`)

**Triggers:** Pull Requests

**What it does:**
- Black formatting check
- isort import sorting check
- Flake8 linting with statistics
- Pylint code analysis
- Cyclomatic complexity calculation
- Maintainability index
- TODO/FIXME comment detection
- Lines of code count

**Results:** Check the PR summary and workflow output

### 4. Dependency Update Workflow (`.github/workflows/dependency-update.yml`)

**Triggers:** Weekly (Mondays at 9 AM UTC), Manual trigger

**What it does:**
- Checks for outdated packages
- Creates GitHub issues for updates
- Auto-approves Dependabot patch updates
- Auto-merges safe dependency updates

### 5. Dependabot (`.github/dependabot.yml`)

**What it does:**
- Weekly checks for dependency updates
- Creates PRs for:
  - Python packages (pip)
  - GitHub Actions versions
  - Docker base images
- Groups related updates together
- Auto-assigns reviewers

## Setup Instructions

### 1. Enable GitHub Actions

1. Go to your repository on GitHub
2. Click "Actions" tab
3. Enable workflows if not already enabled

### 2. Configure Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**

Add the required secrets based on your deployment method.

### 3. Test the Workflows

**Test CI:**
```bash
# Create a test branch
git checkout -b test-ci

# Make a small change
echo "# Test" >> README.md

# Commit and push
git add .
git commit -m "test: CI workflow"
git push origin test-ci

# Create a PR and watch the workflows run
```

**Test CD (manual trigger):**
1. Go to Actions → CD - Deploy
2. Click "Run workflow"
3. Select branch and run

### 4. Set Deployment Method

Go to **Settings → Secrets and variables → Actions → Variables → New repository variable**

Add:
- **Name:** `DEPLOYMENT_METHOD`
- **Value:** `ssh` or `docker` or `cloud`

## Deployment Options

### Option 1: SSH Deployment

**Best for:** Deploying to your own server

**Required Secrets:**
```yaml
DEPLOY_HOST: your-server.com
DEPLOY_USER: ceeai
DEPLOY_SSH_KEY: |
  -----BEGIN OPENSSH PRIVATE KEY-----
  your-private-key-here
  -----END OPENSSH PRIVATE KEY-----
DEPLOY_PORT: 22  # Optional, defaults to 22
DEPLOY_PATH: /home/ceeai/whatsapp_api  # Optional
```

**Setup:**
1. Generate SSH key on your local machine:
   ```bash
   ssh-keygen -t ed25519 -C "github-actions"
   cat ~/.ssh/id_ed25519  # Copy this as DEPLOY_SSH_KEY
   ```

2. Add public key to server:
   ```bash
   ssh ceeai@your-server.com
   echo "your-public-key" >> ~/.ssh/authorized_keys
   ```

3. Ensure the systemd service exists on the server:
   ```bash
   sudo systemctl status lumiera-whatsapp.service
   ```

**Customize deployment script:**
Edit `.github/workflows/cd.yml` under "Deploy to Server via SSH"

### Option 2: Docker Deployment

**Best for:** Container-based deployments

**Required Secrets:**
```yaml
DOCKER_USERNAME: your-dockerhub-username
DOCKER_PASSWORD: your-dockerhub-password-or-token
```

**Setup:**
1. Create Docker Hub account at https://hub.docker.com
2. Create access token: Account Settings → Security → New Access Token
3. Add secrets to GitHub

**Deploy the image:**
```bash
# On your server:
docker pull your-username/whatsapp-api:latest
docker-compose up -d
```

**Test locally:**
```bash
# Build
docker build -t whatsapp-api .

# Run with docker-compose
docker-compose up -d

# Check logs
docker-compose logs -f app

# Stop
docker-compose down
```

### Option 3: Cloud Platform Deployment

**Customize for your platform:**

Edit `.github/workflows/cd.yml` under "Deploy to Cloud Platform"

**Google Cloud Run:**
```bash
gcloud run deploy whatsapp-api \
  --image gcr.io/PROJECT_ID/whatsapp-api:latest \
  --platform managed \
  --region us-central1
```

**AWS ECS:**
```bash
aws ecs update-service \
  --cluster your-cluster \
  --service whatsapp-api \
  --force-new-deployment
```

**Railway:**
```bash
railway up
```

## Docker Deployment

### Build and Run Locally

```bash
# Build the image
docker build -t whatsapp-api .

# Run standalone
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  --name whatsapp-api \
  whatsapp-api

# Or use docker-compose
docker-compose up -d

# View logs
docker logs -f whatsapp-api
# OR
docker-compose logs -f app

# Stop
docker stop whatsapp-api
# OR
docker-compose down
```

### Production Deployment with Docker

```bash
# Pull latest image
docker pull your-username/whatsapp-api:latest

# Start with docker-compose
docker-compose up -d

# Update
docker-compose pull
docker-compose up -d

# Rollback
docker-compose down
docker pull your-username/whatsapp-api:previous-sha
docker-compose up -d
```

### Environment Variables

Create `.env` file (don't commit this!):
```env
# Copy from .env.example and fill in values
ENVIRONMENT=production
DEBUG=false
DATABASE_URL=postgresql://user:pass@postgres:5432/db
REDIS_URL=redis://redis:6379/0
# ... add all required variables
```

## Secrets Configuration

### GitHub Secrets Reference

| Secret Name | Required For | Description | Example |
|------------|--------------|-------------|---------|
| `DEPLOY_HOST` | SSH | Server hostname | `whatsapp.example.com` |
| `DEPLOY_USER` | SSH | SSH username | `ceeai` |
| `DEPLOY_SSH_KEY` | SSH | Private SSH key | `-----BEGIN OPENSSH...` |
| `DEPLOY_PORT` | SSH (optional) | SSH port | `22` |
| `DEPLOY_PATH` | SSH (optional) | App directory | `/home/ceeai/whatsapp_api` |
| `DOCKER_USERNAME` | Docker | Docker Hub username | `myusername` |
| `DOCKER_PASSWORD` | Docker | Docker Hub token | `dckr_pat_...` |
| `SLACK_WEBHOOK_URL` | Notifications (optional) | Slack webhook | `https://hooks.slack.com/...` |

### Add Secrets via GitHub CLI

```bash
# SSH deployment
gh secret set DEPLOY_HOST -b"your-server.com"
gh secret set DEPLOY_USER -b"ceeai"
gh secret set DEPLOY_SSH_KEY < ~/.ssh/id_ed25519

# Docker deployment
gh secret set DOCKER_USERNAME -b"your-username"
gh secret set DOCKER_PASSWORD -b"your-token"
```

## Badge Setup

Add status badges to your README.md:

```markdown
![CI](https://github.com/travoro/lumiera_whatsapp_api/workflows/CI/badge.svg)
![CD](https://github.com/travoro/lumiera_whatsapp_api/workflows/CD%20-%20Deploy/badge.svg)
[![codecov](https://codecov.io/gh/travoro/lumiera_whatsapp_api/branch/main/graph/badge.svg)](https://codecov.io/gh/travoro/lumiera_whatsapp_api)
```

## Monitoring Deployments

### Check Deployment Status

```bash
# Via GitHub CLI
gh run list --workflow=cd.yml

# View specific run
gh run view RUN_ID

# Watch logs
gh run watch
```

### Server Health Check

```bash
# Check if service is running
sudo systemctl status lumiera-whatsapp.service

# View logs
sudo journalctl -u lumiera-whatsapp.service -f

# Restart manually if needed
sudo systemctl restart lumiera-whatsapp.service
```

### Docker Health Check

```bash
# Check container health
docker ps
docker inspect whatsapp-api | grep -A 10 Health

# Via docker-compose
docker-compose ps
```

## Troubleshooting

### CI Tests Failing

1. Check workflow logs in GitHub Actions
2. Run tests locally:
   ```bash
   ./run_tests.sh
   ```
3. Check if `.env.test` is properly configured
4. Ensure database/redis are running

### Deployment Failing

**SSH Deployment:**
- Verify SSH key has correct permissions
- Test SSH connection manually: `ssh -i key user@host`
- Check server logs: `sudo journalctl -u lumiera-whatsapp.service`
- Ensure git repository is accessible on server

**Docker Deployment:**
- Check Docker Hub credentials
- Verify image was pushed: `docker pull your-username/whatsapp-api:latest`
- Check container logs: `docker logs whatsapp-api`
- Verify environment variables are set

### Coverage Not Uploading

1. Sign up at https://codecov.io
2. Add repository to Codecov
3. Add `CODECOV_TOKEN` secret to GitHub
4. Re-run workflow

### Dependabot PRs Not Auto-Merging

1. Ensure Dependabot has access to repository
2. Check that tests pass on Dependabot PRs
3. Verify GitHub Actions has write permissions

## Best Practices

1. **Branch Protection:**
   - Require PR reviews before merging to main
   - Require status checks to pass (CI workflow)
   - Enable "Require branches to be up to date"

2. **Testing:**
   - Write tests for new features
   - Maintain >80% code coverage
   - Run tests locally before pushing

3. **Security:**
   - Never commit secrets or `.env` files
   - Rotate credentials regularly
   - Review Dependabot security updates promptly

4. **Deployment:**
   - Test in staging environment first
   - Monitor logs after deployment
   - Keep rollback plan ready

5. **Documentation:**
   - Document configuration changes
   - Update CI-CD.md when modifying workflows
   - Add deployment notes to PR descriptions

## Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Documentation](https://docs.docker.com/)
- [pytest Documentation](https://docs.pytest.org/)
- [Codecov Documentation](https://docs.codecov.com/)

## Support

For issues with CI/CD setup:
1. Check workflow logs in GitHub Actions
2. Review this documentation
3. Check GitHub Actions status page
4. Open an issue in the repository

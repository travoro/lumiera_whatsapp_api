# GitHub Actions Workflows

This directory contains automated CI/CD workflows for the WhatsApp API project.

## Workflows Overview

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| **CI** | `ci.yml` | Push, PR | Run tests, linting, security scans |
| **CD** | `cd.yml` | Push to main | Deploy to production |
| **Code Quality** | `code-quality.yml` | Pull Request | Check code quality metrics |
| **Dependency Updates** | `dependency-update.yml` | Weekly, Manual | Check for outdated packages |

## Quick Status

| Workflow | Status |
|----------|--------|
| CI | ![CI](https://github.com/travoro/lumiera_whatsapp_api/workflows/CI/badge.svg) |
| CD | ![CD](https://github.com/travoro/lumiera_whatsapp_api/workflows/CD%20-%20Deploy/badge.svg) |
| Code Quality | ![Code Quality](https://github.com/travoro/lumiera_whatsapp_api/workflows/Code%20Quality/badge.svg) |

## Setup Required

Before workflows can run successfully, configure the following:

### 1. Secrets (Settings → Secrets → Actions)

**For SSH Deployment:**
- `DEPLOY_HOST` - Your server hostname
- `DEPLOY_USER` - SSH username
- `DEPLOY_SSH_KEY` - Private SSH key
- `DEPLOY_PORT` (optional) - SSH port (default: 22)
- `DEPLOY_PATH` (optional) - App path on server

**For Docker Deployment:**
- `DOCKER_USERNAME` - Docker Hub username
- `DOCKER_PASSWORD` - Docker Hub token

**Optional:**
- `SLACK_WEBHOOK_URL` - For deployment notifications
- `CODECOV_TOKEN` - For coverage reports (get from codecov.io)

### 2. Variables (Settings → Secrets → Variables)

- `DEPLOYMENT_METHOD` - Choose: `ssh`, `docker`, or `cloud`

### 3. Enable Workflows

1. Go to "Actions" tab
2. Enable workflows if prompted
3. Workflows will run automatically on next push

## Manual Triggers

Some workflows can be triggered manually:

```bash
# Using GitHub CLI
gh workflow run cd.yml
gh workflow run dependency-update.yml

# Or via GitHub UI: Actions → Select workflow → Run workflow
```

## Viewing Results

- **Workflow runs:** Actions tab → Select workflow
- **Coverage report:** Download from workflow artifacts or view on Codecov
- **Security reports:** Download from workflow artifacts
- **Code quality:** View in PR comments and workflow summary

## Troubleshooting

See [CI-CD.md](../../docs/deployment/CI-CD.md) for detailed setup instructions and troubleshooting.

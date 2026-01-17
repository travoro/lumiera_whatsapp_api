# CI/CD Setup Checklist

Quick checklist to get your CI/CD pipeline running.

## ✅ Files Created

The following files have been created for CI/CD:

### GitHub Actions Workflows
- [x] `.github/workflows/ci.yml` - Continuous Integration
- [x] `.github/workflows/cd.yml` - Continuous Deployment
- [x] `.github/workflows/code-quality.yml` - Code Quality Checks
- [x] `.github/workflows/dependency-update.yml` - Dependency Updates
- [x] `.github/dependabot.yml` - Dependabot Configuration

### Documentation
- [x] `CI-CD.md` - Complete CI/CD documentation
- [x] `.github/workflows/README.md` - Workflows overview
- [x] Status badges added to `README.md`

### Development Tools (Bonus)
- [x] `.pre-commit-config.yaml` - Pre-commit hooks
- [x] `watch_tests.sh` - Auto-run tests on changes
- [x] `setup_dev_tools.sh` - Quick setup script
- [x] Updated `run.sh` with auto-reload
- [x] Updated `requirements.txt` with dev tools

## 🚀 Quick Start

### 0. Configure Git (First Time Only)

```bash
# Check if git is configured
git config user.name
git config user.email

# If not configured, set it up:
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# Verify
git config --list | grep user
```

See [GIT-SETUP.md](../getting-started/GIT-SETUP.md) for detailed configuration.

### 1. Commit and Push CI/CD Files

```bash
git add .github/ docs/deployment/CI-CD.md
git commit -m "ci: Add CI/CD pipeline with GitHub Actions"
git push origin main
```

### 2. Enable GitHub Actions

1. Go to https://github.com/travoro/lumiera_whatsapp_api
2. Click **Actions** tab
3. Enable workflows (if prompted)
4. Workflows will start running automatically

### 3. Configure Deployment (Choose One)

#### Option A: SSH Deployment to Your Server

```bash
# Add secrets using GitHub CLI
gh secret set DEPLOY_HOST -b"whatsapp.lumiera.paris"
gh secret set DEPLOY_USER -b"ceeai"
gh secret set DEPLOY_SSH_KEY < ~/.ssh/id_ed25519

# Set deployment method
gh variable set DEPLOYMENT_METHOD -b"ssh"
```

**Or via GitHub UI:**
1. Go to: Settings → Secrets and variables → Actions
2. Add secrets:
   - `DEPLOY_HOST`: `whatsapp.lumiera.paris`
   - `DEPLOY_USER`: `ceeai`
   - `DEPLOY_SSH_KEY`: (paste your private SSH key)
3. Go to Variables tab
4. Add variable:
   - `DEPLOYMENT_METHOD`: `ssh`

### 4. Configure Dependabot

Edit `.github/dependabot.yml` and replace `travoro` with your GitHub username:

```yaml
reviewers:
  - "your-github-username"
assignees:
  - "your-github-username"
```

### 5. Optional: Setup Codecov

For code coverage reports:

1. Sign up at https://codecov.io with your GitHub account
2. Add your repository
3. Copy the token
4. Add to GitHub secrets:
   ```bash
   gh secret set CODECOV_TOKEN -b"your-codecov-token"
   ```

### 6. Optional: Setup Slack Notifications

For deployment notifications:

1. Create Slack webhook: https://api.slack.com/messaging/webhooks
2. Add to GitHub secrets:
   ```bash
   gh secret set SLACK_WEBHOOK_URL -b"https://hooks.slack.com/services/..."
   ```

## 🧪 Test the Pipeline

### Test CI Workflow

```bash
# Create a test branch
git checkout -b test-ci

# Make a small change
echo "# Testing CI" >> README.md
git add README.md
git commit -m "test: Trigger CI workflow"
git push origin test-ci

# Create a PR on GitHub
gh pr create --title "Test CI" --body "Testing CI pipeline"

# Watch the workflow run
gh run watch
```

Expected results:
- ✅ Tests pass
- ✅ Linting passes
- ✅ Code quality checks complete
- ✅ Security scan completes
- ✅ Coverage report generated

### Test CD Workflow (Manual)

```bash
# Trigger manually
gh workflow run cd.yml

# Watch it run
gh run watch

# Or go to GitHub: Actions → CD - Deploy → Run workflow
```

## 📊 Monitoring

### View Workflow Status

```bash
# List recent runs
gh run list

# View specific workflow
gh run list --workflow=ci.yml

# View run details
gh run view <run-id>

# Download artifacts
gh run download <run-id>
```

### GitHub UI

- **All workflows:** https://github.com/travoro/lumiera_whatsapp_api/actions
- **CI runs:** https://github.com/travoro/lumiera_whatsapp_api/actions/workflows/ci.yml
- **CD runs:** https://github.com/travoro/lumiera_whatsapp_api/actions/workflows/cd.yml

## 🛠️ Development Workflow

### Local Development with Auto-Reload

**Terminal 1 - Run app with auto-restart:**
```bash
./run.sh
```

**Terminal 2 - Auto-run tests on changes:**
```bash
./watch_tests.sh
```

### Pre-Commit Hooks

```bash
# Setup (one time)
./setup_dev_tools.sh

# Hooks will now run automatically on git commit
git commit -m "Your message"

# Run manually
pre-commit run --all-files
```

## 📝 What Happens Automatically

### On Every Push & Pull Request:
- ✅ Run all tests with coverage
- ✅ Check code formatting (black, isort)
- ✅ Run linters (flake8, pylint)
- ✅ Type checking (mypy)
- ✅ Security scanning (safety, bandit)
- ✅ Generate coverage reports

### On Push to Main Branch:
- ✅ All CI checks
- 🚀 Deploy to production (if secrets are configured)
- 📢 Send notifications (if configured)

### Every Monday at 9 AM UTC:
- 📦 Check for outdated dependencies
- 🐛 Create issues for updates
- 🔄 Dependabot creates PRs for updates

### On Every Commit (Local):
- ✅ Format code (black, isort)
- ✅ Lint code (flake8)
- ✅ Run all tests

## 🔧 Customization

### Modify CI Workflow

Edit `.github/workflows/ci.yml` to:
- Add/remove Python versions to test
- Change test commands
- Add additional checks
- Modify service configurations

### Modify CD Workflow

Edit `.github/workflows/cd.yml` to:
- Change deployment target
- Add deployment steps
- Modify notification settings
- Add post-deployment checks

### Modify Code Quality Checks

Edit `.github/workflows/code-quality.yml` to:
- Add/remove linters
- Change thresholds
- Add custom checks

## ❗ Troubleshooting

### CI Workflow Fails

```bash
# View error logs
gh run view --log-failed

# Run tests locally
./run_tests.sh
```

### CD Workflow Fails

**SSH Deployment:**
```bash
# Test SSH connection
ssh -i ~/.ssh/id_ed25519 ceeai@whatsapp.lumiera.paris

# Check if service exists
ssh ceeai@whatsapp.lumiera.paris "systemctl status lumiera-whatsapp.service"
```

### Workflows Not Running

1. Check GitHub Actions are enabled: Settings → Actions → General
2. Check branch protection doesn't block workflows
3. Check workflow file syntax: `gh workflow view ci.yml`
4. Check repository permissions: Settings → Actions → General → Workflow permissions

## 📚 Documentation

- **Complete CI/CD Guide:** [CI-CD.md](CI-CD.md)
- **Workflows Overview:** [.github/workflows/README.md](../../.github/workflows/README.md)
- **Development Guide:** [DEVELOPMENT.md](../getting-started/DEVELOPMENT.md)
- **GitHub Actions Docs:** https://docs.github.com/en/actions

## ✨ Next Steps

1. [ ] Commit and push CI/CD files
2. [ ] Enable GitHub Actions
3. [ ] Configure deployment secrets
4. [ ] Test CI workflow with a PR
5. [ ] Test CD workflow manually
6. [ ] Setup Codecov (optional)
7. [ ] Setup Slack notifications (optional)
8. [ ] Configure branch protection rules
9. [ ] Update Dependabot reviewers
10. [ ] Setup development tools locally

## 🎉 Done!

Once everything is set up, your workflow will be:

1. **Develop locally** with auto-reload and auto-testing
2. **Commit** (pre-commit hooks run automatically)
3. **Push** (CI runs automatically)
4. **Create PR** (code quality checks run)
5. **Merge to main** (CD deploys automatically)
6. **Monitor** via GitHub Actions and badges

Happy coding! 🚀

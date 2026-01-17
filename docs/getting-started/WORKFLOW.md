# Development Workflow Guide

This guide explains the streamlined workflow for making changes, testing, and deploying.

## 🎯 Quick Workflow

When working with Claude Code, use these simple phrases to trigger automatic actions:

### "Ship it" / "Deploy this" / "Commit and push"
Claude will automatically:
1. ✅ Run tests to verify everything works
2. 📝 Create a meaningful commit message
3. 📤 Push to GitHub
4. 🔄 Restart the app (if needed)
5. 📊 CI/CD runs automatically on GitHub

### "Run tests"
Claude will:
- Execute the test suite
- Show you the results
- Report any failures

### "Restart the app"
Claude will:
- Restart the systemd service
- Or remind you that uvicorn auto-reloads

## 🔄 Complete Workflow Example

```
You: "Add a new endpoint for getting user stats"

Claude: [makes the code changes]

You: "Ship it"

Claude: [runs tests, commits, pushes, restarts app]
```

## 🛠️ Manual Deployment

If you want to deploy manually:

```bash
# Quick deploy (all-in-one)
./deploy_local.sh "Your commit message"

# Or step by step:
git add .
git commit -m "Your message"
git push origin main
./run_tests.sh
sudo systemctl restart lumiera-whatsapp.service
```

## 🧪 Development Modes

### Mode 1: Full Auto (Recommended for Development)

**Terminal 1 - App with auto-restart:**
```bash
./run.sh
```
- App automatically restarts when you save files
- No manual restart needed

**Terminal 2 - Tests with auto-run:**
```bash
./watch_tests.sh
```
- Tests run automatically when you save files
- Instant feedback

**Your workflow:**
1. Ask Claude to make changes
2. Claude makes changes → app auto-restarts, tests auto-run
3. When ready: "Ship it" → Claude commits and pushes

### Mode 2: Manual Control

**Run app once:**
```bash
./run.sh
```

**Run tests once:**
```bash
./run_tests.sh
```

**Deploy:**
```bash
./deploy_local.sh "Your commit message"
```

### Mode 3: Production (Systemd Service)

**Start/Stop/Restart:**
```bash
sudo systemctl start lumiera-whatsapp.service
sudo systemctl stop lumiera-whatsapp.service
sudo systemctl restart lumiera-whatsapp.service
```

**Check status:**
```bash
sudo systemctl status lumiera-whatsapp.service
```

**View logs:**
```bash
sudo journalctl -u lumiera-whatsapp.service -f
```

## 📝 Commit Message Patterns

When Claude commits changes, it follows conventional commit format:

- `feat:` - New feature
- `fix:` - Bug fix
- `test:` - Adding/updating tests
- `docs:` - Documentation changes
- `chore:` - Maintenance tasks
- `refactor:` - Code refactoring
- `perf:` - Performance improvements
- `style:` - Code style changes

Examples:
```
feat: Add user statistics endpoint
fix: Resolve authentication timeout issue
test: Add tests for message handling
docs: Update API documentation
chore: Update dependencies
```

## 🎬 Common Scenarios

### Scenario 1: Quick Fix
```
You: "Fix the bug in the login validation"
Claude: [fixes the bug]
You: "Ship it"
Claude: [tests, commits "fix: Resolve login validation bug", pushes]
```

### Scenario 2: New Feature
```
You: "Add an endpoint to export task reports as CSV"
Claude: [implements feature]
You: "Run tests first"
Claude: [runs tests, shows results]
You: "Ship it"
Claude: [commits "feat: Add CSV export for task reports", pushes]
```

### Scenario 3: Multiple Changes
```
You: "Add error handling to the webhook and update the docs"
Claude: [makes changes]
You: "Ship it"
Claude: [commits all changes with descriptive message, pushes]
```

### Scenario 4: Emergency Hotfix
```
You: "Critical bug in production - fix the null pointer in message handler"
Claude: [fixes immediately]
You: "Ship it now"
Claude: [tests, commits "fix: Critical - null pointer in message handler", pushes]
```

## 🔍 Checking Deployment Status

### Local Status
```bash
# Check app status
sudo systemctl status lumiera-whatsapp.service

# View recent logs
sudo journalctl -u lumiera-whatsapp.service -n 50

# Follow logs in real-time
sudo journalctl -u lumiera-whatsapp.service -f
```

### CI/CD Status
```bash
# View recent workflow runs
gh run list

# Watch current run
gh run watch

# Or visit GitHub Actions:
# https://github.com/travoro/lumiera_whatsapp_api/actions
```

### Application Health
```bash
# Check if app is responding
curl http://localhost:8000/health

# Check from outside
curl https://whatsapp.lumiera.paris/health
```

## ⚡ Pro Tips

### 1. Use Auto-Reload During Development
Keep `./run.sh` running in one terminal - changes apply instantly without manual restart.

### 2. Watch Tests While Coding
Run `./watch_tests.sh` to get immediate feedback as you code.

### 3. Pre-Commit Hooks
Pre-commit hooks run automatically:
```bash
git commit -m "message"  # Tests run automatically
```

### 4. Skip Hooks When Needed
```bash
git commit -m "WIP: not ready" --no-verify
```

### 5. Quick Status Check
```bash
# One-liner to check everything
sudo systemctl status lumiera-whatsapp.service && curl -s http://localhost:8000/health
```

### 6. Rollback If Needed
```bash
# Revert last commit
git revert HEAD
./deploy_local.sh "Revert: rolling back last change"

# Or reset to previous commit (careful!)
git reset --hard HEAD~1
git push --force origin main  # Only if you're sure!
```

## 🤖 Claude Code Workflow

When working with Claude Code, here's what happens behind the scenes:

### When you say "Ship it":

1. **Claude runs tests**
   ```bash
   ./run_tests.sh
   ```
   - If tests fail, Claude stops and shows you the errors
   - You can fix issues before deploying

2. **Claude checks git status**
   ```bash
   git status
   ```
   - Reviews what files changed

3. **Claude creates commit**
   ```bash
   git add -A
   git commit -m "descriptive message based on changes"
   ```
   - Uses conventional commit format
   - Includes co-author tag for Claude

4. **Claude pushes to GitHub**
   ```bash
   git push origin main
   ```
   - CI/CD automatically starts on GitHub

5. **Claude restarts app (if needed)**
   ```bash
   sudo systemctl restart lumiera-whatsapp.service
   ```
   - Or confirms uvicorn is auto-reloading

6. **Claude confirms deployment**
   - Shows you the commit SHA
   - Links to GitHub Actions
   - Confirms app is running

## 🎯 Your New Workflow Summary

### Before (Manual):
1. Ask for changes
2. Manually test
3. Manually commit
4. Manually push
5. Manually restart app
6. Manually check status

### After (Automated):
1. Ask for changes
2. Say "Ship it"
3. ✨ Done! Everything happens automatically

## 🆘 Troubleshooting

### Tests fail during deployment
- Claude will stop and show you the errors
- Fix the issues
- Say "Ship it" again

### App doesn't restart
- Check if systemd service is running: `systemctl status lumiera-whatsapp.service`
- If running manually with `./run.sh`, it auto-reloads

### Push fails (merge conflicts)
- Claude will detect this
- Pull changes first: `git pull origin main`
- Resolve conflicts
- Say "Ship it" again

### CI/CD fails on GitHub
- Check Actions tab: https://github.com/travoro/lumiera_whatsapp_api/actions
- Claude can help debug the failures

## 📚 Related Documentation

- [CI-CD.md](../deployment/CI-CD.md) - Complete CI/CD setup guide
- [DEVELOPMENT.md](DEVELOPMENT.md) - Development tools and environment
- [CICD-SETUP-CHECKLIST.md](../deployment/CICD-SETUP-CHECKLIST.md) - Setup checklist

---

**Ready to try?** Just ask Claude to make a change, then say "Ship it!" 🚀

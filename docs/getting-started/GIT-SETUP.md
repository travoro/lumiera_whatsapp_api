# Git Configuration Guide

## ✅ Current Configuration

Your git is now configured with:
- **Name:** travoro
- **Email:** traian@lumiera.paris

## 🔍 Check Your Configuration

```bash
git config user.name
git config user.email
```

## 🔧 Change Configuration

### Change name:
```bash
git config --global user.name "Your New Name"
```

### Change email:
```bash
git config --global user.email "your.new.email@example.com"
```

### View all settings:
```bash
git config --list
```

## 🌐 Global vs Local Configuration

### Global (applies to all repos):
```bash
git config --global user.name "travoro"
git config --global user.email "traian@lumiera.paris"
```

### Local (only for this repo):
```bash
git config user.name "travoro"
git config user.email "traian@lumiera.paris"
```

## 🔐 GitHub Authentication

You're using SSH (git@github.com), which is already configured since you can push/pull.

### Check SSH keys:
```bash
ls -la ~/.ssh
```

### Test GitHub connection:
```bash
ssh -T git@github.com
```

Expected output: `Hi travoro! You've successfully authenticated...`

## 📝 Commit Signature

### Sign commits with GPG (optional):
```bash
# Generate GPG key
gpg --full-generate-key

# List keys
gpg --list-secret-keys --keyid-format=long

# Configure git to use it
git config --global user.signingkey YOUR_KEY_ID
git config --global commit.gpgsign true

# Add to GitHub
gpg --armor --export YOUR_KEY_ID
# Copy output and add to GitHub: Settings → SSH and GPG keys
```

## 🎯 Quick Reference

| Command | Description |
|---------|-------------|
| `git config user.name` | Show configured name |
| `git config user.email` | Show configured email |
| `git config --global user.name "Name"` | Set global name |
| `git config --global user.email "email"` | Set global email |
| `git config --list` | Show all settings |
| `git config --unset user.name` | Remove setting |

## ✨ Best Practices

1. **Use your GitHub email** to link commits to your GitHub account
2. **Enable GPG signing** for verified commits (optional)
3. **Keep email private** using GitHub's noreply email:
   - Format: `USERNAME@users.noreply.github.com`
   - Example: `travoro@users.noreply.github.com`
   - Get yours: GitHub Settings → Emails

## 🆘 Troubleshooting

### Commits not showing on GitHub profile?
- Make sure your git email matches your GitHub account email
- Or add your git email to GitHub: Settings → Emails

### Need to change author of last commit?
```bash
git commit --amend --author="travoro <traian@lumiera.paris>"
```

### Change author of multiple commits?
```bash
git rebase -i HEAD~5  # Last 5 commits
# Mark commits as 'edit', then for each:
git commit --amend --author="travoro <traian@lumiera.paris>" --no-edit
git rebase --continue
```

## 🔗 Related Documentation

- [GitHub: Setting your commit email](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/setting-your-commit-email-address)
- [GitHub: Managing commit signature verification](https://docs.github.com/en/authentication/managing-commit-signature-verification)

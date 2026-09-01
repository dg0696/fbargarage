# Git Workflow Guide

**Audience:** Developer (primary); Operations (secondary)  
**Audiences:** developer, operations  
**Status:** Active  
**Doc-reviewed:** 2026-08-31  
**Summary:** Commit conventions, branching, and release steps for this repo. Shipping now uses `/ctp` from gitrepos standards.

---

Shipping now uses `/ctp` from gitrepos standards.

This document outlines the git workflow, commit conventions, and release procedures for the eBay Store Financial Analysis project.

## Commit Message Conventions

We follow [Conventional Commits](https://www.conventionalcommits.org/) specification for commit messages.

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types

- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation only changes
- `style`: Code style changes (formatting, missing semi-colons, etc.)
- `refactor`: Code refactoring without bug fixes or new features
- `perf`: Performance improvements
- `test`: Adding or updating tests
- `chore`: Maintenance tasks, dependency updates
- `archive`: Archiving files or data

### Examples

```
feat(archive): add archive script with manifest generation

Add Python script to archive old files based on age criteria.
Includes dry-run mode and JSON manifest generation.

Closes #1
```

```
fix(reports): correct date parsing in transaction reports

Fix issue where dates with timezone were not parsed correctly.
```

```
docs(readme): update setup instructions

Add virtual environment setup steps to README.
```

```
chore(deps): update Python dependencies

Update pandas to 2.0.0 and add new data processing libraries.
```

## Branch Naming

### Main Branches

- `main`: Production-ready code
- `develop`: Development branch (if using Git Flow)

### Feature Branches

Format: `feature/<description>`

Examples:
- `feature/archive-script`
- `feature/tax-report-generator`
- `feature/data-validation`

### Hotfix Branches

Format: `hotfix/<description>`

Examples:
- `hotfix/fix-date-parsing`
- `hotfix/correct-tax-calculations`

### Release Branches

Format: `release/v<version>`

Examples:
- `release/v1.0.0`
- `release/v1.1.0`

## Tagging Strategy

We use [Semantic Versioning](https://semver.org/) (SemVer) for tags: `vMAJOR.MINOR.PATCH`

### Version Components

- **MAJOR**: Breaking changes or major feature additions
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes and minor improvements

### Tag Examples

- `v0.1.0`: Initial setup
- `v1.0.0`: First production release
- `v1.1.0`: Added new report generation feature
- `v1.1.1`: Fixed bug in date calculations
- `v2.0.0`: Major refactoring with breaking changes

## Release Process

### Creating a Release

1. **Update CHANGELOG.md**
   - Add new version section
   - List all changes since last release
   - Update version links

2. **Update Version Numbers**
   - Update version in any configuration files
   - Update version in documentation if needed

3. **Create Release Branch** (optional for major releases)
   ```bash
   git checkout -b release/v1.0.0
   ```

4. **Final Testing**
   - Run all tests
   - Verify documentation
   - Test archive functionality

5. **Create Annotated Tag**
   ```bash
   git tag -a v1.0.0 -m "Release v1.0.0: Initial production release"
   ```

6. **Push Tag to Remote**
   ```bash
   git push origin v1.0.0
   # Or push all tags
   git push origin --tags
   ```

7. **Create Release Notes**
   - Create file in `releases/v1.0.0.md`
   - Copy relevant section from CHANGELOG.md
   - Add any additional release-specific notes

8. **Merge to Main** (if using release branch)
   ```bash
   git checkout main
   git merge release/v1.0.0
   git push origin main
   ```

### Release Checklist

- [ ] CHANGELOG.md updated
- [ ] Version numbers updated
- [ ] All tests passing
- [ ] Documentation reviewed
- [ ] Tag created and pushed
- [ ] Release notes created
- [ ] GitHub release created (if applicable)

## When to Create Tags

Create tags for:

- **Major Releases**: Significant new features or breaking changes
- **Minor Releases**: New features or improvements
- **Patch Releases**: Bug fixes
- **Milestones**: Important project milestones
- **Initial Setup**: First commit (v0.1.0)

Do not create tags for:
- Every commit
- Work-in-progress features
- Experimental changes

## Tag Commands

### Create Annotated Tag

```bash
git tag -a v1.0.0 -m "Release v1.0.0: Description"
```

### Create Lightweight Tag

```bash
git tag v1.0.0
```

### List Tags

```bash
git tag
git tag -l "v1.*"  # List tags matching pattern
```

### Show Tag Information

```bash
git show v1.0.0
```

### Delete Tag (Local)

```bash
git tag -d v1.0.0
```

### Delete Tag (Remote)

```bash
git push origin --delete v1.0.0
```

### Push Single Tag

```bash
git push origin v1.0.0
```

### Push All Tags

```bash
git push origin --tags
```

## Workflow Examples

### Feature Development

```bash
# Create feature branch
git checkout -b feature/new-analysis-script

# Make changes and commit
git add .
git commit -m "feat(analysis): add revenue analysis script"

# Push branch
git push origin feature/new-analysis-script

# Create pull request (if using GitHub)
# After review, merge to main
```

### Hotfix

```bash
# Create hotfix branch from main
git checkout -b hotfix/fix-calculation main

# Fix the issue
git add .
git commit -m "fix(calc): correct tax calculation formula"

# Tag and release
git tag -a v1.0.1 -m "Release v1.0.1: Fix tax calculation"
git push origin v1.0.1
git push origin hotfix/fix-calculation
```

### Release

```bash
# Update CHANGELOG
# ... edit CHANGELOG.md ...

git add CHANGELOG.md
git commit -m "docs(changelog): update for v1.0.0 release"

# Create tag
git tag -a v1.0.0 -m "Release v1.0.0: Initial production release"

# Push everything
git push origin main
git push origin v1.0.0
```

## Best Practices

1. **Write Clear Commit Messages**
   - Use imperative mood ("Add feature" not "Added feature")
   - Keep subject line under 50 characters
   - Explain "what" and "why" in the body

2. **Commit Often**
   - Make small, logical commits
   - Each commit should represent a complete, working change

3. **Review Before Pushing**
   - Review your changes with `git diff`
   - Ensure commits are logical and complete

4. **Use Branches**
   - Keep main branch stable
   - Use feature branches for new work
   - Use hotfix branches for urgent fixes

5. **Tag Releases**
   - Always tag releases
   - Use annotated tags with descriptive messages
   - Push tags to remote

6. **Update CHANGELOG**
   - Update CHANGELOG.md with each release
   - Include all significant changes
   - Link to issues/PRs when applicable

## Troubleshooting

### Accidentally Committed to Main

```bash
# Create branch from current state
git branch feature/my-feature

# Reset main to previous commit
git reset --hard origin/main

# Continue work on feature branch
git checkout feature/my-feature
```

### Need to Amend Last Commit

```bash
# Make changes
git add .
git commit --amend -m "Updated commit message"

# Force push if already pushed (use with caution)
git push --force-with-lease origin branch-name
```

### Tagged Wrong Commit

```bash
# Delete local tag
git tag -d v1.0.0

# Create tag on correct commit
git tag -a v1.0.0 <commit-hash> -m "Corrected release"

# Force push tag
git push origin v1.0.0 --force
```

## Questions or Issues

For questions about git workflow or to report issues:
1. Review this document
2. Check git log for examples: `git log --oneline --decorate`
3. Open an issue on GitHub

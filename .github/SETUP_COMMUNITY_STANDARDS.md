# GitHub Community Standards Setup Guide

This document explains the GitHub community files that have been added to this repository and how to use them effectively.

## Files Created

### 1. Core Documentation

#### `CONTRIBUTING.md`
Comprehensive guide for contributors covering:
- Development setup instructions
- Coding standards (Python and JavaScript)
- Commit message guidelines
- Pull request process
- Testing guidelines
- Research contribution guidelines

**Action Required**: None - this file is ready to use.

#### `CODE_OF_CONDUCT.md`
Based on the Contributor Covenant 2.1, adapted for academic projects with additional guidelines for:
- Academic integrity
- Proper attribution
- Reproducible research practices

**Action Required**: None - standard code of conduct in place.

### 2. Issue Templates

Located in `.github/ISSUE_TEMPLATE/`:

#### `bug_report.md`
Template for bug reports with sections for:
- Steps to reproduce
- Environment details
- Configuration information
- Screenshots/logs

#### `feature_request.md`
Template for feature requests including:
- Problem/motivation
- Proposed solution
- Use cases
- Collection type applicability

#### `research_contribution.md`
Unique template for academic contributions:
- Research methodology
- Evaluation metrics
- Dataset information
- Publication details
- Collaboration opportunities

#### `documentation.md`
Template for documentation improvements

#### `config.yml`
Configuration for issue templates, enabling GitHub Discussions integration

**Action Required**: Update the GitHub repository URLs in `config.yml` (lines 4, 6) if needed.

### 3. Pull Request Template

`.github/PULL_REQUEST_TEMPLATE.md`

Comprehensive PR template with:
- Change type selection
- Testing checklist
- Code quality checklist
- Documentation checklist
- Research-specific sections

**Action Required**: None - ready to use.

### 4. GitHub Actions Workflows

#### `.github/workflows/code-quality.yml`
Automated checks for:
- Python code formatting (black, isort)
- Python linting (flake8)
- Python tests (pytest)
- Frontend linting (ESLint for all three apps)
- Dependency review

**Action Required**: 
- This workflow will run automatically on PRs
- Consider adding `flake8` to `requirements.txt` if not present
- Create a `tests/` directory and add pytest tests as the project grows

### 5. Dependency Management

#### `.github/dependabot.yml`
Automated dependency updates for:
- Python packages (monthly)
- Frontend packages for all three apps (monthly)
- GitHub Actions (monthly)

**Action Required**: None - Dependabot will automatically create PRs for dependency updates.

### 6. Funding

#### `.github/FUNDING.yml`
Template for adding sponsorship/funding information

**Action Required**: Uncomment and add relevant funding platform usernames if you want to accept sponsorships.

### 7. Labels

#### `.github/labels.json`
Suggested label set including:
- Standard labels (bug, enhancement, documentation)
- Research-specific (research, ml-model)
- Collection-specific (photographs, maps, documents)
- Technical labels (frontend, backend, python, javascript)

**Action Required**: Import these labels to your GitHub repository (see below).

## Setup Instructions

### Step 1: Enable GitHub Discussions (Optional but Recommended)

1. Go to your repository settings on GitHub
2. Scroll to "Features"
3. Check "Discussions"

This enables the discussion link in the issue template config.

### Step 2: Import Labels

You can import the labels using GitHub CLI:

```bash
# Install GitHub CLI if not already installed
# https://cli.github.com/

# Navigate to your repository
cd /path/to/digital-collections-explorer

# Import labels (requires authentication)
gh label create --json name,description,color < .github/labels.json
```

Or manually create them in GitHub:
1. Go to Issues → Labels
2. Create new labels matching those in `labels.json`

### Step 3: Update README.md

The README has been updated with links to:
- `CONTRIBUTING.md`
- Issue templates
- PR template
- `CODE_OF_CONDUCT.md`

**Already completed** ✓

### Step 4: Configure Branch Protection (Recommended)

For the `main` branch:

1. Go to Settings → Branches
2. Add rule for `main`
3. Recommended settings:
   - Require pull request reviews before merging
   - Require status checks to pass (select the code-quality workflow)
   - Require branches to be up to date before merging
   - Include administrators (optional)

### Step 5: Test the Setup

1. Create a test issue using one of the templates
2. Create a test PR to verify the template appears
3. Push a commit to trigger the GitHub Actions workflow
4. Verify Dependabot creates PRs (may take 24-48 hours)

## Customization

### Adjust Issue Templates

Edit files in `.github/ISSUE_TEMPLATE/` to:
- Add or remove fields
- Change labels
- Adjust wording for your audience

### Modify GitHub Actions

Edit `.github/workflows/code-quality.yml` to:
- Add more checks (e.g., security scanning, Docker builds)
- Change Python/Node versions
- Add deployment workflows
- Configure code coverage reporting

### Update Contributing Guidelines

Edit `CONTRIBUTING.md` to:
- Add project-specific development tips
- Include institution-specific guidelines
- Add more detailed examples
- Link to additional resources

## Best Practices

### For Maintainers

1. **Triage issues regularly** using the provided labels
2. **Use templates yourself** when creating issues
3. **Welcome first-time contributors** (comment on their first PR)
4. **Keep templates updated** as the project evolves
5. **Respond to issues promptly** (even if just to acknowledge)
6. **Close stale issues** with a polite comment

### For Contributors

1. **Read CONTRIBUTING.md** before making your first contribution
2. **Use the appropriate issue template** when reporting problems
3. **Follow the PR template checklist** completely
4. **Be patient** - maintainers are often volunteers
5. **Be respectful** as outlined in CODE_OF_CONDUCT.md

## Monitoring Community Health

GitHub provides a "Community Standards" checklist:

1. Go to Insights → Community Standards
2. Check that all items are green ✓
3. Items should include:
   - Description
   - README
   - Code of conduct
   - Contributing guidelines
   - License
   - Issue templates
   - Pull request template

## Additional Enhancements (Optional)

Consider adding:

1. **GitHub Discussions Categories**:
   - Announcements
   - Q&A
   - Ideas
   - Research
   - Show and Tell

2. **Wiki** for:
   - Detailed tutorials
   - Architecture documentation
   - Research notes
   - FAQ

3. **Projects** for:
   - Roadmap tracking
   - Release planning
   - Research milestones

4. **Releases** with:
   - Semantic versioning
   - Changelog
   - Release notes
   - Pre-built artifacts (if applicable)

## Resources

- [GitHub Community Standards](https://opensource.guide/)
- [Contributor Covenant](https://www.contributor-covenant.org/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Dependabot Documentation](https://docs.github.com/en/code-security/dependabot)

## Support

If you have questions about these community files:

1. Check the individual file's documentation
2. Review GitHub's documentation
3. Open a discussion in GitHub Discussions
4. Ask in an issue with the "question" label

---

**Last Updated**: October 2025

These files represent current best practices for open source projects. They should be reviewed and updated periodically as the project and community grow.

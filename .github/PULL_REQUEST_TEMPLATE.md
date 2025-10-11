## Description

<!-- Provide a clear and concise description of your changes -->

## Motivation and Context

<!-- Why is this change needed? What problem does it solve? -->
<!-- If it fixes an open issue, please link to the issue here using #issue_number -->

Fixes #(issue)

## Type of Change

<!-- Mark the relevant option with an "x" -->

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Code refactoring (no functional changes)
- [ ] Performance improvement
- [ ] Research contribution (new models, evaluation methods, etc.)
- [ ] Other (please describe):

## Component(s) Affected

<!-- Mark all that apply -->

- [ ] Backend (Python/FastAPI)
- [ ] Frontend - Photographs
- [ ] Frontend - Maps
- [ ] Frontend - Documents
- [ ] CLIP/ML models
- [ ] Configuration
- [ ] Documentation
- [ ] Tests
- [ ] Build/deployment

## Changes Made

<!-- List the main changes in bullet points -->

- Change 1
- Change 2
- Change 3

## Testing

### How Has This Been Tested?

<!-- Describe the tests you ran and how to reproduce them -->

- [ ] Test A: Description
- [ ] Test B: Description

### Test Configuration

- **Collection type tested**: [photographs/maps/documents/all]
- **Python version**: [e.g., 3.10]
- **Node version**: [e.g., 18]
- **OS**: [e.g., macOS, Ubuntu]
- **CLIP model**: [e.g., openai/clip-vit-base-patch32]

## Screenshots (if applicable)

<!-- Add screenshots to demonstrate UI changes -->

| Before | After |
|--------|-------|
| (screenshot) | (screenshot) |

## Checklist

<!-- Mark completed items with an "x" -->

### Code Quality

- [ ] My code follows the project's coding standards
- [ ] I have run `black .` and `isort .` on Python code
- [ ] I have run `npm run lint` on frontend code (if applicable)
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] My changes generate no new warnings or errors

### Testing

- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] I have tested this locally with actual data

### Documentation

- [ ] I have updated the documentation accordingly
- [ ] I have updated the README if needed
- [ ] I have added docstrings to new functions/classes
- [ ] I have updated `config.json` documentation if config changes were made

### Dependencies

- [ ] I have updated `requirements.txt` (if Python dependencies changed)
- [ ] I have updated `package.json` (if Node dependencies changed)
- [ ] I have documented any new configuration options

### Research (if applicable)

- [ ] I have included references to relevant papers or research
- [ ] I have shared evaluation results or benchmarks
- [ ] I have included information about datasets used
- [ ] I have documented model training procedures

## Breaking Changes

<!-- If this PR contains breaking changes, describe them here -->
<!-- Include migration instructions for users -->

None / (describe breaking changes)

## Additional Notes

<!-- Any additional information that reviewers should know -->

## Reviewers Checklist (for maintainers)

- [ ] Code quality and style compliance
- [ ] Test coverage adequate
- [ ] Documentation complete
- [ ] No security concerns
- [ ] Performance implications acceptable
- [ ] Breaking changes documented

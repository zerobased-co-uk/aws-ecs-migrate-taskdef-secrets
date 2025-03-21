# ECS Task Definition Secrets Updater

This repository contains a Python script to help convert environment variables in AWS ECS task definition files into secrets managed by AWS Secrets Manager. It supports processing multiple task definition files and ensures that if an environment variable appears in more than one file, its values are consistent before consolidating them as a single secret.

## Features

- **Multi-file Support:** Process one or more ECS task definition JSON files at once.
- **Environment Variable Scanning:** Automatically collect and verify environment variables across files.
- **Conflict Resolution:** If an environment variable has conflicting values, the script prompts you to enter a single value or skip it.
- **AWS Secrets Manager Integration:** Creates or updates a single secret with the selected key–value pairs.
- **Task Definition Update:** Replaces plain environment variable definitions with secret references using the actual secret ARN.
- **Output Files:** Writes updated task definitions to new files prefixed with `updated_`.

## Prerequisites

- **Python 3.x**
- **AWS Credentials:** Ensure your AWS credentials are properly configured (using environment variables, the AWS credentials file, or an IAM role).
- **Python Dependencies:** The script uses [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) to interact with AWS Secrets Manager.

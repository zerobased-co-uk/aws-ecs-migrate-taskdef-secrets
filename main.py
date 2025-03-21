#!/usr/bin/env python3
import json
import os
import sys
import boto3
import botocore.exceptions

def collect_env_vars(file_list):
    """
    Iterate over all task definition files and collect environment variables.
    Returns:
      env_candidates: dict mapping env var name to a dict with:
          "overall": set of all encountered values across files,
          "files": dict mapping filename -> set of values found in that file.
      file_data: dict mapping filename to its loaded task definition.
    """
    env_candidates = {}
    file_data = {}
    for file in file_list:
        try:
            with open(file, 'r') as f:
                task_def = json.load(f)
        except Exception as e:
            print(f"Error loading file {file}: {e}")
            continue
        file_data[file] = task_def
        # Process each container's environment variables.
        for container in task_def.get("containerDefinitions", []):
            env_vars = container.get("environment", [])
            for env in env_vars:
                name = env.get("name")
                value = env.get("value")
                if not name:
                    continue
                if name not in env_candidates:
                    env_candidates[name] = {"overall": set(), "files": {}}
                env_candidates[name]["overall"].add(value)
                env_candidates[name]["files"].setdefault(file, set()).add(value)
    return env_candidates, file_data

def prompt_secrets(env_candidates):
    """
    For each environment variable, prompt the user to decide if it should be stored as a secret.
    For variables with conflicting values across files, the user must enter a single value.
    Returns:
      secret_values: dict mapping env var names to the value to be stored as a secret.
    """
    secret_values = {}
    for name, data in env_candidates.items():
        overall = data["overall"]
        if len(overall) == 1:
            # Consistent value across all occurrences.
            value = next(iter(overall))
            answer = input(f"Should env var '{name}' (value: '{value}') be stored as a secret? (y/n): ").strip().lower()
            if answer in ['y', 'yes']:
                secret_values[name] = value
        else:
            # Conflicting values across files.
            print(f"Warning: Environment variable '{name}' has conflicting values:")
            for file, values in data["files"].items():
                print(f"  In file {file}: {list(values)}")
            chosen = input(f"Enter a single value to use for secret '{name}' (or leave blank to skip): ").strip()
            if chosen:
                # Verify that the chosen value is present in all file sets.
                missing_files = [file for file, values in data["files"].items() if chosen not in values]
                if missing_files:
                    print(f"Chosen value '{chosen}' for '{name}' is not present in the following file(s): {missing_files}. Skipping secret for '{name}'.")
                else:
                    secret_values[name] = chosen
    return secret_values

def update_task_definitions(file_data, secret_values):
    """
    For each file's task definition, remove any environment variable that's selected to be a secret,
    and add a secret reference in the container definition.
    """
    for file, task_def in file_data.items():
        for container in task_def.get("containerDefinitions", []):
            env_vars = container.get("environment", [])
            new_env_vars = []
            # Ensure there is a secrets list (or create one)
            secrets_list = container.get("secrets", [])
            for env in env_vars:
                name = env.get("name")
                if name in secret_values:
                    # Add a placeholder for the secret reference.
                    secrets_list.append({
                        "name": name,
                        "valueFrom": f"{{SECRET_ARN}}:{name}::"
                    })
                else:
                    new_env_vars.append(env)
            container["environment"] = new_env_vars
            container["secrets"] = secrets_list

def write_updated_files(file_data):
    """
    Write each updated task definition back to a file with a prefix "updated_".
    """
    for file, task_def in file_data.items():
        updated_filename = "updated_" + os.path.basename(file)
        try:
            with open(updated_filename, 'w') as f:
                json.dump(task_def, f, indent=4)
            print(f"Updated task definition saved to '{updated_filename}'.")
        except Exception as e:
            print(f"Error writing updated task definition for file {file}: {e}")

def create_or_update_secret(secret_name, secret_values):
    """
    Create a new secret (or update an existing one) in AWS Secrets Manager with the provided secret_values.
    Returns the secret ARN.
    """
    client = boto3.client('secretsmanager')
    secret_arn = None
    try:
        response = client.create_secret(
            Name=secret_name,
            SecretString=json.dumps(secret_values)
        )
        secret_arn = response["ARN"]
        print(f"Created secret '{secret_name}' with ARN: {secret_arn}")
    except client.exceptions.ResourceExistsException:
        print(f"Secret '{secret_name}' already exists. Updating secret value...")
        try:
            client.put_secret_value(
                SecretId=secret_name,
                SecretString=json.dumps(secret_values)
            )
            secret_desc = client.describe_secret(SecretId=secret_name)
            secret_arn = secret_desc["ARN"]
            print(f"Updated secret '{secret_name}' with ARN: {secret_arn}")
        except botocore.exceptions.ClientError as e:
            print(f"Error updating secret: {e}")
            sys.exit(1)
    except botocore.exceptions.ClientError as e:
        print(f"Error creating secret: {e}")
        sys.exit(1)
    return secret_arn

def replace_placeholder_with_arn(file_data, secret_arn):
    """
    Replace the placeholder "{SECRET_ARN}" in each container's secret references with the actual secret ARN.
    """
    for file, task_def in file_data.items():
        for container in task_def.get("containerDefinitions", []):
            for secret in container.get("secrets", []):
                if "valueFrom" in secret and "{SECRET_ARN}" in secret["valueFrom"]:
                    secret["valueFrom"] = secret["valueFrom"].replace("{SECRET_ARN}", secret_arn)

def main():
    if len(sys.argv) < 2:
        print("Usage: python update_taskdefs_secrets.py <ecs_task_definition1.json> [ecs_task_definition2.json ...]")
        sys.exit(1)
    
    file_list = sys.argv[1:]
    env_candidates, file_data = collect_env_vars(file_list)
    if not env_candidates:
        print("No environment variables found in the provided task definition files.")
        sys.exit(0)
    
    secret_values = prompt_secrets(env_candidates)
    if not secret_values:
        print("No secrets selected. Exiting without making changes.")
        sys.exit(0)
    
    update_task_definitions(file_data, secret_values)
    
    secret_name = input("Enter the AWS Secrets Manager secret name to store these secrets: ").strip()
    secret_arn = create_or_update_secret(secret_name, secret_values)
    
    replace_placeholder_with_arn(file_data, secret_arn)
    write_updated_files(file_data)

if __name__ == "__main__":
    main()

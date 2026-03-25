"""Deploy this API to Lambda + HTTP API Gateway (boto3, no SAM). Run from backend/: python deploy.py"""

import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
_env_file = BACKEND_DIR / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        pass

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print("Install boto3: pip install boto3")
    sys.exit(1)


def _env_str(key: str, default: str) -> str:
    """GitHub Actions often sets optional secrets to empty string; treat that as unset."""
    v = os.environ.get(key, "").strip()
    return v if v else default


REGION = _env_str("AWS_REGION", "us-east-1")
FUNCTION_NAME = _env_str("LAMBDA_FUNCTION_NAME", "text-to-languages-api")
API_NAME = _env_str("API_NAME", "text-to-languages-api")
ROLE_NAME = _env_str("LAMBDA_ROLE_NAME", "text-to-languages-lambda-role")
LAMBDA_ROLE_ARN = os.environ.get("LAMBDA_ROLE_ARN", "").strip()
LAMBDA_TIMEOUT = 30
LAMBDA_MEMORY = 256
TRANSLATIONS_TABLE_NAME = _env_str("TRANSLATIONS_TABLE", "translations")
USERS_TABLE_NAME = _env_str("USERS_TABLE", "users")

ZIP_PATH = BACKEND_DIR / "lambda_deploy.zip"

# HTTP API CORS — must not use AllowCredentials with AllowOrigins * (browser blocks).
# Kept in sync on every deploy so CI and local CLI produce the same API behavior.
HTTP_API_CORS = {
    "AllowOrigins": ["*"],
    "AllowMethods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    "AllowHeaders": ["*"],
    "ExposeHeaders": ["*"],
    "MaxAge": 86400,
}


def build_zip():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for f in ("app.py", "translate.py", "store.py", "auth_utils.py", "user_store.py"):
            shutil.copy(BACKEND_DIR / f, tmp / f)
        req_lambda = BACKEND_DIR / "requirements-lambda.txt"
        req_file = req_lambda if req_lambda.exists() else BACKEND_DIR / "requirements.txt"
        pip_cmd = [
            sys.executable, "-m", "pip", "install",
            "-r", str(req_file),
            "-t", str(tmp),
            "--platform", "manylinux2014_x86_64",
            "--python-version", "39",
            "--implementation", "cp",
            "--only-binary", ":all:",
            "--upgrade",
            "-q",
        ]
        result = subprocess.run(pip_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("pip install failed. stderr:", result.stderr or "(none)")
            print("stdout:", result.stdout or "(none)")
            result.check_returncode()
        if ZIP_PATH.exists():
            ZIP_PATH.unlink()
        with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in tmp.rglob("*"):
                if f.is_file():
                    arcname = f.relative_to(tmp)
                    zf.write(f, arcname)
    print(f"Built {ZIP_PATH}")


def get_or_create_role(iam):
    role_name = ROLE_NAME
    try:
        role = iam.get_role(RoleName=role_name)
        return role["Role"]["Arn"]
    except ClientError as e:
        if e.response["Error"]["Code"] != "NoSuchEntity":
            raise
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    role = iam.create_role(
        RoleName=role_name,
        AssumeRolePolicyDocument=json.dumps(trust),
        Description="Execution role for text-to-languages Lambda",
    )
    iam.attach_role_policy(
        RoleName=role_name,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    )
    _attach_dynamodb_policy(iam, role_name)
    print(f"Created IAM role: {role_name}")
    return role["Role"]["Arn"]


def _attach_dynamodb_policy(iam, role_name):
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem",
                    "dynamodb:Scan", "dynamodb:UpdateItem", "dynamodb:BatchGetItem", "dynamodb:Query",
                ],
                "Resource": [
                    f"arn:aws:dynamodb:{REGION}:*:table/{TRANSLATIONS_TABLE_NAME}",
                    f"arn:aws:dynamodb:{REGION}:*:table/{USERS_TABLE_NAME}",
                    f"arn:aws:dynamodb:{REGION}:*:table/{USERS_TABLE_NAME}/index/*",
                ],
            }
        ],
    }
    try:
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName="DynamoDBTranslations",
            PolicyDocument=json.dumps(policy),
        )
        print("Attached DynamoDB policy to role")
    except Exception as e:
        print(f"Warning: could not attach DynamoDB policy: {e}")


def ensure_dynamodb_table(dynamodb_client):
    try:
        dynamodb_client.describe_table(TableName=TRANSLATIONS_TABLE_NAME)
        print(f"DynamoDB table exists: {TRANSLATIONS_TABLE_NAME}")
        return TRANSLATIONS_TABLE_NAME
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    dynamodb_client.create_table(
        TableName=TRANSLATIONS_TABLE_NAME,
        KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    print(f"Created DynamoDB table: {TRANSLATIONS_TABLE_NAME}")
    return TRANSLATIONS_TABLE_NAME


def ensure_users_table(dynamodb_client):
    try:
        dynamodb_client.describe_table(TableName=USERS_TABLE_NAME)
        print(f"DynamoDB table exists: {USERS_TABLE_NAME}")
        return USERS_TABLE_NAME
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    dynamodb_client.create_table(
        TableName=USERS_TABLE_NAME,
        KeySchema=[{"AttributeName": "email", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "email", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "user_id-index",
                "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    print(f"Created DynamoDB table: {USERS_TABLE_NAME}")
    return USERS_TABLE_NAME


def _wait_for_lambda_ready(lambda_client, max_wait=60):
    for _ in range(max_wait):
        cfg = lambda_client.get_function(FunctionName=FUNCTION_NAME)["Configuration"]
        status = cfg.get("LastUpdateStatus") or cfg.get("State")
        if status not in ("InProgress",):
            return
        time.sleep(2)
    raise RuntimeError(f"Lambda {FUNCTION_NAME} still updating after {max_wait}s")


def create_or_update_lambda(lambda_client, role_arn, translations_table_name=None):
    with open(ZIP_PATH, "rb") as f:
        zip_bytes = f.read()

    env_vars = {}
    if translations_table_name:
        env_vars["TRANSLATIONS_TABLE"] = translations_table_name
    env_vars["USERS_TABLE"] = USERS_TABLE_NAME
    jwt_secret = os.environ.get("JWT_SECRET", "").strip()
    if jwt_secret:
        env_vars["JWT_SECRET"] = jwt_secret

    try:
        cfg = lambda_client.get_function(FunctionName=FUNCTION_NAME)["Configuration"]
        lambda_client.update_function_code(FunctionName=FUNCTION_NAME, ZipFile=zip_bytes)
        print("Waiting for Lambda code update to finish...")
        _wait_for_lambda_ready(lambda_client)
        current_env = cfg.get("Environment", {}).get("Variables") or {}
        new_env = {**current_env, **env_vars}
        try:
            lambda_client.update_function_configuration(
                FunctionName=FUNCTION_NAME,
                Timeout=LAMBDA_TIMEOUT,
                MemorySize=LAMBDA_MEMORY,
                Environment={"Variables": new_env},
            )
        except ClientError as cfg_err:
            if cfg_err.response["Error"]["Code"] == "ResourceConflictException":
                print("Lambda still busy, waiting then retrying configuration...")
                _wait_for_lambda_ready(lambda_client)
                lambda_client.update_function_configuration(
                    FunctionName=FUNCTION_NAME,
                    Timeout=LAMBDA_TIMEOUT,
                    MemorySize=LAMBDA_MEMORY,
                    Environment={"Variables": new_env},
                )
            else:
                raise
        print(f"Updated Lambda: {FUNCTION_NAME}")
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        lambda_client.create_function(
            FunctionName=FUNCTION_NAME,
            Runtime="python3.9",
            Role=role_arn,
            Handler="app.handler",
            Code={"ZipFile": zip_bytes},
            Timeout=LAMBDA_TIMEOUT,
            MemorySize=LAMBDA_MEMORY,
            Environment={"Variables": env_vars} if env_vars else {},
        )
        print(f"Created Lambda: {FUNCTION_NAME}")

    return lambda_client.get_function(FunctionName=FUNCTION_NAME)["Configuration"]["FunctionArn"]


def create_api_and_routes(apigw, lambda_client, function_arn, account_id):
    api_id = None
    try:
        apis = apigw.get_apis()["Items"]
        for api in apis:
            if api.get("Name") == API_NAME:
                api_id = api["ApiId"]
                print(f"Using existing API: {API_NAME} ({api_id})")
                break
    except Exception:
        pass

    if not api_id:
        api = apigw.create_api(
            Name=API_NAME,
            ProtocolType="HTTP",
            CorsConfiguration=HTTP_API_CORS,
        )
        api_id = api["ApiId"]
        print(f"Created API: {API_NAME} ({api_id})")
    else:
        # Existing API: re-apply CORS so CI deploy matches local CLI (avoids stale GW-only CORS).
        try:
            apigw.update_api(ApiId=api_id, CorsConfiguration=HTTP_API_CORS)
            print("Updated API Gateway CORS (aligned with Lambda / FastAPI).")
        except ClientError as e:
            print(f"Warning: could not update API CORS: {e}")

    integration_id = None
    try:
        integrations = apigw.get_integrations(ApiId=api_id)["Items"]
        for i in integrations:
            if i.get("IntegrationUri") == function_arn:
                integration_id = i["IntegrationId"]
                break
    except Exception:
        pass

    if not integration_id:
        integ = apigw.create_integration(
            ApiId=api_id,
            IntegrationType="AWS_PROXY",
            IntegrationUri=function_arn,
            PayloadFormatVersion="2.0",
        )
        integration_id = integ["IntegrationId"]
        print("Created Lambda integration")

    route_key = "ANY /{proxy+}"
    routes = apigw.get_routes(ApiId=api_id).get("Items", [])
    route_keys = {r.get("RouteKey") for r in routes}
    if route_key not in route_keys:
        apigw.create_route(
            ApiId=api_id,
            RouteKey=route_key,
            Target=f"integrations/{integration_id}",
        )
        print(f"Created route: {route_key}")

    if "$default" not in route_keys:
        apigw.create_route(
            ApiId=api_id,
            RouteKey="$default",
            Target=f"integrations/{integration_id}",
        )
        print("Created route: $default")

    try:
        lambda_client.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId="apigw-invoke",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{REGION}:{account_id}:{api_id}/*",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceConflictException":
            raise

    try:
        apigw.get_stage(ApiId=api_id, StageName="$default")
    except Exception:
        apigw.create_stage(ApiId=api_id, StageName="$default", AutoDeploy=True)

    return api_id


def main():
    print("Building deployment package...")
    build_zip()

    session = boto3.Session(region_name=REGION)
    account_id = session.client("sts").get_caller_identity()["Account"]
    iam = session.client("iam")
    lambda_client = session.client("lambda")
    apigw = session.client("apigatewayv2")
    dynamodb = session.client("dynamodb")

    print("Ensuring DynamoDB tables...")
    ensure_dynamodb_table(dynamodb)
    ensure_users_table(dynamodb)

    if LAMBDA_ROLE_ARN:
        print("Using existing IAM role from LAMBDA_ROLE_ARN")
        role_arn = LAMBDA_ROLE_ARN
    else:
        print("Setting up IAM role...")
        role_arn = get_or_create_role(iam)
        time.sleep(5)

    print("Deploying Lambda...")
    function_arn = create_or_update_lambda(lambda_client, role_arn, TRANSLATIONS_TABLE_NAME)

    print("Configuring API Gateway...")
    api_id = create_api_and_routes(apigw, lambda_client, function_arn, account_id)

    base_url = f"https://{api_id}.execute-api.{REGION}.amazonaws.com"
    print("\n--- Deployment complete ---")
    print(f"API URL: {base_url}")
    print(f"  Health:  GET  {base_url}/health")
    print(f"  Translate: POST {base_url}/translate")
    print(f"  Docs:    {base_url}/docs")
    print("\nShare the API URL above with classmates for the assignment.")


if __name__ == "__main__":
    main()

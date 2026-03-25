"""Deploy this API to Lambda + HTTP API Gateway (boto3, no SAM). Run from backend/: python deploy.py"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

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

# region agent log
_DEBUG_LOG = BACKEND_DIR.parent / ".cursor" / "debug-c35cb3.log"


def _agent_debug_log(*, message: str, hypothesis_id: str, data: Optional[Dict[str, Any]] = None) -> None:
    try:
        payload = {
            "sessionId": "c35cb3",
            "timestamp": int(time.time() * 1000),
            "location": "deploy.py",
            "message": message,
            "hypothesisId": hypothesis_id,
            "data": data or {},
        }
        _DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str) + "\n")
    except Exception:
        pass


# endregion


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


def _smoke_test_health(base_url: str, *, attempts: int = 4, delay_s: float = 3.0) -> None:
    """GET /health on the deployed API. Surfaces 500s that browsers report as CORS errors."""
    url = base_url.rstrip("/") + "/health"
    last_err: Optional[str] = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=25) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                if resp.status == 200:
                    print(f"Health check OK (HTTP {resp.status}): {body[:180]}")
                    return
                last_err = f"HTTP {resp.status}: {body[:300]}"
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
            last_err = f"HTTP {e.code}: {raw[:300]}"
        except Exception as e:
            last_err = str(e)
        if i < attempts - 1:
            time.sleep(delay_s)
    print(
        "WARNING: Post-deploy health check failed after retries. "
        "Browsers often show this as a CORS error, but the API is returning an error. "
        f"Last error: {last_err}"
    )
    print(
        "Hint: Ensure GitHub Actions AWS_REGION matches the region in your API URL "
        f"(this deploy used REGION={REGION}). If the region is wrong, CI updates a "
        "Lambda in another region while Amplify still points at the old API."
    )


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
        )
        api_id = api["ApiId"]
        print(f"Created API: {API_NAME} ({api_id})")

    # Do NOT use API Gateway–managed CORS. It answers OPTIONS at the edge and often conflicts
    # with FastAPI's CORSMiddleware (duplicate / wrong ACAO → browser "CORS error"). Remove any
    # existing GW CORS so OPTIONS + all methods go through Lambda (Mangum → FastAPI).
    cors_del_ok = False
    cors_del_code: Optional[str] = None
    try:
        apigw.delete_cors_configuration(ApiId=api_id)
        cors_del_ok = True
        print("API Gateway CORS disabled — FastAPI handles CORS only.")
    except ClientError as e:
        cors_del_code = e.response.get("Error", {}).get("Code", "")
        if cors_del_code not in ("NotFoundException",):
            print(f"Warning: delete_cors_configuration: {e}")
    # region agent log
    _agent_debug_log(
        message="apigw_delete_cors",
        hypothesis_id="H2",
        data={"api_id": api_id, "cors_delete_ok": cors_del_ok, "cors_error_code": cors_del_code},
    )
    # endregion

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


def _sha256_file_short(path: Path, nbytes: int = 16) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:nbytes]


def main():
    # region agent log
    _agent_debug_log(
        message="deploy_start",
        hypothesis_id="H1",
        data={
            "github_actions": bool(os.environ.get("GITHUB_ACTIONS")),
            "github_sha_env": (os.environ.get("GITHUB_SHA") or "")[:12],
            "ci": bool(os.environ.get("CI")),
        },
    )
    # endregion
    print("Building deployment package...")
    build_zip()

    git_head = ""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(BACKEND_DIR.parent),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if r.returncode == 0:
            git_head = r.stdout.strip()
    except Exception:
        pass
    app_py = BACKEND_DIR / "app.py"
    # region agent log
    _agent_debug_log(
        message="deploy_artifacts_after_zip",
        hypothesis_id="H5",
        data={
            "git_head": git_head[:12] if git_head else "",
            "app_py_sha16": _sha256_file_short(app_py) if app_py.exists() else "",
            "zip_sha16": _sha256_file_short(ZIP_PATH) if ZIP_PATH.exists() else "",
        },
    )
    # endregion

    print(f"=== Deploy region: {REGION} (must match the region in your execute-api URL, e.g. ...execute-api.us-east-1...) ===")
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
    # region agent log
    _agent_debug_log(
        message="deploy_complete",
        hypothesis_id="H1",
        data={"api_id": api_id, "region": REGION, "function_name": FUNCTION_NAME},
    )
    # endregion

    base_url = f"https://{api_id}.execute-api.{REGION}.amazonaws.com"
    print("\n--- Deployment complete ---")
    print(f"API ID: {api_id}  (subdomain in your Amplify VITE_TRANSLATE_API_URL must match)")
    print(f"API URL: {base_url}")
    print(f"  Health:  GET  {base_url}/health")
    print(f"  Translate: POST {base_url}/translate")
    print(f"  Docs:    {base_url}/docs")
    print("\nShare the API URL above with classmates for the assignment.")
    print("")
    _smoke_test_health(base_url)


if __name__ == "__main__":
    main()

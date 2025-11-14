# --- 1. API Gateway (HTTP API) ---

# Defines the main HTTP API Gateway for the project.
# An HTTP API is chosen over a REST API for its lower cost,
# lower latency, and simpler configuration, which is ideal
# for this serverless, Lambda-based backend.
resource "aws_apigatewayv2_api" "main_api" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"

  # --- CORS Configuration ---
  # Configures CORS directly at the API Gateway level.
  # This allows the service to automatically handle browser "preflight"
  # (OPTIONS) requests without invoking the backend Lambda functions.
  # This approach is more performant and cost-effective.
  cors_configuration {
    # Allows any domain. This is a deliberate choice to support
    # the publicly hosted Streamlit frontend.
    allow_origins = ["*"]
    
    # Specifies the methods the frontend is allowed to use.
    allow_methods = ["GET", "POST"]
    
    # Specifies the headers the frontend is allowed to send.
    allow_headers = ["Content-Type"]
    
    # How long the browser can cache this preflight response.
    max_age       = 300
  }
}

# Creates the default stage for the API.
# The '$default' stage is a special stage that is automatically
# served from the API's base URL.
resource "aws_apigatewayv2_stage" "default_stage" {
  api_id      = aws_apigatewayv2_api.main_api.id
  name        = "$default"
  
  # Ensures that any changes to routes or integrations are
  # immediately deployed live.
  auto_deploy = true
}

# --- 2. API Gateway Integrations ---

# These resources define the "backend" for each API route,
# connecting them to their respective Lambda functions.
# All integrations use 'AWS_PROXY', which passes the full
# HTTP request directly to the Lambda for processing.

# Integration for the status-checker (.zip Lambda)
resource "aws_apigatewayv2_integration" "status_checker_integration" {
  api_id           = aws_apigatewayv2_api.main_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.status_checker_lambda.invoke_arn
}

# Integration for the stitcher (Docker Lambda)
resource "aws_apigatewayv2_integration" "stitcher_integration" {
  api_id           = aws_apigatewayv2_api.main_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.stitcher_lambda.invoke_arn
  timeout_milliseconds = 30000
}

# Integration for the find-job (.zip Lambda)
resource "aws_apigatewayv2_integration" "find_job_integration" {
  api_id           = aws_apigatewayv2_api.main_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.find_job_lambda.invoke_arn
}


# --- 3. API Gateway Routes ---

# Defines the public-facing endpoints (routes) for the API
# and maps them to their corresponding backend integrations.

# Route for GET /status/{job_id}
# This endpoint is polled by the frontend to get job progress.
resource "aws_apigatewayv2_route" "get_status_route" {
  api_id    = aws_apigatewayv2_api.main_api.id
  route_key = "GET /status/{job_id}"
  target    = "integrations/${aws_apigatewayv2_integration.status_checker_integration.id}"
}

# Route for POST /stitch
# This endpoint is called once by the frontend to trigger the
# final aggregation (stitcher) Lambda.
resource "aws_apigatewayv2_route" "start_stitcher_route" {
  api_id    = aws_apigatewayv2_api.main_api.id
  route_key = "POST /stitch"
  target    = "integrations/${aws_apigatewayv2_integration.stitcher_integration.id}"
}

# Route for GET /find-job/{upload_id}
# This endpoint resolves the frontend's temporary 'upload_id'
# to the backend's permanent 'job_id' (the file ETag).
resource "aws_apigatewayv2_route" "get_job_by_upload_id_route" {
  api_id    = aws_apigatewayv2_api.main_api.id
  route_key = "GET /find-job/{upload_id}"
  target    = "integrations/${aws_apigatewayv2_integration.find_job_integration.id}"
}
# --- Outputs ---

# This output displays the invocation URL for the created HTTP API Gateway.
output "api_gateway_endpoint" {
  description = "The base URL of the HTTP API Gateway."
  value       = aws_apigatewayv2_api.main_api.api_endpoint
}
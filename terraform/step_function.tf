# --- Step Functions ---

# --- IAM Role for the State Machine ---
resource "aws_iam_role" "step_functions_role" {
  name               = "${var.project_name}-workflow-execution-role"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [{
      Action    = "sts:AssumeRole",
      Effect    = "Allow",
      Principal = { Service = "states.amazonaws.com" }
    }]
  })
}

# --- IAM Policy to allow Step Functions to invoke our Lambdas ---
resource "aws_iam_policy" "step_functions_policy" {
  name   = "${var.project_name}-workflow-invoke-lambda-policy"
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [{
      Action   = "lambda:InvokeFunction",
      Effect   = "Allow",
      Resource = [
        aws_lambda_function.sentiment_lambda.arn,
        aws_lambda_function.zeroshot_lambda.arn,
        aws_lambda_function.absa_lambda.arn
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "step_functions_policy_attachment" {
  role       = aws_iam_role.step_functions_role.name
  policy_arn = aws_iam_policy.step_functions_policy.arn
}


# --- The State Machine Definition ---
resource "aws_sfn_state_machine" "processing_workflow" {
  name     = "${var.project_name}-processing-workflow"
  role_arn = aws_iam_role.step_functions_role.arn

  definition = jsonencode({
    Comment = "Orchestrates the AI analysis of a single review batch.",
    StartAt = "SentimentAnalysis",
    States = {
      "SentimentAnalysis" : {
        Type     = "Task",
        Resource = "arn:aws:states:::lambda:invoke",
        Parameters = {
          "FunctionName" = aws_lambda_function.sentiment_lambda.function_name,
          "Payload.$"    = "$"
        },
        "ResultPath" : "$.LambdaOutput",
        "OutputPath" : "$.LambdaOutput.Payload",
        Retry : [{ 
            "ErrorEquals" : ["States.ALL"], 
            "IntervalSeconds" : 10, 
            "MaxAttempts" : 15,
            "BackoffRate" : 1.5 
        }],
        Catch : [{ "ErrorEquals" : ["States.ALL"], "Next" : "MarkAsFailed" }],
        "Next" : "ZeroShotClassification"
      },
      "ZeroShotClassification" : {
        Type     = "Task",
        Resource = "arn:aws:states:::lambda:invoke",
        Parameters = {
          "FunctionName" = aws_lambda_function.zeroshot_lambda.function_name,
          "Payload.$"    = "$"
        },
        "ResultPath" : "$.LambdaOutput",
        "OutputPath" : "$.LambdaOutput.Payload",
         Retry : [{ 
            "ErrorEquals" : ["States.ALL"], 
            "IntervalSeconds" : 10, 
            "MaxAttempts" : 15,
            "BackoffRate" : 1.5 
        }],
        Catch : [{ "ErrorEquals" : ["States.ALL"], "Next" : "MarkAsFailed" }],
        "Next" : "AspectBasedAnalysis"
      },
      "AspectBasedAnalysis" : {
        Type     = "Task",
        Resource = "arn:aws:states:::lambda:invoke",
        Parameters = {
          "FunctionName" = aws_lambda_function.absa_lambda.function_name,
          "Payload.$"    = "$"
        },
        "ResultPath" : "$.LambdaOutput", 
         Retry : [{ 
            "ErrorEquals" : ["States.ALL"], 
            "IntervalSeconds" : 10, 
            "MaxAttempts" : 15,
            "BackoffRate" : 1.5 
        }],
        Catch : [{ "ErrorEquals" : ["States.ALL"], "Next" : "MarkAsFailed" }],
        "End" : true
      },
      "MarkAsFailed" : {
        "Type" : "Fail",
        "Cause" : "An AI analysis step failed after multiple retries."
      }
    }
  })
}
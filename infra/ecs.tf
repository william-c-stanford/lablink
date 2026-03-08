resource "aws_ecs_cluster" "lablink" {
  name = "lablink-${var.environment}"
}

# --- IAM: Execution Role (ECS agent — pulls images + fetches SSM secrets) ---

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  name               = "lablink-ecs-execution-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow execution role to read SSM parameters for secrets injection
data "aws_iam_policy_document" "ecs_execution_ssm" {
  statement {
    actions   = ["ssm:GetParameters", "secretsmanager:GetSecretValue"]
    resources = ["arn:aws:ssm:${var.aws_region}:*:parameter/lablink/${var.environment}/*"]
  }
}

resource "aws_iam_role_policy" "ecs_execution_ssm" {
  name   = "ssm-read"
  role   = aws_iam_role.ecs_task_execution.id
  policy = data.aws_iam_policy_document.ecs_execution_ssm.json
}

# --- IAM: API Task Role (minimal S3 + SSM) ---

resource "aws_iam_role" "ecs_api_task" {
  name               = "lablink-api-task-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "api_task_policy" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.uploads.arn}/*"]
  }
  statement {
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.aws_region}:*:parameter/lablink/${var.environment}/*"]
  }
}

resource "aws_iam_role_policy" "api_task" {
  name   = "api-task-policy"
  role   = aws_iam_role.ecs_api_task.id
  policy = data.aws_iam_policy_document.api_task_policy.json
}

# --- IAM: Worker Task Role (same as API + broader S3 for parsing) ---

resource "aws_iam_role" "ecs_worker_task" {
  name               = "lablink-worker-task-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "worker_task_policy" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.uploads.arn, "${aws_s3_bucket.uploads.arn}/*"]
  }
  statement {
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.aws_region}:*:parameter/lablink/${var.environment}/*"]
  }
}

resource "aws_iam_role_policy" "worker_task" {
  name   = "worker-task-policy"
  role   = aws_iam_role.ecs_worker_task.id
  policy = data.aws_iam_policy_document.worker_task_policy.json
}

# --- SSM Parameters (populated out-of-band; referenced by task definitions) ---

resource "aws_ssm_parameter" "db_url" {
  name  = "/lablink/${var.environment}/DATABASE_URL"
  type  = "SecureString"
  value = "placeholder"  # Set manually after RDS provisioning
  lifecycle { ignore_changes = [value] }
}

resource "aws_ssm_parameter" "redis_url" {
  name  = "/lablink/${var.environment}/REDIS_URL"
  type  = "SecureString"
  value = "placeholder"
  lifecycle { ignore_changes = [value] }
}

resource "aws_ssm_parameter" "es_url" {
  name  = "/lablink/${var.environment}/ELASTICSEARCH_URL"
  type  = "SecureString"
  value = "placeholder"
  lifecycle { ignore_changes = [value] }
}

resource "aws_ssm_parameter" "s3_bucket" {
  name  = "/lablink/${var.environment}/S3_BUCKET"
  type  = "String"
  value = aws_s3_bucket.uploads.bucket
}

resource "aws_ssm_parameter" "secret_key" {
  name  = "/lablink/${var.environment}/SECRET_KEY"
  type  = "SecureString"
  value = "placeholder"  # Set manually with strong random value
  lifecycle { ignore_changes = [value] }
}

resource "aws_ssm_parameter" "redis_auth_token" {
  name  = "/lablink/${var.environment}/REDIS_AUTH_TOKEN"
  type  = "SecureString"
  value = "placeholder"  # Set manually with strong random value
  lifecycle { ignore_changes = [value] }
}

# --- CloudWatch Log Groups ---

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/lablink-api"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/lablink-worker"
  retention_in_days = 30
}

# --- Task Definitions ---

resource "aws_ecs_task_definition" "api" {
  family                   = "lablink-api-${var.environment}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_api_task.arn

  container_definitions = jsonencode([{
    name      = "api"
    image     = "${var.ecr_repo_url}:${var.image_tag}"
    essential = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    secrets = [
      { name = "DATABASE_URL",      valueFrom = aws_ssm_parameter.db_url.arn },
      { name = "REDIS_URL",         valueFrom = aws_ssm_parameter.redis_url.arn },
      { name = "ELASTICSEARCH_URL", valueFrom = aws_ssm_parameter.es_url.arn },
      { name = "S3_BUCKET",         valueFrom = aws_ssm_parameter.s3_bucket.arn },
      { name = "SECRET_KEY",        valueFrom = aws_ssm_parameter.secret_key.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 40
    }
  }])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "lablink-worker-${var.environment}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.ecs_worker_task.arn

  container_definitions = jsonencode([{
    name      = "worker"
    image     = "${var.ecr_repo_url}-worker:${var.image_tag}"
    essential = true
    secrets = [
      { name = "DATABASE_URL",      valueFrom = aws_ssm_parameter.db_url.arn },
      { name = "REDIS_URL",         valueFrom = aws_ssm_parameter.redis_url.arn },
      { name = "ELASTICSEARCH_URL", valueFrom = aws_ssm_parameter.es_url.arn },
      { name = "S3_BUCKET",         valueFrom = aws_ssm_parameter.s3_bucket.arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.worker.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "worker"
      }
    }
    healthCheck = {
      command     = ["CMD-SHELL", "celery -A lablink.tasks.celery_app inspect ping || exit 1"]
      interval    = 60
      timeout     = 10
      retries     = 3
      startPeriod = 60
    }
  }])
}

# --- ECS Services ---

resource "aws_ecs_service" "api" {
  name            = "lablink-api"
  cluster         = aws_ecs_cluster.lablink.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }
}

resource "aws_ecs_service" "worker" {
  name            = "lablink-worker"
  cluster         = aws_ecs_cluster.lablink.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.api.id]
    assign_public_ip = false
  }
}

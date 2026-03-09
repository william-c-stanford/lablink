terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  backend "s3" {
    bucket         = "lablink-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "lablink-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "lablink"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

variable "aws_region" {
  description = "AWS region"
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (production, staging)"
  default     = "production"
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  default     = "latest"
}

variable "ecr_repo_url" {
  description = "ECR repository base URL (without tag)"
  type        = string
}

data "aws_availability_zones" "available" {
  state = "available"
}

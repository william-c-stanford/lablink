resource "aws_db_instance" "lablink" {
  identifier        = "lablink-${var.environment}"
  engine            = "postgres"
  engine_version    = "16.3"
  instance_class    = "db.t4g.medium"
  allocated_storage = 20
  storage_type      = "gp3"
  db_name           = "lablink"
  username          = "lablink"

  # Managed password — stored in Secrets Manager, never in Terraform state
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.lablink.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.lablink.name

  publicly_accessible       = false
  multi_az                  = false # Enable for production HA
  skip_final_snapshot       = false
  final_snapshot_identifier = "lablink-${var.environment}-final"
  backup_retention_period   = 7
  deletion_protection       = true
  storage_encrypted         = true
}

resource "aws_db_parameter_group" "lablink" {
  name   = "lablink-pg16-${var.environment}"
  family = "postgres16"
}

resource "aws_db_subnet_group" "lablink" {
  name       = "lablink-${var.environment}"
  subnet_ids = aws_subnet.private[*].id
}

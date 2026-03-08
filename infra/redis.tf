# Must use replication_group (not aws_elasticache_cluster) to support AUTH + TLS.
# Encryption settings cannot be changed after creation.
resource "aws_elasticache_replication_group" "lablink" {
  replication_group_id       = "lablink-${var.environment}"
  description                = "LabLink Redis"
  node_type                  = "cache.t4g.micro"
  num_cache_clusters         = 1
  engine_version             = "7.0"
  parameter_group_name       = "default.redis7"
  port                       = 6379
  security_group_ids         = [aws_security_group.redis.id]
  subnet_group_name          = aws_elasticache_subnet_group.lablink.name
  transit_encryption_enabled = true
  at_rest_encryption_enabled = true
  auth_token                 = aws_ssm_parameter.redis_auth_token.value
}

resource "aws_elasticache_subnet_group" "lablink" {
  name       = "lablink-${var.environment}"
  subnet_ids = aws_subnet.private[*].id
}

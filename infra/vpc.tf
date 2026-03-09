resource "aws_vpc" "lablink" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = { Name = "lablink-${var.environment}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.lablink.id
  cidr_block        = cidrsubnet(aws_vpc.lablink.cidr_block, 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags = { Name = "lablink-private-${count.index + 1}" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.lablink.id
  cidr_block              = cidrsubnet(aws_vpc.lablink.cidr_block, 8, count.index + 10)
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
  tags = { Name = "lablink-public-${count.index + 1}" }
}

resource "aws_internet_gateway" "lablink" {
  vpc_id = aws_vpc.lablink.id
  tags = { Name = "lablink-${var.environment}" }
}

resource "aws_eip" "nat" {
  domain     = "vpc"
  depends_on = [aws_internet_gateway.lablink]
}

resource "aws_nat_gateway" "lablink" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  depends_on    = [aws_internet_gateway.lablink]
  tags = { Name = "lablink-${var.environment}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.lablink.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.lablink.id
  }
  tags = { Name = "lablink-public" }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.lablink.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.lablink.id
  }
  tags = { Name = "lablink-private" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# Security Groups

resource "aws_security_group" "api" {
  name        = "lablink-api-${var.environment}"
  description = "LabLink API ECS tasks"
  vpc_id      = aws_vpc.lablink.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.lablink.cidr_block]
  }
}

resource "aws_security_group" "rds" {
  name        = "lablink-rds-${var.environment}"
  description = "LabLink RDS PostgreSQL"
  vpc_id      = aws_vpc.lablink.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }
}

resource "aws_security_group" "redis" {
  name        = "lablink-redis-${var.environment}"
  description = "LabLink ElastiCache Redis"
  vpc_id      = aws_vpc.lablink.id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }
}

resource "aws_security_group" "opensearch" {
  name        = "lablink-opensearch-${var.environment}"
  description = "LabLink OpenSearch"
  vpc_id      = aws_vpc.lablink.id

  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.api.id]
  }
}

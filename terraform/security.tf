resource "yandex_vpc_security_group" "front" {
  name       = "${var.name_prefix}-front"
  network_id = yandex_vpc_network.lab.id
  ingress {
    protocol          = "TCP"
    port              = 22
    predefined_target = "self_security_group"
  }
  ingress {
    protocol       = "TCP"
    port           = 80
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    protocol          = "TCP"
    port              = 8080
    predefined_target = "loadbalancer_healthchecks"
  }
  ingress {
    protocol       = "TCP"
    port           = 22
    v4_cidr_blocks = var.admin_cidrs
  }
  egress {
    protocol       = "ANY"
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "yandex_vpc_security_group" "backend" {
  name       = "${var.name_prefix}-backend"
  network_id = yandex_vpc_network.lab.id
  ingress {
    protocol          = "TCP"
    port              = 21064
    predefined_target = "self_security_group"
  }
  dynamic "ingress" {
    for_each = toset([22, 3031])
    content {
      protocol          = "TCP"
      port              = ingress.value
      security_group_id = yandex_vpc_security_group.front.id
    }
  }
  ingress {
    protocol          = "TCP"
    port              = 7788
    predefined_target = "self_security_group"
  }
  ingress {
    protocol          = "UDP"
    from_port         = 5404
    to_port           = 5405
    predefined_target = "self_security_group"
  }
  ingress {
    protocol          = "TCP"
    port              = 2224
    predefined_target = "self_security_group"
  }
  ingress {
    protocol          = "TCP"
    port              = 2224
    security_group_id = yandex_vpc_security_group.front.id
  }
  egress {
    protocol       = "ANY"
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "yandex_vpc_security_group" "db" {
  name       = "${var.name_prefix}-db"
  network_id = yandex_vpc_network.lab.id
  ingress {
    protocol          = "TCP"
    port              = 22
    security_group_id = yandex_vpc_security_group.front.id
  }
  dynamic "ingress" {
    for_each = toset([5432, 5403, 2224])
    content {
      protocol          = "TCP"
      port              = ingress.value
      security_group_id = yandex_vpc_security_group.backend.id
    }
  }
  ingress {
    protocol          = "TCP"
    port              = 2224
    security_group_id = yandex_vpc_security_group.front.id
  }
  egress {
    protocol       = "ANY"
    v4_cidr_blocks = ["0.0.0.0/0"]
  }
}

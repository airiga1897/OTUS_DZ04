resource "yandex_lb_target_group" "front" {
  name = "${var.name_prefix}-front"
  dynamic "target" {
    for_each = toset(["nginx1", "nginx2"])
    content {
      subnet_id = yandex_vpc_subnet.lab.id
      address   = local.addresses[target.value]
    }
  }
}
resource "yandex_lb_network_load_balancer" "front" {
  name = var.name_prefix
  listener {
    name        = "http"
    port        = 80
    target_port = 80
    external_address_spec { ip_version = "ipv4" }
  }
  attached_target_group {
    target_group_id = yandex_lb_target_group.front.id
    healthcheck {
      name                = "nginx-ready"
      interval            = 2
      timeout             = 1
      healthy_threshold   = 2
      unhealthy_threshold = 2
      http_options {
        port = 8080
        path = "/health/front"
      }
    }
  }
}


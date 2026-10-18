resource "openstack_lb_loadbalancer_v2" "front" {
  name          = var.name_prefix
  vip_subnet_id = openstack_networking_subnet_v2.lab.id
  flavor_id     = var.lb_flavor_id
  depends_on    = [openstack_networking_router_interface_v2.lab]
}
resource "openstack_lb_listener_v2" "http" {
  name            = var.name_prefix
  protocol        = "TCP"
  protocol_port   = 80
  loadbalancer_id = openstack_lb_loadbalancer_v2.front.id
}
resource "openstack_lb_pool_v2" "front" {
  name        = var.name_prefix
  protocol    = "TCP"
  lb_method   = "ROUND_ROBIN"
  listener_id = openstack_lb_listener_v2.http.id
}
resource "openstack_lb_member_v2" "front" {
  for_each      = toset(["nginx1", "nginx2"])
  name          = each.key
  pool_id       = openstack_lb_pool_v2.front.id
  subnet_id     = openstack_networking_subnet_v2.lab.id
  address       = local.addresses[each.key]
  protocol_port = 80
  monitor_port  = 8080
}
resource "openstack_lb_monitor_v2" "front" {
  pool_id        = openstack_lb_pool_v2.front.id
  type           = "HTTP"
  delay          = 5
  timeout        = 3
  max_retries    = 3
  url_path       = "/health/front"
  expected_codes = "200"
}
resource "openstack_networking_floatingip_v2" "site" {
  pool    = var.external_network_name
  port_id = openstack_lb_loadbalancer_v2.front.vip_port_id
}

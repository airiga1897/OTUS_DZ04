locals {
  # Между ролями разрешены только нужные порты; внешние SSH /32 — отдельно.
  internal_rules = {
    front_ssh_peer    = { role = "front", source = "front", protocol = "tcp", first = 22, last = 22 }
    backend_dlm       = { role = "backend", source = "backend", protocol = "tcp", first = 21064, last = 21064 }
    front_http        = { role = "front", source = "subnet", protocol = "tcp", first = 80, last = 80 }
    front_health      = { role = "front", source = "subnet", protocol = "tcp", first = 8080, last = 8080 }
    backend_ssh       = { role = "backend", source = "front", protocol = "tcp", first = 22, last = 22 }
    backend_uwsgi     = { role = "backend", source = "front", protocol = "tcp", first = 3031, last = 3031 }
    backend_pcs_front = { role = "backend", source = "front", protocol = "tcp", first = 2224, last = 2224 }
    backend_pcs_peer  = { role = "backend", source = "backend", protocol = "tcp", first = 2224, last = 2224 }
    backend_drbd      = { role = "backend", source = "backend", protocol = "tcp", first = 7788, last = 7788 }
    backend_corosync  = { role = "backend", source = "backend", protocol = "udp", first = 5404, last = 5405 }
    db_ssh            = { role = "db", source = "front", protocol = "tcp", first = 22, last = 22 }
    db_pcs_front      = { role = "db", source = "front", protocol = "tcp", first = 2224, last = 2224 }
    db_pcs_backend    = { role = "db", source = "backend", protocol = "tcp", first = 2224, last = 2224 }
    db_postgres       = { role = "db", source = "backend", protocol = "tcp", first = 5432, last = 5432 }
    db_qnetd          = { role = "db", source = "backend", protocol = "tcp", first = 5403, last = 5403 }
  }
}
resource "openstack_networking_secgroup_v2" "role" {
  for_each             = toset(["front", "backend", "db"])
  name                 = "${var.name_prefix}-${each.key}"
  delete_default_rules = true
}
resource "openstack_networking_secgroup_rule_v2" "egress" {
  for_each          = openstack_networking_secgroup_v2.role
  direction         = "egress"
  ethertype         = "IPv4"
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = each.value.id
}
resource "openstack_networking_secgroup_rule_v2" "admin" {
  for_each          = toset(var.admin_cidrs)
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = var.admin_ssh_port
  port_range_max    = var.admin_ssh_port
  remote_ip_prefix  = each.value
  security_group_id = openstack_networking_secgroup_v2.role["front"].id
}
resource "openstack_networking_secgroup_rule_v2" "internal" {
  for_each          = local.internal_rules
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = each.value.protocol
  port_range_min    = each.value.first
  port_range_max    = each.value.last
  remote_group_id   = each.value.source == "subnet" ? null : openstack_networking_secgroup_v2.role[each.value.source].id
  remote_ip_prefix  = each.value.source == "subnet" ? var.subnet_cidr : null
  security_group_id = openstack_networking_secgroup_v2.role[each.value.role].id
}

locals {
  nodes = {
    nginx1   = { host = 10, role = "front" }
    nginx2   = { host = 11, role = "front" }
    backend1 = { host = 21, role = "backend" }
    backend2 = { host = 22, role = "backend" }
    db       = { host = 30, role = "db" }
  }
  addresses = { for name, n in local.nodes : name => cidrhost(var.subnet_cidr, n.host) }
}
data "openstack_networking_network_v2" "external" {
  name     = var.external_network_name
  external = true
}
resource "openstack_networking_network_v2" "lab" {
  name           = var.name_prefix
  admin_state_up = true
}
resource "openstack_networking_subnet_v2" "lab" {
  name        = var.name_prefix
  network_id  = openstack_networking_network_v2.lab.id
  cidr        = var.subnet_cidr
  ip_version  = 4
  enable_dhcp = true
}
resource "openstack_networking_router_v2" "egress" {
  name                = var.name_prefix
  external_network_id = data.openstack_networking_network_v2.external.id
}
resource "openstack_networking_router_interface_v2" "lab" {
  router_id = openstack_networking_router_v2.egress.id
  subnet_id = openstack_networking_subnet_v2.lab.id
}
resource "openstack_networking_port_v2" "node" {
  for_each           = local.nodes
  name               = "${var.name_prefix}-${each.key}"
  network_id         = openstack_networking_network_v2.lab.id
  security_group_ids = [openstack_networking_secgroup_v2.role[each.value.role].id]
  fixed_ip {
    subnet_id  = openstack_networking_subnet_v2.lab.id
    ip_address = local.addresses[each.key]
  }
}
resource "openstack_blockstorage_volume_v3" "boot" {
  for_each          = local.nodes
  name              = "${var.name_prefix}-${each.key}-boot"
  size              = var.boot_disk_gb
  image_id          = var.image_id
  volume_type       = var.volume_type
  availability_zone = var.availability_zone
}
resource "openstack_blockstorage_volume_v3" "data" {
  for_each          = toset(["backend1", "backend2"])
  name              = "${var.name_prefix}-${each.key}-data"
  size              = var.data_disk_gb
  volume_type       = var.volume_type
  availability_zone = var.availability_zone
}
resource "openstack_compute_servergroup_v2" "pair" {
  for_each = toset(["front", "backend"])
  name     = "${var.name_prefix}-${each.key}"
  policies = ["anti-affinity"]
}
resource "openstack_compute_instance_v2" "node" {
  for_each          = local.nodes
  name              = "${var.name_prefix}-${each.key}"
  flavor_id         = var.flavor_ids[each.value.role]
  availability_zone = var.availability_zone
  block_device {
    uuid                  = openstack_blockstorage_volume_v3.boot[each.key].id
    source_type           = "volume"
    destination_type      = "volume"
    boot_index            = 0
    delete_on_termination = false
  }
  network { port = openstack_networking_port_v2.node[each.key].id }
  dynamic "scheduler_hints" {
    for_each = each.value.role == "db" ? [] : [each.value.role]
    content { group = openstack_compute_servergroup_v2.pair[scheduler_hints.value].id }
  }
  user_data = "#cloud-config\n${yamlencode({
    hostname   = each.key
    users      = [{ name = var.ssh_user, groups = ["sudo"], shell = "/bin/bash", sudo = "ALL=(ALL) NOPASSWD:ALL", lock_passwd = true, ssh_authorized_keys = [trimspace(file(pathexpand(var.ssh_public_key_path)))] }]
    ssh_pwauth = false
    write_files = each.value.role == "front" && var.admin_ssh_port != 22 ? [{
      path        = "/etc/ssh/sshd_config.d/10-otus-admin-port.conf"
      permissions = "0644"
      content     = "Port 22\nPort ${var.admin_ssh_port}\n"
    }] : []
    runcmd = each.value.role == "front" && var.admin_ssh_port != 22 ? [
      "sshd -t && systemctl stop ssh.service ssh.socket && systemctl disable ssh.socket && systemctl enable --now ssh.service"
    ] : []
  })}"
  depends_on = [openstack_networking_router_interface_v2.lab]
}
resource "openstack_compute_volume_attach_v2" "data" {
  for_each    = openstack_blockstorage_volume_v3.data
  instance_id = openstack_compute_instance_v2.node[each.key].id
  volume_id   = each.value.id
}
resource "openstack_networking_floatingip_v2" "admin" {
  for_each   = toset(["nginx1", "nginx2"])
  pool       = var.external_network_name
  port_id    = openstack_networking_port_v2.node[each.key].id
  depends_on = [openstack_networking_router_interface_v2.lab]
}

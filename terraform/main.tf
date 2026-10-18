locals {
  nodes = {
    nginx1   = { host = 10, memory = 1, disk = 10, role = "front" }
    nginx2   = { host = 11, memory = 1, disk = 10, role = "front" }
    backend1 = { host = 21, memory = 2, disk = 10, role = "backend" }
    backend2 = { host = 22, memory = 2, disk = 10, role = "backend" }
    db       = { host = 30, memory = 1, disk = 10, role = "db" }
  }
  addresses       = { for name, node in local.nodes : name => cidrhost(var.subnet_cidr, node.host) }
  security_groups = { front = yandex_vpc_security_group.front.id, backend = yandex_vpc_security_group.backend.id, db = yandex_vpc_security_group.db.id }
}
data "yandex_compute_image" "ubuntu" {
  count  = var.image_id == null ? 1 : 0
  family = "ubuntu-2404-lts"
}
resource "yandex_vpc_network" "lab" { name = var.name_prefix }
resource "yandex_vpc_gateway" "egress" {
  name = "${var.name_prefix}-nat"
  shared_egress_gateway {}
}
resource "yandex_vpc_route_table" "egress" {
  name       = "${var.name_prefix}-egress"
  network_id = yandex_vpc_network.lab.id
  static_route {
    destination_prefix = "0.0.0.0/0"
    gateway_id         = yandex_vpc_gateway.egress.id
  }
}
resource "yandex_vpc_subnet" "lab" {
  name           = var.name_prefix
  zone           = var.zone
  network_id     = yandex_vpc_network.lab.id
  v4_cidr_blocks = [var.subnet_cidr]
  route_table_id = yandex_vpc_route_table.egress.id
}
resource "yandex_vpc_address" "admin" {
  for_each = toset(["nginx1", "nginx2"])
  name     = "${var.name_prefix}-${each.key}"
  external_ipv4_address { zone_id = var.zone }
}
resource "yandex_compute_disk" "data" {
  for_each = toset(["backend1", "backend2"])
  name     = "${var.name_prefix}-${each.key}-data"
  zone     = var.zone
  size     = 1
  type     = "network-hdd"
}
resource "yandex_iam_service_account" "fence" {
  name        = "${var.name_prefix}-fence"
  folder_id   = var.folder_id
  description = "Остановка только двух backend учебного стенда для STONITH."
}
resource "yandex_compute_instance" "node" {
  for_each           = local.nodes
  name               = "${var.name_prefix}-${each.key}"
  hostname           = each.key
  platform_id        = "standard-v3"
  zone               = var.zone
  folder_id          = var.folder_id
  service_account_id = each.value.role == "backend" ? yandex_iam_service_account.fence.id : null
  labels             = { project = var.name_prefix, role = each.value.role }
  resources {
    cores         = 2
    core_fraction = var.core_fraction
    memory        = each.value.memory
  }
  boot_disk {
    auto_delete = true
    initialize_params {
      image_id = var.image_id != null ? var.image_id : data.yandex_compute_image.ubuntu[0].id
      size     = each.value.disk
      type     = "network-hdd"
    }
  }
  dynamic "secondary_disk" {
    for_each = each.value.role == "backend" ? [each.key] : []
    content {
      disk_id     = yandex_compute_disk.data[secondary_disk.value].id
      device_name = "gfs-data"
      auto_delete = false
    }
  }
  network_interface {
    subnet_id          = yandex_vpc_subnet.lab.id
    ip_address         = local.addresses[each.key]
    nat                = each.value.role == "front"
    nat_ip_address     = each.value.role == "front" ? yandex_vpc_address.admin[each.key].external_ipv4_address[0].address : null
    security_group_ids = [local.security_groups[each.value.role]]
  }
  metadata_options {
    gce_http_endpoint = each.value.role == "backend" ? 1 : 2
    gce_http_token    = each.value.role == "backend" ? 1 : 2
  }
  metadata = {
    user-data = "#cloud-config\n${yamlencode({
      users      = [{ name = var.ssh_user, groups = ["sudo"], shell = "/bin/bash", sudo = "ALL=(ALL) NOPASSWD:ALL", lock_passwd = true, ssh_authorized_keys = [trimspace(file(pathexpand(var.ssh_public_key_path)))] }]
      ssh_pwauth = false
    })}"
  }
}
# Новые ВМ стенда: привязка не затрагивает IAM существующих ресурсов.
resource "yandex_compute_instance_iam_binding" "fence" {
  for_each    = toset(["backend1", "backend2"])
  instance_id = yandex_compute_instance.node[each.key].id
  role        = "compute.operator"
  members     = ["serviceAccount:${yandex_iam_service_account.fence.id}"]
}


output "lab" {
  value = {
    ssh_user         = var.ssh_user
    private_ips      = local.addresses
    public_ips       = { for n, addr in yandex_vpc_address.admin : n => addr.external_ipv4_address[0].address }
    instance_ids     = { for n, vm in yandex_compute_instance.node : n => vm.id }
    site_url         = "http://${one(one(yandex_lb_network_load_balancer.front.listener).external_address_spec).address}"
    load_balancer_id = yandex_lb_network_load_balancer.front.id
  }
}


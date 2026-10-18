output "lab" {
  value = {
    cloud_provider   = "selectel"
    ssh_user         = var.ssh_user
    admin_ssh_port   = var.admin_ssh_port
    private_ips      = local.addresses
    public_ips       = { for n, ip in openstack_networking_floatingip_v2.admin : n => ip.address }
    instance_ids     = { for n, vm in openstack_compute_instance_v2.node : n => vm.id }
    data_volume_ids  = { for n, disk in openstack_blockstorage_volume_v3.data : n => disk.id }
    site_url         = "http://${openstack_networking_floatingip_v2.site.address}"
    load_balancer_id = openstack_lb_loadbalancer_v2.front.id
  }
}

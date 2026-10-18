variable "region" { type = string }
variable "availability_zone" { type = string }
variable "image_id" { type = string }
variable "volume_type" { type = string }
variable "lb_flavor_id" { type = string }
variable "external_network_name" {
  type    = string
  default = "external-network"
}
variable "flavor_ids" {
  type = object({ front = string, backend = string, db = string })
}
variable "name_prefix" {
  type    = string
  default = "otus-dz04-sel"
}
variable "subnet_cidr" {
  type    = string
  default = "10.44.0.0/24"
}
variable "admin_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.admin_cidrs) > 0 && alltrue([for c in var.admin_cidrs : can(cidrnetmask(c)) && split("/", c)[1] == "32"])
    error_message = "Укажите IPv4 /32 администратора."
  }
}
variable "ssh_user" {
  type    = string
  default = "otus"
}
variable "admin_ssh_port" {
  type    = number
  default = 22
  validation {
    condition     = contains([22, 443], var.admin_ssh_port)
    error_message = "Внешний SSH-порт: 22 или 443."
  }
}
variable "ssh_public_key_path" {
  type    = string
  default = "../.local/selectel/otus_dz04.pub"
}
variable "boot_disk_gb" {
  type    = number
  default = 10
  validation {
    condition     = var.boot_disk_gb >= 10 && floor(var.boot_disk_gb) == var.boot_disk_gb
    error_message = "Не менее 10 ГБ; также проверьте min_disk выбранного образа."
  }
}
variable "data_disk_gb" {
  type    = number
  default = 1
  validation {
    condition     = var.data_disk_gb >= 1 && floor(var.data_disk_gb) == var.data_disk_gb
    error_message = "Нужен целочисленный размер от 1 ГБ; минимум типа диска проверяется отдельно."
  }
}

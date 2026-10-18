variable "cloud_id" { type = string }
variable "folder_id" { type = string }
variable "zone" {
  type    = string
  default = "ru-central1-a"
}
variable "name_prefix" {
  type    = string
  default = "otus-dz04"
}
variable "subnet_cidr" {
  type    = string
  default = "10.40.0.0/24"
}
variable "admin_cidrs" {
  type = list(string)
  validation {
    condition     = length(var.admin_cidrs) > 0 && alltrue([for c in var.admin_cidrs : can(cidrnetmask(c)) && split("/", c)[1] == "32"])
    error_message = "Укажите отдельные IPv4 /32 администратора."
  }
}
variable "ssh_user" {
  type    = string
  default = "otus"
}
variable "ssh_public_key_path" {
  type    = string
  default = "../.local/otus_dz04.pub"
}
variable "image_id" {
  type    = string
  default = null
}
variable "core_fraction" {
  type    = number
  default = 20
  validation {
    condition     = contains([20, 50, 100], var.core_fraction)
    error_message = "Допустимы 20, 50 или 100; экономичный стенд использует 20."
  }
}


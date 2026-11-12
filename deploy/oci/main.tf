# VM del paper trading en Oracle Cloud Always Free (PQ-56; semilla de PQ-70).
#
# Portable: no lleva identificadores de ninguna cuenta ni región. Busca solo el dominio de
# disponibilidad y la imagen de Ubuntu 24.04 compatible con la forma elegida. Crea su propia red
# pública con un único puerto de entrada abierto, el 22 (SSH). El dashboard se ve por túnel SSH.
# Guía: docs/runbooks/oracle-cloud.md

terraform {
  required_version = ">= 1.5"
  required_providers {
    oci = {
      source = "oracle/oci"
    }
  }
}

provider "oci" {
  region = var.region
}

locals {
  is_flex = length(regexall("Flex$", var.shape)) > 0
  is_arm  = length(regexall("^VM\\.Standard\\.A", var.shape)) > 0
  tags    = { proyecto = "prometheusquant", ticket = "PQ-56" }
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

# Ubuntu 24.04 completa (no «Minimal»), la build más reciente compatible con la forma.
data "oci_core_images" "ubuntu" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "24.04"
  shape                    = var.shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"

  filter {
    name   = "display_name"
    values = [local.is_arm ? "^Canonical-Ubuntu-24\\.04-aarch64-\\d" : "^Canonical-Ubuntu-24\\.04-\\d"]
    regex  = true
  }
}

resource "oci_core_vcn" "main" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.0.0.0/16"]
  display_name   = "prometheus-vcn"
  dns_label      = "prometheus"
  freeform_tags  = local.tags
}

resource "oci_core_internet_gateway" "main" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "prometheus-igw"
  enabled        = true
  freeform_tags  = local.tags
}

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "prometheus-public-rt"
  freeform_tags  = local.tags

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.main.id
  }
}

# Solo el 22 de entrada. ICMP 3/4 lo exige el descubrimiento de MTU; el resto, cerrado.
resource "oci_core_security_list" "ssh_only" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "prometheus-ssh-only"
  freeform_tags  = local.tags

  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }

  ingress_security_rules {
    protocol = "6" # TCP
    source   = "0.0.0.0/0"
    tcp_options {
      min = 22
      max = 22
    }
  }

  ingress_security_rules {
    protocol = "1" # ICMP
    source   = "0.0.0.0/0"
    icmp_options {
      type = 3
      code = 4
    }
  }
}

resource "oci_core_subnet" "public" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.main.id
  cidr_block                 = "10.0.0.0/24"
  display_name               = "prometheus-public-subnet"
  dns_label                  = "public"
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.ssh_only.id]
  prohibit_public_ip_on_vnic = false
  freeform_tags              = local.tags
}

resource "oci_core_instance" "paper" {
  compartment_id      = var.compartment_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[var.availability_domain_number - 1].name
  display_name        = var.instance_name
  shape               = var.shape
  freeform_tags       = local.tags

  dynamic "shape_config" {
    for_each = local.is_flex ? [1] : []
    content {
      ocpus         = var.ocpus
      memory_in_gbs = var.memory_gbs
    }
  }

  source_details {
    source_type             = "image"
    source_id               = data.oci_core_images.ubuntu.images[0].id
    boot_volume_size_in_gbs = var.boot_volume_gbs
  }

  create_vnic_details {
    subnet_id                 = oci_core_subnet.public.id
    assign_public_ip          = true
    assign_private_dns_record = true
    hostname_label            = "paper"
  }

  metadata = {
    ssh_authorized_keys = trimspace(var.ssh_public_keys)
  }

  instance_options {
    are_legacy_imds_endpoints_disabled = true
  }

  # Si Oracle reinicia el host por mantenimiento, la VM vuelve a arrancar sola.
  availability_config {
    recovery_action = "RESTORE_INSTANCE"
  }

  is_pv_encryption_in_transit_enabled = true
}

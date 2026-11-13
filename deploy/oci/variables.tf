# Variables del stack de la VM del paper trading (PQ-56).
# Resource Manager de Oracle rellena solas tenancy_ocid, compartment_ocid y region.

variable "tenancy_ocid" {
  type        = string
  description = "OCID de la cuenta (lo pone Resource Manager)."
}

variable "compartment_ocid" {
  type        = string
  description = "Compartimento donde se crea todo (lo pone Resource Manager)."
}

variable "region" {
  type        = string
  description = "Región de origen de la cuenta (la pone Resource Manager). Nunca una de EE. UU."
}

variable "ssh_public_keys" {
  type        = string
  description = "Claves SSH públicas con acceso, separadas por comas: la tuya,la de tu compañero."

  validation {
    condition     = length(regexall("ssh-(ed25519|rsa) ", var.ssh_public_keys)) >= 1
    error_message = "Pega al menos una clave pública que empiece por ssh-ed25519 o ssh-rsa."
  }
}

variable "shape" {
  type        = string
  default     = "VM.Standard.A1.Flex"
  description = "VM.Standard.A1.Flex (Ampere, ARM) o VM.Standard.E2.1.Micro (AMD, si no hay capacidad)."
}

variable "ocpus" {
  type        = number
  default     = 2
  description = "Solo A1.Flex. Límite Always Free: 2 OCPU EN TOTAL entre todas las A1 de la cuenta."

  validation {
    condition     = var.ocpus >= 1 && var.ocpus <= 2
    error_message = "Always Free permite 1 o 2 OCPU de A1 en total."
  }
}

variable "memory_gbs" {
  type        = number
  default     = 12
  description = "Solo A1.Flex. Límite Always Free: 12 GB EN TOTAL entre todas las A1 de la cuenta."

  validation {
    condition     = var.memory_gbs >= 1 && var.memory_gbs <= 12
    error_message = "Always Free permite hasta 12 GB de A1 en total."
  }
}

variable "boot_volume_gbs" {
  type        = number
  default     = 100
  description = "Disco de arranque. El cupo gratuito es de 200 GB en total."
}

variable "availability_domain_number" {
  type        = number
  default     = 1
  description = "Déjalo en 1. São Paulo y Bogotá tienen un solo dominio; solo las regiones grandes tienen 2 o 3."
}

variable "variant" {
  type        = string
  default     = "a12"
  description = "Sufijo corto de esta variante (a12, a11, micro): nombra la VM y su red para que no choquen."

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{0,9}$", var.variant))
    error_message = "Solo minúsculas y números, empezando por letra (máx. 10)."
  }
}

output "public_ip" {
  description = "IP pública de la VM: es lo único que hay que pasarle al agente."
  value       = oci_core_instance.paper.public_ip
}

output "ssh" {
  description = "Comando para conectarse."
  value       = "ssh -i ~/.ssh/prometheus_oci ubuntu@${oci_core_instance.paper.public_ip}"
}

output "image" {
  description = "Imagen usada (para el registro)."
  value       = data.oci_core_images.ubuntu.images[0].display_name
}

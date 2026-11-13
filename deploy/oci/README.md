# deploy/oci: VM del paper trading en Oracle Cloud (Always Free)

Stack de Terraform **portable**: sirve para cualquier cuenta y región. Crea:

- una red propia con IP pública y **solo el puerto 22 abierto**;
- una VM **Ubuntu 24.04** Always Free;
- la imagen y el dominio de disponibilidad, que los busca solo.

Guía completa, con las reglas de Oracle, en [`docs/runbooks/oracle-cloud.md`](../../docs/runbooks/oracle-cloud.md).

## Usarlo desde la consola, sin instalar nada

1. Empaqueta los `.tf` en un `.zip` con los archivos en la raíz:

    ```bash
    cd deploy/oci && zip prometheus-oci-stack.zip *.tf
    ```

2. Consola de Oracle → ☰ → **Developer Services** → **Resource Manager** → **Stacks** →
   **Create stack** → **My configuration** → sube el `.zip`.
3. En **Configure variables**:

    | Variable | Qué poner |
    |---|---|
    | `ssh_public_keys` | Tu clave pública y la de tu compañero, **separadas por una coma** (la consola no admite saltos de línea) |
    | `shape` | `VM.Standard.A1.Flex`, o `VM.Standard.E2.1.Micro` si A1 no tiene capacidad |
    | `ocpus` / `memory_gbs` | `2` / `12` (todo el cupo); `1` / `6` si 2/12 no tiene capacidad |
    | El resto | Como viene |

4. **Create**, y luego **Actions → Apply** (*Automatically approved*).
5. Cuando el trabajo termine en **Succeeded**, la pestaña **Outputs** muestra `public_ip`.

## Si dice «Out of host capacity»

No hay capacidad de esa forma en ese momento. Vuelve a pulsar **Apply** más tarde, con un rato
entre intentos: Oracle limita las peticiones («Too many requests»). Mientras tanto se puede editar
el stack con `ocpus = 1` y `memory_gbs = 6`, o con la micro.

**Crecer después:** cambia `ocpus` y `memory_gbs` en el stack y pulsa **Apply**. Es la misma VM:
Oracle la reinicia y conserva el disco y la IP.

**Guardia del límite:** antes de crear una A1, el stack suma las A1 que ya hay en la cuenta. Si se
superarían 2 OCPU o 12 GB, se niega con un mensaje claro (Oracle desactivaría todas). La micro
(E2.1.Micro) tiene su propio cupo y puede convivir con una A1. Cada variante (`variant`) tiene
nombre y red propios.

## Validación local (opcional)

```bash
terraform init -backend=false && terraform validate   # Terraform 1.5.x, como Resource Manager
```

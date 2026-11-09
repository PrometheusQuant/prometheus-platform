# Cuenta de Oracle Cloud y VM del paper trading (PQ-56)

Guía para el titular. La cuenta pide identidad y una tarjeta, así que solo la puede crear él.
Después, el agente despliega por SSH con una clave dedicada (PQ-57).

Condiciones de Oracle verificadas el 2026-11-09 en su documentación oficial:
[Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
y [registro](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingup_topic-Sign_Up_for_Free_Oracle_Cloud_Promotion.htm).

!!! warning "Tres reglas que no tienen vuelta atrás"
    - **La región de origen es permanente** y la VM gratuita solo puede vivir ahí. No elijas una
      región de **EE. UU.**: Binance bloquea esas IP y el runner no podría leer el mercado.
    - **Límite de Ampere A1: 2 OCPU y 12 GB en total** en toda la cuenta. Si se supera, Oracle
      desactiva **todas** las instancias A1 y las borra a los 30 días.
    - **Oracle reclama las VM gratuitas ociosas**: las que durante 7 días tienen por debajo del
      20 % la CPU (percentil 95), la red y, en A1, la memoria. Ver «Riesgo de reclamación».

## 1. Crear la cuenta (≈ 15 min)

1. Entra en <https://signup.cloud.oracle.com/>.
2. Datos personales:
    - país: **Bolivia**;
    - correo: el tuyo (verifícalo con el enlace que llega).
3. **Nombre de la cuenta (tenancy):** `prometheusquant`. Es la URL de acceso; anótalo.
4. **Región de origen (home region)**, en este orden de preferencia:
    1. **Brazil East (São Paulo)**, `sa-saopaulo-1`;
    2. **Chile Central (Santiago)**, `sa-santiago-1`;
    3. Mexico Central (Querétaro), `mx-queretaro-1`.

    Nunca una de EE. UU. Si dudas, para y pregunta: no se puede cambiar.
5. **Verificación de pago:** una tarjeta de crédito, o de débito que funcione como crédito.
    - No sirven las tarjetas prepago, virtuales ni de débito con PIN.
    - Oracle hace una retención temporal pequeña que se devuelve sola, y **no cobra** mientras la
      cuenta no se actualice a pago.
6. Acepta y espera el correo de «cuenta lista», que puede tardar unos minutos.

**No actualices la cuenta a «Pay As You Go»** sin hablarlo antes: deja de ser gratuita.

## 2. Proteger la cuenta (≈ 5 min)

1. Entra en <https://cloud.oracle.com/> con el nombre de la cuenta.
2. Activa la **verificación en dos pasos (MFA)** con una app (Oracle Mobile Authenticator, Google
   Authenticator o similar). Está en el menú del perfil, arriba a la derecha.
3. La contraseña y los códigos de MFA no van al chat, al repo ni a WhatsApp.

## 3. Clave SSH para la VM (≈ 1 min, en tu terminal de WSL)

Es una clave **solo para este servidor**, sin frase de paso, para que el agente pueda desplegar:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/prometheus_oci -C "prometheusquant-oci" -N ""
cat ~/.ssh/prometheus_oci.pub
```

- La **pública** (`.pub`) se pega en Oracle en el paso 4.
- La **privada** (`~/.ssh/prometheus_oci`) no sale nunca de tu máquina.

## 4. Crear la VM (≈ 10 min)

Menú ☰ → **Compute** → **Instances** → **Create instance**.

| Campo | Valor |
|---|---|
| Name | `prometheus-paper` |
| Placement | El dominio de disponibilidad que ofrezca (si da error de capacidad, prueba otro) |
| Image | **Canonical Ubuntu 24.04** (la variante *aarch64*; Oracle la ofrece sola al elegir A1) |
| Shape | **Ampere → VM.Standard.A1.Flex**, **2 OCPU** y **12 GB** (todo el cupo gratuito, nada más) |
| Networking | *Create new virtual cloud network* y *public subnet*; **Assign a public IPv4 address**: sí |
| SSH keys | *Paste public keys*: el contenido de `~/.ssh/prometheus_oci.pub` |
| Boot volume | 100 GB (el cupo gratuito es de 200 GB en total) |

Pulsa **Create**. En 1–2 minutos el estado pasa a *Running*; copia la **Public IP address**.

**Si dice «Out of capacity for shape VM.Standard.A1.Flex»** (pasa en regiones concurridas):

- reintenta más tarde o con otro dominio de disponibilidad;
- mientras tanto se puede usar **VM.Standard.E2.1.Micro** (AMD, 1/8 OCPU, 1 GB, también gratuita).
  Alcanza para el runner y el vigilante, pero no para Dagster ni para el dashboard.

## 5. Comprobar que solo está abierto el 22

Instancia → enlace de la **subnet** → **Security Lists** → *Default Security List*.

- **Ingress rules:** solo TCP **22** desde `0.0.0.0/0`, más las de ICMP que trae por defecto.
  **No añadas** el 8501 (dashboard) ni otros puertos.
- El dashboard se verá por un túnel SSH (`ssh -L 8501:localhost:8501 …`), nunca expuesto a
  internet. Lo configura PQ-57.

## 6. Primera conexión y prueba de Binance (≈ 2 min)

```bash
ssh -i ~/.ssh/prometheus_oci ubuntu@<IP_PÚBLICA>
# ya dentro de la VM:
curl -s -o /dev/null -w "%{http_code}\n" "https://fapi.binance.com/fapi/v1/premiumIndex?symbol=SOLUSDT"
curl -s -o /dev/null -w "%{http_code}\n" "https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT"
exit
```

Las dos deben responder **200**. Un **451** o **403** es que Binance bloquea la región: para y avisa
antes de seguir.

## 7. Entregar al agente

Pásale solo esto, que no es secreto:

- la **IP pública** de la VM;
- la región elegida;
- el resultado de las dos pruebas de Binance (los códigos 200).

Con eso, el agente se conecta con `~/.ssh/prometheus_oci` desde tu misma máquina y sigue con
PQ-57 (Docker, runner, vigilante, túnel del dashboard) y PQ-115 (usuarios de David y Boris).

## Riesgo de reclamación de la VM ociosa

El runner del carry es ligero: un ciclo por minuto y unas pocas peticiones. Por sí solo podría
quedar por debajo del 20 % de CPU, red y memoria, y Oracle podría reclamar la VM. Mitigaciones:

- **Uso real del servidor:** con el runner, el vigilante, el dashboard y el lakehouse del equipo
  (PQ-115), la memoria usada debería superar el 20 % de 12 GB (2,4 GB). Se verifica con
  `free -h` tras el despliegue, *por verificar en PQ-57*.
- **Copias de seguridad** del diario y del estado del bróker fuera de la VM (PQ-73). Si Oracle
  reclama la VM, se recrea y se restaura.
- **Plan B:** actualizar la cuenta a *Pay As You Go* con un presupuesto y una alerta en 0 USD.
  Que eso evite la reclamación está *por verificar* en la documentación de Oracle. Hay riesgo de
  cargos: es una decisión del titular.
